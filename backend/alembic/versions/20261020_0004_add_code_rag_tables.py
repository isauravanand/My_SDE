"""Add Code RAG indexing jobs and code chunks tables

Revision ID: 20261020_0004
Revises: 20261019_0003
Create Date: 2026-10-20 13:30:00.000000 UTC

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261020_0004"
down_revision: str | None = "20261019_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. repo_indexing_jobs
    op.create_table(
        "repo_indexing_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("github_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_ref", sa.String(length=128), server_default="main", nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("files_discovered", sa.Integer(), server_default="0", nullable=False),
        sa.Column("files_accepted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("files_excluded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("files_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunks_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "exclusions_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("ix_repo_indexing_jobs_workspace_id", "repo_indexing_jobs", ["workspace_id"])
    op.create_index("ix_repo_indexing_jobs_repository_id", "repo_indexing_jobs", ["repository_id"])
    op.create_index("ix_repo_indexing_jobs_commit_sha", "repo_indexing_jobs", ["commit_sha"])
    op.create_index("ix_repo_indexing_jobs_status", "repo_indexing_jobs", ["status"])
    op.create_index(
        "ix_repo_indexing_jobs_repo_status",
        "repo_indexing_jobs",
        ["repository_id", "status"],
    )
    op.create_index(
        "ix_repo_indexing_jobs_repo_commit",
        "repo_indexing_jobs",
        ["repository_id", "commit_sha"],
    )

    # 2. repo_code_chunks
    op.create_table(
        "repo_code_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("github_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("file_language", sa.String(length=64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("chunk_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("symbol_name", sa.String(length=255), nullable=True),
        sa.Column("symbol_type", sa.String(length=64), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "embedding_vector",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "repository_id",
            "commit_sha",
            "content_hash",
            "chunk_index",
            name="uq_chunk_repo_commit_hash_idx",
        ),
    )
    op.create_index("ix_repo_code_chunks_workspace", "repo_code_chunks", ["workspace_id"])
    op.create_index(
        "ix_repo_code_chunks_repo_commit",
        "repo_code_chunks",
        ["repository_id", "commit_sha"],
    )
    op.create_index("ix_repo_code_chunks_commit_sha", "repo_code_chunks", ["commit_sha"])
    op.create_index("ix_repo_code_chunks_path", "repo_code_chunks", ["file_path"])
    op.create_index("ix_repo_code_chunks_lang", "repo_code_chunks", ["file_language"])
    op.create_index("ix_repo_code_chunks_content_hash", "repo_code_chunks", ["content_hash"])


def downgrade() -> None:
    op.drop_table("repo_code_chunks")
    op.drop_table("repo_indexing_jobs")
