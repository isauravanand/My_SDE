import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import GUID, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.github import GitHubRepository
    from app.models.workspace import Workspace


class RepoIndexingJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks asynchronous repository ingestion, chunking, and embedding runs."""

    __tablename__ = "repo_indexing_jobs"
    __table_args__ = (
        Index("ix_repo_indexing_jobs_repo_status", "repository_id", "status"),
        Index("ix_repo_indexing_jobs_repo_commit", "repository_id", "commit_sha"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("github_repositories.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    target_ref: Mapped[str] = mapped_column(String(128), default="main", nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="queued",
        index=True,
        nullable=False,
    )  # queued, running, completed, partially_completed, failed, cancelled

    files_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_accepted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_excluded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)

    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusions_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    repository: Mapped["GitHubRepository"] = relationship("GitHubRepository")

    def __repr__(self) -> str:
        return f"<RepoIndexingJob id={self.id} repo_id={self.repository_id} commit={self.commit_sha[:8]} status={self.status}>"


class RepoCodeChunk(Base, UUIDPrimaryKeyMixin):
    """Retrievable code chunk with metadata and dense embedding vector."""

    __tablename__ = "repo_code_chunks"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "commit_sha",
            "content_hash",
            "chunk_index",
            name="uq_chunk_repo_commit_hash_idx",
        ),
        Index("ix_repo_code_chunks_repo_commit", "repository_id", "commit_sha"),
        Index("ix_repo_code_chunks_workspace", "workspace_id"),
        Index("ix_repo_code_chunks_path", "file_path"),
        Index("ix_repo_code_chunks_lang", "file_language"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("github_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_language: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    symbol_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    symbol_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    # Stored as JSON array of floats for maximum compatibility across SQLite and PostgreSQL
    embedding_vector: Mapped[list[float]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    repository: Mapped["GitHubRepository"] = relationship("GitHubRepository")

    def __repr__(self) -> str:
        return f"<RepoCodeChunk id={self.id} path={self.file_path}:{self.start_line}-{self.end_line} symbol={self.symbol_name}>"
