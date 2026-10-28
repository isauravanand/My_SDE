"""Add planning runs and implementation plans tables

Revision ID: 20261020_0005
Revises: 20261020_0004
Create Date: 2026-10-20 14:00:00.000000 UTC

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261020_0005"
down_revision: str | None = "20261020_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. planning_runs
    op.create_table(
        "planning_runs",
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
            "requested_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("base_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
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
    op.create_index("ix_planning_runs_workspace_id", "planning_runs", ["workspace_id"])
    op.create_index("ix_planning_runs_task_id", "planning_runs", ["task_id"])
    op.create_index("ix_planning_runs_repository_id", "planning_runs", ["repository_id"])
    op.create_index("ix_planning_runs_status", "planning_runs", ["status"])
    op.create_index(
        "ix_planning_runs_workspace_task",
        "planning_runs",
        ["workspace_id", "task_id"],
    )
    op.create_index(
        "ix_planning_runs_task_status",
        "planning_runs",
        ["task_id", "status"],
    )

    # 2. implementation_plans
    op.create_table(
        "implementation_plans",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "planning_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("planning_runs.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
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
        sa.Column("schema_version", sa.String(length=32), server_default="mysde.plan.v1", nullable=False),
        sa.Column(
            "plan_data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
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
    op.create_index("ix_implementation_plans_planning_run_id", "implementation_plans", ["planning_run_id"])
    op.create_index("ix_implementation_plans_workspace_id", "implementation_plans", ["workspace_id"])
    op.create_index("ix_implementation_plans_task_id", "implementation_plans", ["task_id"])
    op.create_index(
        "ix_implementation_plans_task_created",
        "implementation_plans",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_implementation_plans_task_created", table_name="implementation_plans")
    op.drop_index("ix_implementation_plans_task_id", table_name="implementation_plans")
    op.drop_index("ix_implementation_plans_workspace_id", table_name="implementation_plans")
    op.drop_index("ix_implementation_plans_planning_run_id", table_name="implementation_plans")
    op.drop_table("implementation_plans")

    op.drop_index("ix_planning_runs_task_status", table_name="planning_runs")
    op.drop_index("ix_planning_runs_workspace_task", table_name="planning_runs")
    op.drop_index("ix_planning_runs_status", table_name="planning_runs")
    op.drop_index("ix_planning_runs_repository_id", table_name="planning_runs")
    op.drop_index("ix_planning_runs_task_id", table_name="planning_runs")
    op.drop_index("ix_planning_runs_workspace_id", table_name="planning_runs")
    op.drop_table("planning_runs")
