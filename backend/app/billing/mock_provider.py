import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

from app.billing.base import BaseBillingProvider, CheckoutSessionResult, WebhookVerificationResult

logger = logging.getLogger(__name__)


class MockBillingProvider(BaseBillingProvider):
    """
    Deterministic simulated billing provider for local development and automated testing.
    Never initiates network requests, requires no external secrets, and never makes real charges.
    """

    MOCK_WEBHOOK_SECRET = "mock_webhook_secret_dev_key_32chars"

    def __init__(self, webhook_secret: str | None = None):
        self.webhook_secret = webhook_secret or self.MOCK_WEBHOOK_SECRET

    def create_subscription_checkout(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        user_email: str,
        user_name: str,
        plan_code: str,
        amount_cents: int,
        currency: str = "INR",
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> CheckoutSessionResult:
        session_id = f"mock_chk_{uuid.uuid4().hex[:16]}"
        sub_id = f"mock_sub_{uuid.uuid4().hex[:16]}"
        cust_id = f"mock_cust_{uuid.uuid4().hex[:16]}"

        logger.info(
            "Created simulated checkout session for workspace %s (plan=%s, amount=%d %s)",
            workspace_id, plan_code, amount_cents, currency
        )

        return CheckoutSessionResult(
            provider="mock",
            session_id=session_id,
            checkout_url=f"/billing?mock_checkout_session={session_id}&plan={plan_code}",
            plan_code=plan_code,
            amount_cents=amount_cents,
            currency=currency,
            provider_customer_id=cust_id,
            provider_subscription_id=sub_id,
            metadata={
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "user_email": user_email,
            },
        )

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> WebhookVerificationResult:
        signature = headers.get("x-mock-signature") or headers.get("X-Mock-Signature")
        if not signature:
            # Also allow testing with razorpay header alias in mock mode
            signature = headers.get("x-razorpay-signature") or headers.get("X-Razorpay-Signature")

        expected_sig = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not signature or not hmac.compare_digest(signature, expected_sig):
            return WebhookVerificationResult(
                is_valid=False,
                error="Invalid webhook cryptographic signature",
            )

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            return WebhookVerificationResult(
                is_valid=False,
                error=f"Malformed webhook JSON body: {e}",
            )

        event_id = payload.get("event_id") or payload.get("id") or f"mock_evt_{uuid.uuid4().hex[:12]}"
        event_type = payload.get("event") or payload.get("event_type") or "subscription.activated"

        return WebhookVerificationResult(
            is_valid=True,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
        )

    def cancel_subscription(
        self,
        provider_subscription_id: str,
        at_period_end: bool = True,
    ) -> bool:
        logger.info(
            "Mock billing provider marked subscription %s as cancelled (at_period_end=%s)",
            provider_subscription_id, at_period_end
        )
        return True

    def get_subscription_status(
        self,
        provider_subscription_id: str,
    ) -> dict[str, Any]:
        return {
            "id": provider_subscription_id,
            "status": "active",
            "provider": "mock",
        }
