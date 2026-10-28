from app.billing.base import BaseBillingProvider
from app.billing.mock_provider import MockBillingProvider
from app.billing.razorpay_provider import RazorpayBillingProvider
from app.core.config import get_settings


def get_billing_provider(provider_override: str | None = None) -> BaseBillingProvider:
    """
    Factory function resolving the active billing provider based on configuration.
    Defaults to MockBillingProvider if provider is 'mock' or if Razorpay credentials are unset.
    """
    settings = get_settings()
    provider_name = (provider_override or settings.BILLING_PROVIDER).lower()

    if provider_name == "razorpay" and settings.is_razorpay_configured:
        return RazorpayBillingProvider(settings)

    return MockBillingProvider()
