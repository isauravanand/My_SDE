import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanResponse(BaseModel):
    """Public subscription plan tier information."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_code: str
    name: str
    description: str | None = None
    price_inr_cents: int
    price_usd_cents: int
    billing_interval: str
    monthly_agent_runs: int
    monthly_repair_runs: int
    monthly_tokens: int
    max_parallel_runs: int
    features: list[str] = Field(default_factory=list)
    is_active: bool


class QuotaUsageSummary(BaseModel):
    """Current billing period usage meters and remaining allowances."""
    agent_runs_used: int
    agent_runs_limit: int
    repair_runs_used: int
    repair_runs_limit: int
    tokens_used: int
    tokens_limit: int
    parallel_runs_active: int
    max_parallel_runs: int
    is_agent_runs_exceeded: bool
    is_repair_runs_exceeded: bool
    period_start: datetime
    period_end: datetime


class SubscriptionResponse(BaseModel):
    """Workspace tenant subscription details and live quota usage."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    status: str
    plan: PlanResponse
    billing_owner_id: uuid.UUID | None = None
    provider: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    cancelled_at: datetime | None = None
    is_in_good_standing: bool
    usage: QuotaUsageSummary


class CreateCheckoutRequest(BaseModel):
    """Request payload to initiate checkout or plan upgrade."""
    plan_code: str = Field(..., description="Target plan code (e.g. pro, team)")
    currency: str = Field(default="INR", description="Currency code (INR, USD)")


class CheckoutResponse(BaseModel):
    """Checkout session reference for frontend payment flow."""
    provider: str
    session_id: str
    checkout_url: str | None = None
    plan_code: str
    amount_cents: int
    currency: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CancelSubscriptionResponse(BaseModel):
    """Response confirming subscription cancellation state."""
    subscription_id: uuid.UUID
    status: str
    cancel_at_period_end: bool
    message: str


class UsageLedgerItemResponse(BaseModel):
    """Auditable usage ledger entry."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    event_type: str
    quantity: int
    run_id: uuid.UUID | None = None
    operation_id: str
    model_name: str | None = None
    token_count: int | None = None
    estimated_cost_usd: float | None = None
    created_at: datetime
