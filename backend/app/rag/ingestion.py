import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.github.client import GitHubApiClient, GitHubApiError
from app.models.code_rag import RepoCodeChunk, RepoIndexingJob
from app.models.github import GitHubInstallation, GitHubRepository
from app.rag.chunking import CodeChunker
from app.rag.embeddings.base import BaseEmbeddingProvider
from app.rag.filtering import ExclusionReason, FileFilter

logger = logging.getLogger(__name__)


class RepositoryIngestionService:
    """Orchestrates repository tree retrieval, filtering, chunking, embedding, and storage."""

    def __init__(
        self,
        github_client: GitHubApiClient | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
        file_filter: FileFilter | None = None,
        chunker: CodeChunker | None = None,
    ):
        self.settings = get_settings()
        self.github_client = github_client or GitHubApiClient(self.settings)
        self.file_filter = file_filter or FileFilter(
            max_bytes=self.settings.CODE_RAG_MAX_FILE_SIZE_BYTES
        )
        self.chunker = chunker or CodeChunker(
            target_lines=self.settings.CODE_RAG_CHUNK_SIZE_LINES,
            overlap_lines=self.settings.CODE_RAG_CHUNK_OVERLAP_LINES,
        )
        self.embedding_provider = embedding_provider

    async def ingest_repository(
        self,
        db: Session,
        job_id: Any,
    ) -> RepoIndexingJob:
        """Run the ingestion pipeline for a given RepoIndexingJob."""
        job = db.get(RepoIndexingJob, job_id)
        if not job:
            raise ValueError(f"RepoIndexingJob {job_id} not found")

        repo: GitHubRepository | None = db.get(GitHubRepository, job.repository_id)
        if not repo:
            job.status = "failed"
            job.error_summary = "Repository record not found in database"
            db.commit()
            return job

        installation: GitHubInstallation | None = db.get(GitHubInstallation, repo.installation_id)
        if not installation or installation.status != "active":
            job.status = "failed"
            job.error_summary = "GitHub installation is missing or inactive"
            db.commit()
            return job

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        exclusions_count: dict[str, int] = {reason.value: 0 for reason in ExclusionReason}
        accepted_files: list[dict[str, Any]] = []

        try:
            # 1. Resolve commit SHA if not set or verify
            if not job.commit_sha or len(job.commit_sha) != 40:
                target_ref = job.target_ref or repo.default_branch or "main"
                commit_sha = self.github_client.get_ref_commit(
                    installation_id=installation.installation_id,
                    owner=repo.owner_login,
                    repo=repo.name,
                    ref=target_ref,
                )
                job.commit_sha = commit_sha
                db.commit()
            else:
                commit_sha = job.commit_sha

            # 2. Fetch recursive git tree
            tree_data = self.github_client.get_tree(
                installation_id=installation.installation_id,
                owner=repo.owner_login,
                repo=repo.name,
                tree_sha=commit_sha,
                recursive=True,
            )

            raw_tree = tree_data.get("tree", [])
            is_truncated = tree_data.get("truncated", False)
            total_discovered = len(raw_tree)
            job.files_discovered = total_discovered

            # 3. Filter entries by path and metadata
            max_files = self.settings.CODE_RAG_MAX_FILES_PER_REPO

            for item in raw_tree:
                # Only process blobs (files)
                if item.get("type") != "blob":
                    continue

                path = item.get("path", "")
                size = item.get("size")
                decision = self.file_filter.evaluate_path(path, file_size=size)

                if not decision.accepted:
                    reason_key = decision.reason.value if decision.reason else "other"
                    exclusions_count[reason_key] = exclusions_count.get(reason_key, 0) + 1
                    continue

                accepted_files.append({
                    "path": path,
                    "sha": item.get("sha"),
                    "size": size,
                    "language": decision.language,
                })

                if len(accepted_files) >= max_files:
                    logger.info(f"Reached max indexing files limit ({max_files}) for {repo.full_name}")
                    break

            job.files_accepted = len(accepted_files)
            job.files_excluded = total_discovered - len(accepted_files)
            job.exclusions_summary = exclusions_count
            db.commit()

            # 4. Fetch content and chunk files
            all_chunks_to_insert: list[dict[str, Any]] = []
            files_failed = 0

            for f_info in accepted_files:
                path = f_info["path"]
                sha = f_info["sha"]
                language = f_info["language"] or "text"

                try:
                    content_bytes = self.github_client.get_blob_content(
                        installation_id=installation.installation_id,
                        owner=repo.owner_login,
                        repo=repo.name,
                        blob_sha=sha,
                    )
                except GitHubApiError as e:
                    logger.warning(f"Failed to fetch content for blob {sha} ({path}): {e}")
                    files_failed += 1
                    continue

                # Content-level security check
                content_decision = self.file_filter.evaluate_content(path, content_bytes)
                if not content_decision.accepted:
                    reason_key = content_decision.reason.value if content_decision.reason else "other"
                    exclusions_count[reason_key] = exclusions_count.get(reason_key, 0) + 1
                    continue

                try:
                    text = content_bytes.decode("utf-8", errors="replace")
                except Exception:
                    files_failed += 1
                    continue

                file_chunks = self.chunker.chunk_file(path, text, language)
                for fc in file_chunks:
                    all_chunks_to_insert.append({
                        "file_path": path,
                        "file_language": language,
                        "chunk_index": fc.chunk_index,
                        "start_line": fc.start_line,
                        "end_line": fc.end_line,
                        "chunk_content": fc.chunk_content,
                        "content_hash": fc.content_hash,
                        "symbol_name": fc.symbol_name,
                        "symbol_type": fc.symbol_type,
                    })

            job.files_failed = files_failed

            # 5. Generate embeddings
            if not self.embedding_provider:
                from app.rag.embeddings.factory import get_embedding_provider
                self.embedding_provider = get_embedding_provider(self.settings)

            job.embedding_provider = "fake" if self.embedding_provider.is_fake else self.settings.EMBEDDING_PROVIDER
            job.embedding_model = self.embedding_provider.model_name
            job.embedding_dimensions = self.embedding_provider.dimensions

            if all_chunks_to_insert:
                texts_to_embed = [c["chunk_content"] for c in all_chunks_to_insert]
                vectors = await self.embedding_provider.embed_texts(texts_to_embed)

                # 6. Delete previous chunks for this repo & commit if re-indexing
                db.query(RepoCodeChunk).filter(
                    RepoCodeChunk.repository_id == repo.id,
                    RepoCodeChunk.commit_sha == commit_sha,
                ).delete(synchronize_session=False)

                # 7. Insert new chunk records
                chunk_models: list[RepoCodeChunk] = []
                for chunk_data, vec in zip(all_chunks_to_insert, vectors, strict=True):
                    chunk_model = RepoCodeChunk(
                        workspace_id=repo.workspace_id,
                        repository_id=repo.id,
                        commit_sha=commit_sha,
                        file_path=chunk_data["file_path"],
                        file_language=chunk_data["file_language"],
                        chunk_index=chunk_data["chunk_index"],
                        start_line=chunk_data["start_line"],
                        end_line=chunk_data["end_line"],
                        chunk_content=chunk_data["chunk_content"],
                        content_hash=chunk_data["content_hash"],
                        symbol_name=chunk_data["symbol_name"],
                        symbol_type=chunk_data["symbol_type"],
                        embedding_model=self.embedding_provider.model_name,
                        embedding_dimensions=self.embedding_provider.dimensions,
                        embedding_vector=vec,
                    )
                    chunk_models.append(chunk_model)

                db.bulk_save_objects(chunk_models)
                job.chunks_count = len(chunk_models)

            # Finalize status
            job.status = "partially_completed" if (is_truncated or files_failed > 0) else "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.exclusions_summary = exclusions_count
            db.commit()
            return job

        except Exception as e:
            logger.error(f"Indexing job {job.id} failed: {e}", exc_info=True)
            job.status = "failed"
            job.error_summary = str(e)
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return job
