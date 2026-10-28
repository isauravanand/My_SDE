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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import GUID, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.execution import ExecutionRun, PatchArtifact
    from app.models.github import GitHubRepository
    from app.models.task import Task
    from app.models.user import User
    from app.models.workspace import Workspace


class PublishingRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks the Git publishing and GitHub Pull Request creation lifecycle."""

    __tablename__ = "publishing_runs"
    __table_args__ = (
        Index("ix_publishing_runs_workspace_task", "workspace_id", "task_id"),
        Index("ix_publishing_runs_execution_status", "execution_run_id", "status"),
        Index("ix_publishing_runs_idempotency", "idempotency_key", unique=True),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    execution_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("execution_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("github_repositories.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    patch_artifact_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("patch_artifacts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Approval and patch verification binding
    approved_patch_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Status tracking:
    # pending_approval, approved, preparing, pushing_branch, creating_pr, completed, failed, stale_base_conflict
    status: Mapped[str] = mapped_column(String(32), default="pending_approval", index=True, nullable=False)

    # Git branch metadata
    base_branch: Mapped[str] = mapped_column(String(128), default="main", nullable=False)
    base_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    head_branch: Mapped[str] = mapped_column(String(256), nullable=False)
    head_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # GitHub Pull Request metadata
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    pr_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_state: Mapped[str] = mapped_column(String(32), default="open", nullable=False)

    # Error and idempotency tracking
    safe_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Changed files snapshot
    changed_files: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", lazy="selectin")
    task: Mapped["Task"] = relationship("Task", lazy="selectin")
    execution_run: Mapped["ExecutionRun"] = relationship("ExecutionRun", lazy="selectin")
    repository: Mapped["GitHubRepository"] = relationship("GitHubRepository", lazy="selectin")
    patch_artifact: Mapped["PatchArtifact"] = relationship("PatchArtifact", lazy="selectin")
    requested_by_user: Mapped["User"] = relationship("User", foreign_keys=[requested_by_user_id], lazy="selectin")
    approved_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_user_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<PublishingRun id={self.id} status={self.status} pr={self.pr_number}>"
