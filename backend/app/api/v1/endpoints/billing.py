import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_workspace_membership, require_role, validate_csrf
from app.db.session import get_db
from app.models.billing import SubscriptionPlan, UsageLedgerEntry
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.billing import (
    CancelSubscriptionResponse,
    CheckoutResponse,
    CreateCheckoutRequest,
    PlanResponse,
    SubscriptionResponse,
    UsageLedgerItemResponse,
)
from app.services.billing_service import BillingService

router = APIRouter(prefix="/billing", tags=["SaaS Billing & Subscriptions"])


@router.get(
    "/plans",
    response_model=list[PlanResponse],
    summary="List available subscription plans and feature matrix",
)
def list_subscription_plans(
    db: Session = Depends(get_db),
):
    """Returns active subscription plans with quotas, concurrency limits, and prices."""
    service = BillingService(db)
    service.ensure_default_plans()
    plans = db.scalars(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active == True)  # noqa: E712
        .order_by(SubscriptionPlan.price_inr_cents.asc())
    ).all()
    return plans


@router.get(
    "/subscription",
    response_model=SubscriptionResponse,
    summary="Get active subscription status and live quota consumption",
)
def get_workspace_subscription(
    workspace_id: uuid.UUID = Query(..., description="Target workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    workspace_membership: tuple[Workspace, WorkspaceMembership] = Depends(get_workspace_membership),
):
    """Returns active subscription details, renewal periods, and live billing quota usage."""
    service = BillingService(db)
    sub = service.get_or_create_workspace_subscription(workspace_id, owner_id=current_user.id)
    usage = service.get_workspace_quota_usage(workspace_id)

    return SubscriptionResponse(
        id=sub.id,
        workspace_id=sub.workspace_id,
        status=sub.status,
        plan=PlanResponse.model_validate(sub.plan),
        billing_owner_id=sub.billing_owner_id,
        provider=sub.provider,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        cancel_at_period_end=sub.cancel_at_period_end,
        cancelled_at=sub.cancelled_at,
        is_in_good_standing=sub.is_in_good_standing,
        usage=usage,
    )


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    summary="Initiate subscription checkout session or upgrade",
    dependencies=[Depends(validate_csrf)],
)
def create_checkout_session(
    payload: CreateCheckoutRequest,
    workspace_id: uuid.UUID = Query(..., description="Target workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    workspace_membership: tuple[Workspace, WorkspaceMembership] = Depends(require_role(["owner", "admin"])),
):
    """Initiates checkout or upgrade session via configured payment provider."""
    service = BillingService(db)
    result = service.create_checkout_session(
        workspace_id=workspace_id,
        user=current_user,
        plan_code=payload.plan_code,
        currency=payload.currency,
    )
    return CheckoutResponse(
        provider=result.provider,
        session_id=result.session_id,
        checkout_url=result.checkout_url,
        plan_code=result.plan_code,
        amount_cents=result.amount_cents,
        currency=result.currency,
        metadata=result.metadata,
    )


@router.post(
    "/cancel",
    response_model=CancelSubscriptionResponse,
    summary="Request subscription cancellation at the end of the billing cycle",
    dependencies=[Depends(validate_csrf)],
)
def cancel_subscription(
    workspace_id: uuid.UUID = Query(..., description="Target workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    workspace_membership: tuple[Workspace, WorkspaceMembership] = Depends(require_role(["owner", "admin"])),
):
    """Schedules subscription cancellation at the end of the active billing cycle."""
    service = BillingService(db)
    sub = service.cancel_workspace_subscription(workspace_id, current_user.id)
    return CancelSubscriptionResponse(
        subscription_id=sub.id,
        status=sub.status,
        cancel_at_period_end=sub.cancel_at_period_end,
        message="Subscription will cancel at the end of the current billing cycle.",
    )


@router.get(
    "/usage",
    response_model=list[UsageLedgerItemResponse],
    summary="List workspace usage ledger entries",
)
def get_workspace_usage_history(
    workspace_id: uuid.UUID = Query(..., description="Target workspace ID"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    workspace_membership: tuple[Workspace, WorkspaceMembership] = Depends(get_workspace_membership),
):
    """Returns historical ledger entries recording billable agent runs, repairs, and model calls."""
    entries = db.scalars(
        select(UsageLedgerEntry)
        .where(UsageLedgerEntry.workspace_id == workspace_id)
        .order_by(UsageLedgerEntry.created_at.desc())
        .limit(limit)
    ).all()
    return entries


@router.post(
    "/webhooks/{provider}",
    summary="Receive and verify payment provider webhooks",
    status_code=status.HTTP_200_OK,
)
async def receive_billing_webhook(
    provider: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public webhook receiver verifying HMAC signatures against raw request body
    and executing idempotent subscription state transitions.
    """
    raw_body = await request.body()
    headers = dict(request.headers)

    service = BillingService(db)
    result = service.process_webhook_event(
        provider_name=provider.lower(),
        raw_body=raw_body,
        headers=headers,
    )
    return result
