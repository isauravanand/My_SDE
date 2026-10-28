"""Add publishing_runs table for Git and PR publishing

Revision ID: 20261021_0008
Revises: 20261021_0007
Create Date: 2026-10-21 23:00:00.000000 UTC

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261021_0008"
down_revision: str | None = "20261021_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publishing_runs",
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
            "execution_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("github_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patch_artifact_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("patch_artifacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_patch_hash", sa.String(length=64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_approval"),
        sa.Column("base_branch", sa.String(length=128), nullable=False, server_default="main"),
        sa.Column("base_commit_sha", sa.String(length=40), nullable=False),
        sa.Column("head_branch", sa.String(length=256), nullable=False),
        sa.Column("head_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("pr_url", sa.String(length=512), nullable=True),
        sa.Column("pr_title", sa.String(length=256), nullable=True),
        sa.Column("pr_body", sa.Text(), nullable=True),
        sa.Column("pr_state", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "changed_files",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_publishing_runs_workspace_task", "publishing_runs", ["workspace_id", "task_id"])
    op.create_index("ix_publishing_runs_execution_status", "publishing_runs", ["execution_run_id", "status"])
    op.create_index("ix_publishing_runs_idempotency", "publishing_runs", ["idempotency_key"], unique=True)
    op.create_index("ix_publishing_runs_repository_id", "publishing_runs", ["repository_id"])
    op.create_index("ix_publishing_runs_status", "publishing_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_publishing_runs_status", table_name="publishing_runs")
    op.drop_index("ix_publishing_runs_repository_id", table_name="publishing_runs")
    op.drop_index("ix_publishing_runs_idempotency", table_name="publishing_runs")
    op.drop_index("ix_publishing_runs_execution_status", table_name="publishing_runs")
    op.drop_index("ix_publishing_runs_workspace_task", table_name="publishing_runs")
    op.drop_table("publishing_runs")
