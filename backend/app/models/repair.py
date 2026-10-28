import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Float,
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
    from app.models.execution import ExecutionRun
    from app.models.task import Task
    from app.models.user import User
    from app.models.workspace import Workspace


class RepairRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks a bounded AI repair lifecycle run for a failed execution."""

    __tablename__ = "repair_runs"
    __table_args__ = (
        Index("ix_repair_runs_execution_status", "execution_run_id", "status"),
        Index("ix_repair_runs_workspace_task", "workspace_id", "task_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    execution_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("execution_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="queued",
        index=True,
        nullable=False,
    )  # queued, analyzing, repairing, running_checks, completed, failed, budget_exhausted, non_repairable, cancelled

    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    consumed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_model_calls: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    consumed_model_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    final_outcome: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )  # passed, failed, partially_verified, repair_exhausted, infrastructure_failure, cancelled, non_repairable

    safe_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", lazy="selectin")
    task: Mapped["Task"] = relationship("Task", lazy="selectin")
    execution_run: Mapped["ExecutionRun"] = relationship(
        "ExecutionRun",
        back_populates="repair_runs",
        lazy="selectin",
    )
    requested_by_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[requested_by_user_id],
        lazy="selectin",
    )
    attempts: Mapped[list["RepairAttempt"]] = relationship(
        "RepairAttempt",
        back_populates="repair_run",
        cascade="all, delete-orphan",
        order_by="RepairAttempt.attempt_number.asc()",
        lazy="selectin",
    )


class RepairAttempt(Base, UUIDPrimaryKeyMixin):
    """Records an individual repair attempt with failure classification and outcome."""

    __tablename__ = "repair_attempts"
    __table_args__ = (
        UniqueConstraint("repair_run_id", "attempt_number", name="uq_repair_attempt_run_number"),
        Index("ix_repair_attempts_run_attempt", "repair_run_id", "attempt_number"),
    )

    repair_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("repair_runs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    failure_classification: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )
    evidence_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )

    root_cause_hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
    )  # pending, valid, invalid, rejected, applied, failed
    proposed_change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    patch_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    application_result: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )  # success, failed, skipped
    verification_results_summary: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    repair_run: Mapped["RepairRun"] = relationship(
        "RepairRun",
        back_populates="attempts",
        lazy="selectin",
    )
