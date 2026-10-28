import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.base import CheckoutSessionResult
from app.billing.factory import get_billing_provider
from app.core.config import get_settings
from app.core.logging import redact_sensitive_data
from app.models.billing import (
    ProcessedWebhookEvent,
    Subscription,
    SubscriptionPlan,
    UsageLedgerEntry,
)
from app.models.execution import ExecutionRun
from app.models.user import User
from app.schemas.billing import QuotaUsageSummary

logger = logging.getLogger(__name__)

ACTIVE_RUN_STATUSES = ("queued", "preparing", "applying_patch", "running_checks")


class QuotaExceededError(HTTPException):
    """Raised when a workspace exceeds its plan quota or concurrency allowance."""

    def __init__(
        self,
        message: str,
        quota_type: str = "agent_runs",
        limit: int = 0,
        used: int = 0,
        status_code: int = status.HTTP_402_PAYMENT_REQUIRED,
    ):
        super().__init__(
            status_code=status_code,
            detail={
                "code": "QUOTA_EXCEEDED",
                "message": message,
                "quota_type": quota_type,
                "limit": limit,
                "used": used,
                "upgrade_url": "/billing",
            },
        )


DEFAULT_PLANS_DATA = [
    {
        "plan_code": "free",
        "name": "Free Starter",
        "description": "Ideal for solo developers evaluating MySDE on open-source repos",
        "price_inr_cents": 0,
        "price_usd_cents": 0,
        "billing_interval": "monthly",
        "monthly_agent_runs": 15,
        "monthly_repair_runs": 5,
        "monthly_tokens": 250000,
        "max_parallel_runs": 1,
        "features": ["code_rag", "sandbox_verification", "pull_request_publishing"],
        "is_active": True,
    },
    {
        "plan_code": "pro",
        "name": "Professional",
        "description": "For active developers shipping production software daily",
        "price_inr_cents": 249900,
        "price_usd_cents": 2900,
        "billing_interval": "monthly",
        "monthly_agent_runs": 100,
        "monthly_repair_runs": 50,
        "monthly_tokens": 2000000,
        "max_parallel_runs": 3,
        "features": ["code_rag", "sandbox_verification", "pull_request_publishing", "automated_repair_loop", "priority_queue"],
        "is_active": True,
    },
    {
        "plan_code": "team",
        "name": "Team Scale",
        "description": "For high-velocity engineering teams requiring concurrent multi-agent runs",
        "price_inr_cents": 799900,
        "price_usd_cents": 9900,
        "billing_interval": "monthly",
        "monthly_agent_runs": 500,
        "monthly_repair_runs": 250,
        "monthly_tokens": 10000000,
        "max_parallel_runs": 10,
        "features": ["code_rag", "sandbox_verification", "pull_request_publishing", "automated_repair_loop", "priority_queue", "team_analytics", "dedicated_sandbox_runners"],
        "is_active": True,
    },
]


