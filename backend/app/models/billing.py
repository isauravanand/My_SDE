import uuid
from datetime import datetime, timezone
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import GUID, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class SubscriptionPlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Database-backed subscription plan tiers and quotas."""

    __tablename__ = "subscription_plans"

    plan_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_inr_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 249900 = ₹2,499.00
    price_usd_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 2900 = $29.00
    billing_interval: Mapped[str] = mapped_column(String(16), default="monthly", nullable=False)

    monthly_agent_runs: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    monthly_repair_runs: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    monthly_tokens: Mapped[int] = mapped_column(Integer, default=250000, nullable=False)
    max_parallel_runs: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    features: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="plan", cascade="all"
    )

    def __repr__(self) -> str:
        return f"<SubscriptionPlan code={self.plan_code} name={self.name}>"


class Subscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Active subscription status, billing period, and provider links for a workspace tenant."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_status", "status"),
        Index("ix_subscriptions_provider_sub", "provider_subscription_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    billing_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        nullable=False,
    )  # active, trialing, past_due, cancelled, expired, paused

    provider: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)  # mock, razorpay
    provider_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )

    # Relationships
    plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan", back_populates="subscriptions", lazy="selectin")
    workspace: Mapped["Workspace"] = relationship("Workspace", lazy="selectin")
    billing_owner: Mapped["User | None"] = relationship("User", lazy="selectin")

    @property
    def is_in_good_standing(self) -> bool:
        """Return True if subscription is actively entitled to use quotas."""
        now = datetime.now(timezone.utc)
        if self.status in ("active", "trialing"):
            return True
        if self.status == "past_due":
            # Grace period: allow 3 days past period end
            return now <= (self.current_period_end if self.current_period_end.tzinfo else self.current_period_end.replace(tzinfo=timezone.utc))
        return False

    def __repr__(self) -> str:
        return f"<Subscription workspace_id={self.workspace_id} status={self.status}>"


class UsageLedgerEntry(Base, UUIDPrimaryKeyMixin):
    """Immutable, append-only auditable ledger of all billable operational events."""

    __tablename__ = "usage_ledger_entries"
    __table_args__ = (
        UniqueConstraint("operation_id", "event_type", name="uq_usage_ledger_operation_event"),
        Index("ix_usage_ledger_workspace_created", "workspace_id", "created_at"),
        Index("ix_usage_ledger_workspace_event", "workspace_id", "event_type"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )  # agent_run_started, agent_run_completed, repair_run_started, repair_run_completed, model_token_usage
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    run_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), index=True, nullable=True)
    operation_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", lazy="selectin")
    user: Mapped["User | None"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<UsageLedgerEntry event={self.event_type} qty={self.quantity} op={self.operation_id}>"


class ProcessedWebhookEvent(Base, UUIDPrimaryKeyMixin):
    """Idempotency tracking log for verified payment and subscription webhooks."""

    __tablename__ = "processed_webhook_events"
    __table_args__ = (
        Index("ix_processed_webhook_events_provider_event", "provider", "event_id"),
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # razorpay, mock
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="processed", nullable=False)  # processed, ignored, failed
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ProcessedWebhookEvent provider={self.provider} event_id={self.event_id} status={self.status}>"
