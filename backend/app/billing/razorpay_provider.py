import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

import httpx

from app.billing.base import BaseBillingProvider, CheckoutSessionResult, WebhookVerificationResult
from app.core.config import Settings, get_settings
from app.core.logging import redact_sensitive_data

logger = logging.getLogger(__name__)


class RazorpayBillingError(Exception):
    """Raised when Razorpay API interaction fails."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RazorpayBillingProvider(BaseBillingProvider):
    """
    India-compatible billing provider integration with Razorpay Subscription & Orders API.
    Operates in test/sandbox mode with verified HMAC-SHA256 webhook signatures.
    """

    RAZORPAY_API_BASE = "https://api.razorpay.com/v1"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.key_id = self.settings.RAZORPAY_KEY_ID
        self.key_secret = self.settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = self.settings.RAZORPAY_WEBHOOK_SECRET

    def _ensure_configured(self) -> None:
        if not self.key_id or not self.key_secret:
            raise RazorpayBillingError(
                "Razorpay API credentials (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET) are not configured."
            )

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
        """
        Creates a Razorpay Subscription / Order reference for frontend checkout initiation.
        """
        self._ensure_configured()

        payload = {
            "amount": amount_cents,  # in smallest currency unit (e.g. paise)
            "currency": currency.upper(),
            "receipt": f"rcpt_{str(workspace_id)[:8]}_{uuid.uuid4().hex[:6]}",
            "notes": {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "plan_code": plan_code,
                "user_email": user_email,
            },
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{self.RAZORPAY_API_BASE}/orders",
                    auth=(self.key_id, self.key_secret),
                    json=payload,
                )
        except Exception as e:
            logger.error("Failed to connect to Razorpay API: %s", redact_sensitive_data(str(e)))
            raise RazorpayBillingError(f"Unable to reach payment provider: {e}") from e

        if resp.status_code >= 400:
            error_data = resp.json().get("error", {}) if resp.text else {}
            msg = error_data.get("description") or f"Razorpay order creation returned HTTP {resp.status_code}"
            logger.error("Razorpay order creation error: %s", redact_sensitive_data(msg))
            raise RazorpayBillingError(msg, status_code=resp.status_code)

        order_data = resp.json()
        order_id = order_data["id"]

        return CheckoutSessionResult(
            provider="razorpay",
            session_id=order_id,
            checkout_url=f"/billing?provider=razorpay&order_id={order_id}&plan={plan_code}",
            plan_code=plan_code,
            amount_cents=amount_cents,
            currency=currency,
            provider_subscription_id=order_id,
            metadata={
                "order_id": order_id,
                "key_id": self.key_id,
                "workspace_id": str(workspace_id),
                "user_name": user_name,
                "user_email": user_email,
            },
        )

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> WebhookVerificationResult:
        """
        Verify inbound webhook signature using HMAC-SHA256 against the raw request body.
        Uses constant-time comparison to prevent timing attacks.
        """
        if not self.webhook_secret:
            return WebhookVerificationResult(
                is_valid=False,
                error="Razorpay webhook secret is not configured on the server.",
            )

        signature = headers.get("x-razorpay-signature") or headers.get("X-Razorpay-Signature")
        if not signature:
            return WebhookVerificationResult(
                is_valid=False,
                error="Missing X-Razorpay-Signature header in webhook request.",
            )

        expected_sig = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("Razorpay webhook signature verification failed.")
            return WebhookVerificationResult(
                is_valid=False,
                error="Invalid cryptographic signature for webhook payload.",
            )

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            return WebhookVerificationResult(
                is_valid=False,
                error=f"Malformed webhook JSON payload: {e}",
            )

        event_type = payload.get("event")
        event_id = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id") or f"rzp_evt_{uuid.uuid4().hex[:12]}"

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
        self._ensure_configured()
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{self.RAZORPAY_API_BASE}/subscriptions/{provider_subscription_id}/cancel",
                    auth=(self.key_id, self.key_secret),
                    json={"cancel_at_cycle_end": 1 if at_period_end else 0},
                )
                return resp.status_code in (200, 204)
        except Exception as e:
            logger.error("Failed to cancel Razorpay subscription %s: %s", provider_subscription_id, redact_sensitive_data(str(e)))
            return False

    def get_subscription_status(
        self,
        provider_subscription_id: str,
    ) -> dict[str, Any]:
        self._ensure_configured()
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    f"{self.RAZORPAY_API_BASE}/subscriptions/{provider_subscription_id}",
                    auth=(self.key_id, self.key_secret),
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.error("Failed to fetch Razorpay subscription status: %s", redact_sensitive_data(str(e)))
        return {"id": provider_subscription_id, "status": "unknown"}
