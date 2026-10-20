"""Add GitHub App integration models and repository references

Revision ID: 20261019_0003
Revises: 20261019_0002
Create Date: 2026-10-19 20:20:00.000000 UTC

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261019_0003"
down_revision: str | None = "20261019_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. github_installations
    op.create_table(
        "github_installations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=64), server_default="User", nullable=False),
        sa.Column("account_avatar_url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("permissions_json", sa.Text(), nullable=True),
        sa.Column("uninstalled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", name="uq_workspace_github_installation"),
    )
    op.create_index("ix_github_installations_workspace_id", "github_installations", ["workspace_id"], unique=False)
    op.create_index("ix_github_installations_installation_id", "github_installations", ["installation_id"], unique=True)
    op.create_index("ix_github_installations_status", "github_installations", ["status"], unique=False)

    # 2. github_repositories
    op.create_table(
        "github_repositories",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "installation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("github_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_login", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("default_branch", sa.String(length=128), server_default="main", nullable=False),
        sa.Column("is_private", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", "github_repo_id", name="uq_workspace_github_repo_id"),
    )
    op.create_index("ix_github_repositories_workspace_id", "github_repositories", ["workspace_id"], unique=False)
    op.create_index("ix_github_repositories_installation_id", "github_repositories", ["installation_id"], unique=False)
    op.create_index("ix_github_repositories_github_repo_id", "github_repositories", ["github_repo_id"], unique=False)
    op.create_index("ix_github_repositories_full_name", "github_repositories", ["full_name"], unique=False)
    op.create_index("ix_github_repositories_is_selected", "github_repositories", ["is_selected"], unique=False)

    # 3. github_oauth_states
    op.create_table(
        "github_oauth_states",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state_token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_github_oauth_states_workspace_id", "github_oauth_states", ["workspace_id"], unique=False)
    op.create_index("ix_github_oauth_states_user_id", "github_oauth_states", ["user_id"], unique=False)
    op.create_index("ix_github_oauth_states_state_token", "github_oauth_states", ["state_token"], unique=True)
    op.create_index("ix_github_oauth_states_expires_at", "github_oauth_states", ["expires_at"], unique=False)

    # 4. github_webhook_deliveries
    op.create_table(
        "github_webhook_deliveries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("delivery_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="processed", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_github_webhook_deliveries_delivery_id", "github_webhook_deliveries", ["delivery_id"], unique=True)

    # 5. Add repository_id to projects
    op.add_column(
        "projects",
        sa.Column(
            "repository_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("github_repositories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_projects_repository_id", "projects", ["repository_id"], unique=False)

    # 6. Add repository and issue reference fields to tasks
    op.add_column(
        "tasks",
        sa.Column(
            "repository_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("github_repositories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("tasks", sa.Column("github_issue_number", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("github_issue_url", sa.String(length=512), nullable=True))
    op.add_column("tasks", sa.Column("github_issue_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_tasks_repository_id", "tasks", ["repository_id"], unique=False)
    op.create_index("ix_tasks_github_issue_id", "tasks", ["github_issue_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tasks_github_issue_id", table_name="tasks")
    op.drop_index("ix_tasks_repository_id", table_name="tasks")
    op.drop_column("tasks", "github_issue_id")
    op.drop_column("tasks", "github_issue_url")
    op.drop_column("tasks", "github_issue_number")
    op.drop_column("tasks", "repository_id")

    op.drop_index("ix_projects_repository_id", table_name="projects")
    op.drop_column("projects", "repository_id")

    op.drop_table("github_webhook_deliveries")
    op.drop_table("github_oauth_states")
    op.drop_table("github_repositories")
    op.drop_table("github_installations")
