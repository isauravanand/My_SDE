import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.github.client import GitHubApiClient, GitHubApiError
from app.models.code_rag import RepoIndexingJob
from app.models.github import GitHubInstallation, GitHubRepository
from app.rag.embeddings.factory import get_embedding_provider
from app.rag.ingestion import RepositoryIngestionService

logger = logging.getLogger(__name__)


async def _run_indexing_in_background(job_id: uuid.UUID) -> None:
    """Async background worker executing repository ingestion in a fresh DB session."""
    db: Session = SessionLocal()
    try:
        settings = get_settings()
        github_client = GitHubApiClient(settings)
        embedding_provider = get_embedding_provider(settings)
        ingestion_service = RepositoryIngestionService(
            github_client=github_client,
            embedding_provider=embedding_provider,
        )
        await ingestion_service.ingest_repository(db, job_id)
    except Exception as e:
        logger.error(f"Error in background indexing job {job_id}: {e}", exc_info=True)
        try:
            job = db.get(RepoIndexingJob, job_id)
            if job and job.status in ("queued", "running"):
                job.status = "failed"
                job.error_summary = f"Background worker exception: {e}"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


class IndexingService:
    """Orchestrator for creating, tracking, and executing repository Code RAG indexing jobs."""

    def __init__(
        self,
        github_client: GitHubApiClient | None = None,
        ingestion_service: RepositoryIngestionService | None = None,
    ):
        self.settings = get_settings()
        self.github_client = github_client or GitHubApiClient(self.settings)
        self.ingestion_service = ingestion_service

    def enqueue_indexing_job(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
        target_ref: str | None = None,
        force_reindex: bool = False,
        run_sync: bool = False,
    ) -> RepoIndexingJob:
        """Create or return an existing indexing job, then trigger execution."""
        # 1. Verify repository
        repo = db.scalar(
            select(GitHubRepository).where(
                GitHubRepository.id == repository_id,
                GitHubRepository.workspace_id == workspace_id,
            )
        )
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found in authorized workspace",
            )

        if not repo.is_selected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository is not selected for this workspace. Please select it in Repositories settings.",
            )

        # 2. Verify installation
        installation = db.scalar(
            select(GitHubInstallation).where(
                GitHubInstallation.id == repo.installation_id,
                GitHubInstallation.workspace_id == workspace_id,
                GitHubInstallation.status == "active",
            )
        )
        if not installation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Active GitHub App installation not found for this repository",
            )

        ref_to_use = target_ref or repo.default_branch or "main"

        # 3. Resolve ref to commit SHA
        try:
            commit_sha = self.github_client.get_ref_commit(
                installation_id=installation.installation_id,
                owner=repo.owner_login,
                repo=repo.name,
                ref=ref_to_use,
            )
        except GitHubApiError as e:
            raise HTTPException(
                status_code=e.status_code if e.status_code < 500 else status.HTTP_502_BAD_GATEWAY,
                detail=f"GitHub error resolving ref '{ref_to_use}': {e.message}",
            ) from e

        # 4. Check for active job (queued / running)
        active_job = db.scalar(
            select(RepoIndexingJob).where(
                RepoIndexingJob.repository_id == repo.id,
                RepoIndexingJob.commit_sha == commit_sha,
                RepoIndexingJob.status.in_(["queued", "running"]),
            )
        )
        if active_job:
            return active_job

        # 5. Check if already completed and not force_reindex
        if not force_reindex:
            existing_completed = db.scalar(
                select(RepoIndexingJob).where(
                    RepoIndexingJob.repository_id == repo.id,
                    RepoIndexingJob.commit_sha == commit_sha,
                    RepoIndexingJob.status == "completed",
                )
            )
            if existing_completed:
                return existing_completed

        # 6. Create new job record
        provider = get_embedding_provider(self.settings)
        new_job = RepoIndexingJob(
            workspace_id=workspace_id,
            repository_id=repo.id,
            target_ref=ref_to_use,
            commit_sha=commit_sha,
            status="queued",
            embedding_provider="fake" if provider.is_fake else self.settings.EMBEDDING_PROVIDER,
            embedding_model=provider.model_name,
            embedding_dimensions=provider.dimensions,
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)

        # 7. Launch execution
        if run_sync:
            # Synchronous execution (useful in tests or CLI)
            ingestion = self.ingestion_service or RepositoryIngestionService(
                github_client=self.github_client,
                embedding_provider=provider,
            )
            # Run async function in current loop or via asyncio.run
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # For pytest or nested loop
                    asyncio.create_task(ingestion.ingest_repository(db, new_job.id))
                else:
                    asyncio.run(ingestion.ingest_repository(db, new_job.id))
            except RuntimeError:
                asyncio.run(ingestion.ingest_repository(db, new_job.id))
            db.refresh(new_job)
        else:
            # Asynchronous background execution
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_run_indexing_in_background(new_job.id))
            except RuntimeError:
                # No running event loop in current thread
                pass

        return new_job

    def get_latest_status(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
    ) -> RepoIndexingJob | None:
        """Fetch the most recent indexing job for a repository."""
        return db.scalar(
            select(RepoIndexingJob)
            .where(
                RepoIndexingJob.repository_id == repository_id,
                RepoIndexingJob.workspace_id == workspace_id,
            )
            .order_by(desc(RepoIndexingJob.created_at))
        )

    def list_jobs(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
        limit: int = 10,
    ) -> list[RepoIndexingJob]:
        """Fetch recent indexing runs for a repository."""
        return list(
            db.scalars(
                select(RepoIndexingJob)
                .where(
                    RepoIndexingJob.repository_id == repository_id,
                    RepoIndexingJob.workspace_id == workspace_id,
                )
                .order_by(desc(RepoIndexingJob.created_at))
                .limit(limit)
            ).all()
        )
