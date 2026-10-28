import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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
    from app.models.github import GitHubRepository
    from app.models.planning import ImplementationPlan
    from app.models.publishing import PublishingRun
    from app.models.repair import RepairRun
    from app.models.task import Task
    from app.models.user import User
    from app.models.workspace import Workspace


class ExecutionRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks an isolated code execution and verification lifecycle run."""

    __tablename__ = "execution_runs"
    __table_args__ = (
        Index("ix_execution_runs_workspace_task", "workspace_id", "task_id"),
        Index("ix_execution_runs_task_status", "task_id", "status"),
        Index("ix_execution_runs_plan", "plan_id"),
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
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("github_repositories.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("implementation_plans.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    base_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="queued",
        index=True,
        nullable=False,
    )  # queued, preparing, awaiting_patch_approval, applying_patch, running_checks, completed, failed, cancel_requested, cancelled, timed_out, cleanup_failed

    sandbox_provider: Mapped[str] = mapped_column(String(32), default="docker", nullable=False)
    sandbox_image: Mapped[str] = mapped_column(String(128), default="python:3.10-slim", nullable=False)
    safe_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleanup_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", lazy="selectin")
    task: Mapped["Task"] = relationship("Task", lazy="selectin")
    repository: Mapped["GitHubRepository | None"] = relationship("GitHubRepository", lazy="selectin")
    plan: Mapped["ImplementationPlan"] = relationship("ImplementationPlan", lazy="selectin")
    requested_by_user: Mapped["User"] = relationship("User", foreign_keys=[requested_by_user_id], lazy="selectin")
    patches: Mapped[list["PatchArtifact"]] = relationship(
        "PatchArtifact",
        back_populates="execution_run",
        cascade="all, delete-orphan",
        order_by="PatchArtifact.created_at.desc()",
        lazy="selectin",
    )
    verification_results: Mapped[list["VerificationResult"]] = relationship(
        "VerificationResult",
        back_populates="execution_run",
        cascade="all, delete-orphan",
        order_by="VerificationResult.created_at.asc()",
        lazy="selectin",
    )
    repair_runs: Mapped[list["RepairRun"]] = relationship(
        "RepairRun",
        back_populates="execution_run",
        cascade="all, delete-orphan",
        order_by="RepairRun.created_at.desc()",
        lazy="selectin",
    )
    publishing_runs: Mapped[list["PublishingRun"]] = relationship(
        "PublishingRun",
        back_populates="execution_run",
        cascade="all, delete-orphan",
        order_by="PublishingRun.created_at.desc()",
        lazy="selectin",
    )


class PatchArtifact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Stores validated unified diff patch proposals and human approval decisions."""

    __tablename__ = "patch_artifacts"
    __table_args__ = (
        Index("ix_patch_artifacts_run", "execution_run_id"),
        Index("ix_patch_artifacts_status", "execution_run_id", "validation_status"),
    )

    execution_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("execution_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    patch_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(32),
        default="valid",
        nullable=False,
    )  # valid, invalid, rejected, applied
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_diff: Mapped[str] = mapped_column(Text, nullable=False)

    changed_files_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    additions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changed_files: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )

    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    execution_run: Mapped["ExecutionRun"] = relationship(
        "ExecutionRun",
        back_populates="patches",
        lazy="selectin",
    )
    approved_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_user_id], lazy="selectin")


class VerificationResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Records the outcome of an approved verification command executed in the sandbox."""

    __tablename__ = "verification_results"
    __table_args__ = (
        Index("ix_verification_results_run", "execution_run_id"),
    )

    execution_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("execution_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    verification_type: Mapped[str] = mapped_column(String(64), nullable=False)  # test, lint, syntax, typecheck
    command_name: Mapped[str] = mapped_column(String(64), nullable=False)
    command_args: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )
    exit_code: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # passed, failed, timed_out, skipped, error
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    stdout_excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stderr_excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Relationships
    execution_run: Mapped["ExecutionRun"] = relationship(
        "ExecutionRun",
        back_populates="verification_results",
        lazy="selectin",
    )
