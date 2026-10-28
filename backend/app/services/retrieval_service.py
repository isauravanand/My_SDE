import logging
import re
import uuid
from typing import Any

import numpy as np
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.code_rag import RepoCodeChunk, RepoIndexingJob
from app.models.github import GitHubRepository
from app.rag.embeddings.base import BaseEmbeddingProvider
from app.rag.embeddings.factory import get_embedding_provider

logger = logging.getLogger(__name__)


class RetrievalService:
    """Retrieval-Augmented Generation search service over indexed repository code chunks."""

    def __init__(
        self,
        embedding_provider: BaseEmbeddingProvider | None = None,
    ):
        self.settings = get_settings()
        self.embedding_provider = embedding_provider

    async def retrieve_chunks(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
        query: str,
        commit_sha: str | None = None,
        top_k: int = 5,
        file_path_pattern: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Perform semantic and lexical hybrid code retrieval for an authorized repository."""
        # 1. Verify repository ownership & selection
        repo = db.scalar(
            select(GitHubRepository).where(
                GitHubRepository.id == repository_id,
                GitHubRepository.workspace_id == workspace_id,
            )
        )
        if not repo:
            raise ValueError("Repository not found in authorized workspace")

        clean_query = query.strip()
        if not clean_query:
            return {
                "repository_id": str(repo.id),
                "repository_name": repo.full_name,
                "commit_sha": commit_sha or "",
                "is_indexed": True,
                "results": [],
                "total_results": 0,
            }

        # 2. Resolve commit SHA to search
        if not commit_sha:
            # Find the most recently completed indexing job
            latest_job = db.scalar(
                select(RepoIndexingJob).where(
                    RepoIndexingJob.repository_id == repo.id,
                    RepoIndexingJob.workspace_id == workspace_id,
                    RepoIndexingJob.status.in_(["completed", "partially_completed"]),
                ).order_by(desc(RepoIndexingJob.completed_at))
            )
            if not latest_job:
                return {
                    "repository_id": str(repo.id),
                    "repository_name": repo.full_name,
                    "commit_sha": "",
                    "is_indexed": False,
                    "message": "Repository has not been indexed yet. Please trigger an indexing job first.",
                    "results": [],
                    "total_results": 0,
                }
            target_commit = latest_job.commit_sha
        else:
            target_commit = commit_sha

        # 3. Query candidate code chunks
        chunk_query = select(RepoCodeChunk).where(
            RepoCodeChunk.repository_id == repo.id,
            RepoCodeChunk.workspace_id == workspace_id,
            RepoCodeChunk.commit_sha == target_commit,
        )

        if language:
            chunk_query = chunk_query.where(RepoCodeChunk.file_language == language.lower())

        if file_path_pattern:
            clean_pat = file_path_pattern.strip().replace("*", "%")
            chunk_query = chunk_query.where(RepoCodeChunk.file_path.ilike(f"%{clean_pat}%"))

        candidate_chunks: list[RepoCodeChunk] = list(db.scalars(chunk_query).all())

        if not candidate_chunks:
            return {
                "repository_id": str(repo.id),
                "repository_name": repo.full_name,
                "commit_sha": target_commit,
                "is_indexed": True,
                "results": [],
                "total_results": 0,
            }

        # 4. Generate embedding for query
        if not self.embedding_provider:
            self.embedding_provider = get_embedding_provider(self.settings)

        # Check model compatibility
        first_chunk = candidate_chunks[0]
        if (
            first_chunk.embedding_model != self.embedding_provider.model_name
            or first_chunk.embedding_dimensions != self.embedding_provider.dimensions
        ):
            logger.warning(
                f"Embedding model mismatch: stored chunks use '{first_chunk.embedding_model}' "
                f"({first_chunk.embedding_dimensions}d), but current provider is "
                f"'{self.embedding_provider.model_name}' ({self.embedding_provider.dimensions}d)."
            )

        query_vector = await self.embedding_provider.embed_query(clean_query)

        # Check dimension alignment
        if first_chunk.embedding_dimensions != len(query_vector):
            return {
                "repository_id": str(repo.id),
                "repository_name": repo.full_name,
                "commit_sha": target_commit,
                "is_indexed": False,
                "message": (
                    f"Embedding model dimension mismatch (stored {first_chunk.embedding_dimensions}d vs current {len(query_vector)}d). "
                    "Please re-index the repository with the current model."
                ),
                "results": [],
                "total_results": 0,
            }

        # 5. Compute vector cosine similarity using numpy
        chunk_vectors = np.array([c.embedding_vector for c in candidate_chunks], dtype=np.float32)
        q_vec = np.array(query_vector, dtype=np.float32)

        # Normalize query vector if needed
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        # Matrix dot product (both already unit-normalized)
        cosine_sims = np.dot(chunk_vectors, q_vec)

        # 6. Hybrid scoring with lexical boost
        query_terms = set(re.findall(r"\w+", clean_query.lower()))
        scored_items: list[dict[str, Any]] = []

        safe_top_k = min(max(1, top_k), 25)

        for idx, chunk in enumerate(candidate_chunks):
            cos_score = float(cosine_sims[idx])

            # Lexical term overlap
            content_lower = chunk.chunk_content.lower()
            path_lower = chunk.file_path.lower()
            sym_lower = (chunk.symbol_name or "").lower()

            term_matches = sum(1 for t in query_terms if t in content_lower or t in path_lower)
            lexical_ratio = (term_matches / len(query_terms)) if query_terms else 0.0

            symbol_boost = 0.15 if any(t in sym_lower for t in query_terms) else 0.0
            path_boost = 0.10 if any(t in path_lower for t in query_terms) else 0.0

            # Composite hybrid score (0.0 to 1.0)
            hybrid_score = (cos_score * 0.70) + (lexical_ratio * 0.20) + symbol_boost + path_boost
            clamped_score = max(0.0, min(1.0, hybrid_score))

            github_url = (
                f"https://github.com/{repo.owner_login}/{repo.name}/blob/"
                f"{target_commit}/{chunk.file_path}#L{chunk.start_line}-L{chunk.end_line}"
            )

            scored_items.append({
                "chunk_id": str(chunk.id),
                "file_path": chunk.file_path,
                "file_language": chunk.file_language,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "symbol_name": chunk.symbol_name,
                "symbol_type": chunk.symbol_type,
                "chunk_content": chunk.chunk_content,
                "score": round(clamped_score, 4),
                "commit_sha": chunk.commit_sha,
                "github_url": github_url,
            })

        # 7. Deterministic sorting: score DESC, file_path ASC, start_line ASC
        scored_items.sort(key=lambda x: (-x["score"], x["file_path"], x["start_line"]))

        # 8. Deduplicate overlapping line chunks from same file
        deduped_results: list[dict[str, Any]] = []
        covered_ranges: dict[str, list[tuple[int, int]]] = {}

        for item in scored_items:
            path = item["file_path"]
            start, end = item["start_line"], item["end_line"]

            ranges = covered_ranges.setdefault(path, [])
            # Check overlap > 50%
            is_redundant = False
            for existing_start, existing_end in ranges:
                overlap = max(0, min(end, existing_end) - max(start, existing_start))
                length = end - start + 1
                if length > 0 and (overlap / length) > 0.5:
                    is_redundant = True
                    break

            if not is_redundant:
                ranges.append((start, end))
                deduped_results.append(item)
                if len(deduped_results) >= safe_top_k:
                    break

        return {
            "repository_id": str(repo.id),
            "repository_name": repo.full_name,
            "commit_sha": target_commit,
            "is_indexed": True,
            "results": deduped_results,
            "total_results": len(deduped_results),
        }
