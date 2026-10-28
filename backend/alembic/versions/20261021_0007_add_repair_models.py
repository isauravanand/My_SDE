"""Add repair runs and repair attempts tables

Revision ID: 20261021_0007
Revises: 20261021_0006
Create Date: 2026-10-21 16:00:00.000000 UTC

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261021_0007"
down_revision: str | None = "20261021_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. repair_runs
    op.create_table(
        "repair_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "execution_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("consumed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_model_calls", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("consumed_model_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_outcome", sa.String(length=32), nullable=True),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_repair_runs_execution_status",
        "repair_runs",
        ["execution_run_id", "status"],
    )
    op.create_index(
        "ix_repair_runs_workspace_task",
        "repair_runs",
        ["workspace_id", "task_id"],
    )
    op.create_index(
        "ix_repair_runs_execution_run_id",
        "repair_runs",
        ["execution_run_id"],
    )
    op.create_index(
        "ix_repair_runs_status",
        "repair_runs",
        ["status"],
    )

    # 2. repair_attempts
    op.create_table(
        "repair_attempts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "repair_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("repair_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "failure_classification",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "evidence_references",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=False,
        ),
        sa.Column("root_cause_hypothesis", sa.Text(), nullable=True),
        sa.Column("proposal_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("proposed_change_summary", sa.Text(), nullable=True),
        sa.Column("patch_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "validation_result",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=True,
        ),
        sa.Column("application_result", sa.String(length=32), nullable=True),
        sa.Column(
            "verification_results_summary",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=True,
        ),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("repair_run_id", "attempt_number", name="uq_repair_attempt_run_number"),
    )
    op.create_index(
        "ix_repair_attempts_run_attempt",
        "repair_attempts",
        ["repair_run_id", "attempt_number"],
    )
    op.create_index(
        "ix_repair_attempts_repair_run_id",
        "repair_attempts",
        ["repair_run_id"],
    )


def downgrade() -> None:
    op.drop_table("repair_attempts")
    op.drop_table("repair_runs")
