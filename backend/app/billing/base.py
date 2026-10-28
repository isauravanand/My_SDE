import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class CheckoutSessionResult(BaseModel):
    """Result of creating a checkout session or order with a billing provider."""
    provider: str
    session_id: str
    checkout_url: str | None = None
    plan_code: str
    amount_cents: int
    currency: str = "INR"
    provider_customer_id: str | None = None
    provider_subscription_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebhookVerificationResult(BaseModel):
    """Result of cryptographically verifying an inbound provider webhook."""
    is_valid: bool
    event_id: str | None = None
    event_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BaseBillingProvider(ABC):
    """Provider-neutral abstract interface for SaaS subscription billing."""

    @abstractmethod
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
        """Create a hosted checkout session or payment order reference."""
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> WebhookVerificationResult:
        """Cryptographically verify the inbound webhook payload using the raw request body."""
        pass

    @abstractmethod
    def cancel_subscription(
        self,
        provider_subscription_id: str,
        at_period_end: bool = True,
    ) -> bool:
        """Request cancellation of an active subscription with the payment gateway."""
        pass

    @abstractmethod
    def get_subscription_status(
        self,
        provider_subscription_id: str,
    ) -> dict[str, Any]:
        """Fetch live subscription status directly from the provider API."""
        pass
