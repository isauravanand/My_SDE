"""Add billing, subscription plans, usage ledger, and webhook processing tables

Revision ID: 20261022_0009
Revises: 20261021_0008
Create Date: 2026-10-22 11:00:00.000000 UTC

"""
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261022_0009"
down_revision: str | None = "20261021_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create subscription_plans table
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("plan_code", sa.String(32), unique=True, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_inr_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("price_usd_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("billing_interval", sa.String(16), server_default="monthly", nullable=False),
        sa.Column("monthly_agent_runs", sa.Integer(), server_default="15", nullable=False),
        sa.Column("monthly_repair_runs", sa.Integer(), server_default="5", nullable=False),
        sa.Column("monthly_tokens", sa.Integer(), server_default="250000", nullable=False),
        sa.Column("max_parallel_runs", sa.Integer(), server_default="1", nullable=False),
        sa.Column("features", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_subscription_plans_code", "subscription_plans", ["plan_code"])
    op.create_index("ix_subscription_plans_active", "subscription_plans", ["is_active"])

    # 2. Create subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "billing_owner_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("provider", sa.String(32), server_default="mock", nullable=False),
        sa.Column("provider_customer_id", sa.String(128), nullable=True),
        sa.Column("provider_subscription_id", sa.String(128), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_provider_sub", "subscriptions", ["provider_subscription_id"])

    # 3. Create usage_ledger_entries table
    op.create_table(
        "usage_ledger_entries",
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
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("operation_id", sa.String(128), nullable=False),
        sa.Column("model_name", sa.String(64), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("operation_id", "event_type", name="uq_usage_ledger_operation_event"),
    )
    op.create_index("ix_usage_ledger_workspace_created", "usage_ledger_entries", ["workspace_id", "created_at"])
    op.create_index("ix_usage_ledger_workspace_event", "usage_ledger_entries", ["workspace_id", "event_type"])

    # 4. Create processed_webhook_events table
    op.create_table(
        "processed_webhook_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(128), unique=True, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="processed", nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_processed_webhook_events_provider_event", "processed_webhook_events", ["provider", "event_id"])

    # 5. Seed Initial Plans (Free, Pro, Team)
    plans_table = sa.table(
        "subscription_plans",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("plan_code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("price_inr_cents", sa.Integer),
        sa.column("price_usd_cents", sa.Integer),
        sa.column("billing_interval", sa.String),
        sa.column("monthly_agent_runs", sa.Integer),
        sa.column("monthly_repair_runs", sa.Integer),
        sa.column("monthly_tokens", sa.Integer),
        sa.column("max_parallel_runs", sa.Integer),
        sa.column("features", sa.JSON),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    free_plan_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    pro_plan_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    team_plan_id = uuid.UUID("00000000-0000-0000-0000-000000000003")

    now = datetime.now(timezone.utc)

    op.bulk_insert(
        plans_table,
        [
            {
                "id": free_plan_id,
                "plan_code": "free",
                "name": "Free Starter",
                "description": "Essential automated code investigation and sandbox checks for individuals.",
                "price_inr_cents": 0,
                "price_usd_cents": 0,
                "billing_interval": "monthly",
                "monthly_agent_runs": 15,
                "monthly_repair_runs": 5,
                "monthly_tokens": 250000,
                "max_parallel_runs": 1,
                "features": ["code_rag", "sandbox_verification", "pull_request_publishing"],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": pro_plan_id,
                "plan_code": "pro",
                "name": "Professional",
                "description": "High-volume autonomous engineering, self-healing repairs, and priority sandbox execution.",
                "price_inr_cents": 249900,  # ₹2,499 / mo
                "price_usd_cents": 2900,    # $29 / mo
                "billing_interval": "monthly",
                "monthly_agent_runs": 100,
                "monthly_repair_runs": 50,
                "monthly_tokens": 2000000,
                "max_parallel_runs": 3,
                "features": [
                    "code_rag",
                    "sandbox_verification",
                    "automated_repair",
                    "pull_request_publishing",
                    "priority_sandboxes",
                ],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": team_plan_id,
                "plan_code": "team",
                "name": "Team Scale",
                "description": "Comprehensive engineering platform with high concurrency, extended budgets, and team collaboration.",
                "price_inr_cents": 799900,  # ₹7,999 / mo
                "price_usd_cents": 9900,    # $99 / mo
                "billing_interval": "monthly",
                "monthly_agent_runs": 500,
                "monthly_repair_runs": 250,
                "monthly_tokens": 10000000,
                "max_parallel_runs": 10,
                "features": [
                    "code_rag",
                    "sandbox_verification",
                    "automated_repair",
                    "pull_request_publishing",
                    "priority_sandboxes",
                    "team_seat_management",
                    "audit_ledger_export",
                ],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("processed_webhook_events")
    op.drop_table("usage_ledger_entries")
    op.drop_table("subscriptions")
    op.drop_table("subscription_plans")
