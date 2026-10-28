"""Add execution runs, patch artifacts, and verification results tables

Revision ID: 20261021_0006
Revises: 20261020_0005
Create Date: 2026-10-21 15:00:00.000000 UTC

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261021_0006"
down_revision: str | None = "20261020_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. execution_runs
    op.create_table(
        "execution_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("github_repositories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "plan_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("implementation_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("base_commit_sha", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("sandbox_provider", sa.String(length=32), server_default="docker", nullable=False),
        sa.Column("sandbox_image", sa.String(length=128), server_default="python:3.10-slim", nullable=False),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.Column("cleanup_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_execution_runs_workspace_id", "execution_runs", ["workspace_id"])
    op.create_index("ix_execution_runs_task_id", "execution_runs", ["task_id"])
    op.create_index("ix_execution_runs_repository_id", "execution_runs", ["repository_id"])
    op.create_index("ix_execution_runs_plan_id", "execution_runs", ["plan_id"])
    op.create_index("ix_execution_runs_status", "execution_runs", ["status"])
    op.create_index(
        "ix_execution_runs_workspace_task",
        "execution_runs",
        ["workspace_id", "task_id"],
    )
    op.create_index(
        "ix_execution_runs_task_status",
        "execution_runs",
        ["task_id", "status"],
    )

    # 2. patch_artifacts
    op.create_table(
        "patch_artifacts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "execution_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("patch_hash", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=32), server_default="valid", nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("raw_diff", sa.Text(), nullable=False),
        sa.Column("changed_files_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("additions_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deletions_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "changed_files",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("is_approved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "approved_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_patch_artifacts_execution_run_id", "patch_artifacts", ["execution_run_id"])
    op.create_index(
        "ix_patch_artifacts_status",
        "patch_artifacts",
        ["execution_run_id", "validation_status"],
    )

    # 3. verification_results
    op.create_table(
        "verification_results",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "execution_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("verification_type", sa.String(length=64), nullable=False),
        sa.Column("command_name", sa.String(length=64), nullable=False),
        sa.Column(
            "command_args",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("exit_code", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_seconds", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("stdout_excerpt", sa.Text(), server_default="", nullable=False),
        sa.Column("stderr_excerpt", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_verification_results_execution_run_id", "verification_results", ["execution_run_id"])


def downgrade() -> None:
    op.drop_index("ix_verification_results_execution_run_id", table_name="verification_results")
    op.drop_table("verification_results")

    op.drop_index("ix_patch_artifacts_status", table_name="patch_artifacts")
    op.drop_index("ix_patch_artifacts_execution_run_id", table_name="patch_artifacts")
    op.drop_table("patch_artifacts")

    op.drop_index("ix_execution_runs_task_status", table_name="execution_runs")
    op.drop_index("ix_execution_runs_workspace_task", table_name="execution_runs")
    op.drop_index("ix_execution_runs_status", table_name="execution_runs")
    op.drop_index("ix_execution_runs_plan_id", table_name="execution_runs")
    op.drop_index("ix_execution_runs_repository_id", table_name="execution_runs")
    op.drop_index("ix_execution_runs_task_id", table_name="execution_runs")
    op.drop_index("ix_execution_runs_workspace_id", table_name="execution_runs")
    op.drop_table("execution_runs")