class BillingService:
    """Manages multi-tenant subscriptions, quota enforcement, and usage ledger auditing."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def ensure_default_plans(self) -> None:
        """Seeds standard plans if none exist in the database."""
        for plan_spec in DEFAULT_PLANS_DATA:
            existing = self.db.scalar(
                select(SubscriptionPlan).where(SubscriptionPlan.plan_code == plan_spec["plan_code"])
            )
            if not existing:
                self.db.add(SubscriptionPlan(**plan_spec))
        self.db.flush()

    def get_or_create_workspace_subscription(
        self,
        workspace_id: uuid.UUID,
        owner_id: uuid.UUID | None = None,
    ) -> Subscription:
        """
        Retrieves active workspace subscription. Automatically seeds Free Starter subscription
        if the workspace was created prior to billing onboarding.
        """
        sub = self.db.scalar(
            select(Subscription).where(Subscription.workspace_id == workspace_id)
        )
        if sub:
            return sub

        self.ensure_default_plans()

        # Lookup default Free plan
        free_plan = self.db.scalar(
            select(SubscriptionPlan).where(SubscriptionPlan.plan_code == "free")
        )

        now = datetime.now(timezone.utc)
        sub = Subscription(
            workspace_id=workspace_id,
            plan_id=free_plan.id,
            billing_owner_id=owner_id,
            status="active",
            provider="mock",
            current_period_start=now - timedelta(hours=1),
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
            metadata_json={"auto_seeded": True},
        )
        self.db.add(sub)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def get_workspace_quota_usage(
        self,
        workspace_id: uuid.UUID,
    ) -> QuotaUsageSummary:
        """
        Calculates live quota consumption for the workspace across the current billing cycle.
        """
        sub = self.get_or_create_workspace_subscription(workspace_id)
        plan = sub.plan

        period_start = sub.current_period_start
        period_end = sub.current_period_end

        # 1. Agent runs used in this billing cycle
        agent_runs_count = self.db.scalar(
            select(func.coalesce(func.sum(UsageLedgerEntry.quantity), 0)).where(
                UsageLedgerEntry.workspace_id == workspace_id,
                UsageLedgerEntry.event_type == "agent_run_started",
                UsageLedgerEntry.created_at >= period_start,
                UsageLedgerEntry.created_at <= period_end,
            )
        ) or 0

        # 2. Repair runs used in this billing cycle
        repairs_count = self.db.scalar(
            select(func.coalesce(func.sum(UsageLedgerEntry.quantity), 0)).where(
                UsageLedgerEntry.workspace_id == workspace_id,
                UsageLedgerEntry.event_type == "repair_run_started",
                UsageLedgerEntry.created_at >= period_start,
                UsageLedgerEntry.created_at <= period_end,
            )
        ) or 0

        # 3. Model tokens consumed
        tokens_count = self.db.scalar(
            select(func.coalesce(func.sum(UsageLedgerEntry.token_count), 0)).where(
                UsageLedgerEntry.workspace_id == workspace_id,
                UsageLedgerEntry.created_at >= period_start,
                UsageLedgerEntry.created_at <= period_end,
            )
        ) or 0

        # 4. Currently active parallel execution runs
        parallel_active = self.db.scalar(
            select(func.count(ExecutionRun.id)).where(
                ExecutionRun.workspace_id == workspace_id,
                ExecutionRun.status.in_(ACTIVE_RUN_STATUSES),
            )
        ) or 0

        return QuotaUsageSummary(
            agent_runs_used=agent_runs_count,
            agent_runs_limit=plan.monthly_agent_runs,
            repair_runs_used=repairs_count,
            repair_runs_limit=plan.monthly_repair_runs,
            tokens_used=tokens_count,
            tokens_limit=plan.monthly_tokens,
            parallel_runs_active=parallel_active,
            max_parallel_runs=plan.max_parallel_runs,
            is_agent_runs_exceeded=agent_runs_count >= plan.monthly_agent_runs,
            is_repair_runs_exceeded=repairs_count >= plan.monthly_repair_runs,
            period_start=period_start,
            period_end=period_end,
        )

    def enforce_quota(
        self,
        workspace_id: uuid.UUID,
        quota_type: str = "agent_runs",
        quantity: int = 1,
    ) -> None:
        """
        Enforces server-side subscription quotas and concurrency limits.
        Uses database row locking on subscription to prevent concurrent race conditions.
        """
        if not self.settings.BILLING_ENFORCEMENT_ENABLED:
            return

        # Ensure subscription exists
        sub = self.get_or_create_workspace_subscription(workspace_id)

        # Acquire pessimistic lock on subscription row if database engine supports it
        try:
            locked_sub = self.db.scalar(
                select(Subscription).where(Subscription.id == sub.id).with_for_update()
            )
            if locked_sub:
                sub = locked_sub
        except Exception:
            # Fallback for engines/drivers where with_for_update is not available
            pass

        if not sub.is_in_good_standing:
            raise QuotaExceededError(
                f"Workspace subscription is {sub.status}. Please update payment method.",
                quota_type=quota_type,
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
            )

        plan = sub.plan
        usage = self.get_workspace_quota_usage(workspace_id)

        if quota_type == "agent_runs":
            if usage.agent_runs_used + quantity > plan.monthly_agent_runs:
                raise QuotaExceededError(
                    f"Monthly agent run quota exceeded ({usage.agent_runs_used}/{plan.monthly_agent_runs}). Upgrade your plan to dispatch more runs.",
                    quota_type="agent_runs",
                    limit=plan.monthly_agent_runs,
                    used=usage.agent_runs_used,
                )
            if usage.parallel_runs_active >= plan.max_parallel_runs:
                raise QuotaExceededError(
                    f"Maximum concurrent parallel runs reached ({usage.parallel_runs_active}/{plan.max_parallel_runs}). Please wait for active runs to complete or upgrade.",
                    quota_type="parallel_runs",
                    limit=plan.max_parallel_runs,
                    used=usage.parallel_runs_active,
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        elif quota_type == "repair_runs":
            if usage.repair_runs_used + quantity > plan.monthly_repair_runs:
                raise QuotaExceededError(
                    f"Monthly repair run quota exceeded ({usage.repair_runs_used}/{plan.monthly_repair_runs}). Upgrade your plan to run additional automated repairs.",
                    quota_type="repair_runs",
                    limit=plan.monthly_repair_runs,
                    used=usage.repair_runs_used,
                )

    def record_usage(
        self,
        workspace_id: uuid.UUID,
        event_type: str,
        operation_id: str,
        user_id: uuid.UUID | None = None,
        quantity: int = 1,
        run_id: uuid.UUID | None = None,
        model_name: str | None = None,
        token_count: int | None = None,
        estimated_cost_usd: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageLedgerEntry:
        """
        Records an auditable usage ledger entry.
        Guarantees idempotency via unique constraint on (operation_id, event_type).
        """
        # Check for existing entry with same operation_id and event_type
        existing = self.db.scalar(
            select(UsageLedgerEntry).where(
                UsageLedgerEntry.operation_id == str(operation_id),
                UsageLedgerEntry.event_type == event_type,
            )
        )
        if existing:
            logger.debug(
                "Idempotent usage record skipped: operation %s with event %s already recorded.",
                operation_id, event_type
            )
            return existing

        entry = UsageLedgerEntry(
            workspace_id=workspace_id,
            user_id=user_id,
            event_type=event_type,
            quantity=quantity,
            run_id=run_id,
            operation_id=str(operation_id),
            model_name=model_name,
            token_count=token_count,
            estimated_cost_usd=estimated_cost_usd,
            metadata_json=metadata or {},
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def create_checkout_session(
        self,
        workspace_id: uuid.UUID,
        user: User,
        plan_code: str,
        currency: str = "INR",
    ) -> CheckoutSessionResult:
        """Initiates a checkout session for upgrading the workspace plan."""
        self.ensure_default_plans()
        plan = self.db.scalar(
            select(SubscriptionPlan).where(
                SubscriptionPlan.plan_code == plan_code,
                SubscriptionPlan.is_active == True,  # noqa: E712
            )
        )
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription plan '{plan_code}' not found.",
            )

        provider = get_billing_provider()
        amount_cents = plan.price_inr_cents if currency.upper() == "INR" else plan.price_usd_cents

        result = provider.create_subscription_checkout(
            workspace_id=workspace_id,
            user_id=user.id,
            user_email=user.email,
            user_name=user.full_name or "Developer",
            plan_code=plan.plan_code,
            amount_cents=amount_cents,
            currency=currency,
        )
        return result

    def cancel_workspace_subscription(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Subscription:
        """Schedules active subscription for cancellation at the end of the billing period."""
        sub = self.get_or_create_workspace_subscription(workspace_id)
        if sub.plan.plan_code == "free":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Free starter plan cannot be cancelled.",
            )

        provider = get_billing_provider(sub.provider)
        if sub.provider_subscription_id:
            provider.cancel_subscription(sub.provider_subscription_id, at_period_end=True)

        sub.cancel_at_period_end = True
        sub.cancelled_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def process_webhook_event(
        self,
        provider_name: str,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """
        Cryptographically verifies and processes an inbound webhook payload idempotently.
        """
        provider = get_billing_provider(provider_name)
        verification = provider.verify_webhook_signature(raw_body, headers)

        if not verification.is_valid:
            logger.warning("Rejected invalid webhook from %s: %s", provider_name, verification.error)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=verification.error or "Invalid webhook signature",
            )

        event_id = verification.event_id
        event_type = verification.event_type
        payload = verification.payload
        payload_hash = hashlib.sha256(raw_body).hexdigest()

        # Idempotency check against processed_webhook_events
        existing_event = self.db.scalar(
            select(ProcessedWebhookEvent).where(
                ProcessedWebhookEvent.provider == provider_name,
                ProcessedWebhookEvent.event_id == event_id,
            )
        )
        if existing_event:
            logger.info("Webhook %s event %s already processed; skipping duplicate.", provider_name, event_id)
            return {"status": "already_processed", "event_id": event_id}

        # Process event transitions
        status_outcome = "processed"
        error_msg = None

        try:
            self._handle_verified_webhook(provider_name, event_type, payload)
        except Exception as e:
            logger.error("Error handling webhook event %s: %s", event_id, redact_sensitive_data(str(e)))
            status_outcome = "failed"
            error_msg = str(e)

        # Record event in processed_webhook_events log
        event_record = ProcessedWebhookEvent(
            provider=provider_name,
            event_id=event_id,
            event_type=event_type or "unknown",
            status=status_outcome,
            payload_hash=payload_hash,
            error_message=error_msg,
        )
        self.db.add(event_record)
        self.db.commit()

        if status_outcome == "failed":
            raise HTTPException(status_code=500, detail="Webhook processing failed")

        return {"status": "success", "event_id": event_id, "event_type": event_type}

    def _handle_verified_webhook(
        self,
        provider: str,
        event_type: str | None,
        payload: dict[str, Any],
    ) -> None:
        """Updates subscription state based on verified webhook event payload."""
        notes = payload.get("notes") or payload.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {})
        workspace_id_str = notes.get("workspace_id")
        plan_code = notes.get("plan_code")

        if not workspace_id_str:
            # Check top level metadata
            meta = payload.get("metadata") or {}
            workspace_id_str = meta.get("workspace_id")
            plan_code = meta.get("plan_code") or plan_code

        if not workspace_id_str:
            logger.info("Webhook payload did not contain workspace_id metadata; ignored.")
            return

        workspace_id = uuid.UUID(workspace_id_str)
        sub = self.get_or_create_workspace_subscription(workspace_id)

        now = datetime.now(timezone.utc)

        # Successful payment / activation events
        if event_type in (
            "order.paid",
            "payment.captured",
            "subscription.activated",
            "subscription.charged",
            "mock.payment_captured",
        ):
            if plan_code:
                new_plan = self.db.scalar(
                    select(SubscriptionPlan).where(SubscriptionPlan.plan_code == plan_code)
                )
                if new_plan:
                    sub.plan_id = new_plan.id

            sub.status = "active"
            sub.current_period_start = now
            sub.current_period_end = now + timedelta(days=30)
            sub.cancel_at_period_end = False
            sub.cancelled_at = None
            logger.info("Activated subscription for workspace %s on plan %s", workspace_id, plan_code)

        # Payment failure events
        elif event_type in ("payment.failed", "subscription.pending", "mock.payment_failed"):
            sub.status = "past_due"
            logger.warning("Subscription marked past_due for workspace %s", workspace_id)

        # Subscription cancellation events
        elif event_type in ("subscription.cancelled", "mock.subscription_cancelled"):
            sub.cancel_at_period_end = True
            sub.cancelled_at = now
            logger.info("Subscription marked cancel_at_period_end for workspace %s", workspace_id)
