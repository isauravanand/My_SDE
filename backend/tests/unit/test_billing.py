import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.billing.mock_provider import MockBillingProvider
from app.billing.razorpay_provider import RazorpayBillingProvider
from app.core.config import Settings
from app.models.billing import (
    Subscription,
    UsageLedgerEntry,
)
from app.services.billing_service import BillingService


class TestPlanDefinitionsAndStanding:
    """Validate plan configurations and subscription good-standing calculations."""

    def test_subscription_in_good_standing(self):
        now = datetime.now(timezone.utc)
        sub = Subscription(
            workspace_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        assert sub.is_in_good_standing is True

    def test_past_due_within_grace_period_is_entitled(self):
        now = datetime.now(timezone.utc)
        sub = Subscription(
            workspace_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            status="past_due",
            current_period_start=now - timedelta(days=29),
            current_period_end=now + timedelta(days=1),  # Period end still in future
        )
        assert sub.is_in_good_standing is True

    def test_past_due_after_grace_period_is_not_entitled(self):
        now = datetime.now(timezone.utc)
        sub = Subscription(
            workspace_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            status="past_due",
            current_period_start=now - timedelta(days=35),
            current_period_end=now - timedelta(days=5),
        )
        assert sub.is_in_good_standing is False


class TestMockBillingProvider:
    """Validate mock billing provider behavior for offline environments."""

    def test_mock_checkout_creation(self):
        provider = MockBillingProvider()
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        result = provider.create_subscription_checkout(
            workspace_id=ws_id,
            user_id=user_id,
            user_email="dev@example.com",
            user_name="Dev User",
            plan_code="pro",
            amount_cents=249900,
            currency="INR",
        )

        assert result.provider == "mock"
        assert result.plan_code == "pro"
        assert result.amount_cents == 249900
        assert result.provider_subscription_id.startswith("mock_sub_")
        assert result.session_id.startswith("mock_chk_")

    def test_mock_webhook_signature_verification(self):
        secret = "test_mock_secret_key_12345"
        provider = MockBillingProvider(webhook_secret=secret)

        raw_payload = json.dumps({"event": "order.paid", "id": "evt_123"}).encode("utf-8")
        valid_signature = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()

        res = provider.verify_webhook_signature(raw_payload, {"x-mock-signature": valid_signature})
        assert res.is_valid is True
        assert res.event_id == "evt_123"
        assert res.event_type == "order.paid"

    def test_mock_webhook_tampered_payload_rejected(self):
        secret = "test_mock_secret_key_12345"
        provider = MockBillingProvider(webhook_secret=secret)

        raw_payload = json.dumps({"event": "order.paid", "id": "evt_123"}).encode("utf-8")
        tampered_payload = json.dumps({"event": "order.paid", "id": "evt_123", "hacked": True}).encode("utf-8")
        valid_signature = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()

        res = provider.verify_webhook_signature(tampered_payload, {"x-mock-signature": valid_signature})
        assert res.is_valid is False
        assert "Invalid" in res.error


class TestRazorpayProviderSignatures:
    """Validate Razorpay HMAC-SHA256 signature verification over raw request body."""

    def test_valid_razorpay_signature(self):
        secret = "rzp_secret_webhook_key_xyz"
        settings = Settings(
            RAZORPAY_KEY_ID="rzp_test_1234567890",
            RAZORPAY_KEY_SECRET="fake_secret_key_123",
            RAZORPAY_WEBHOOK_SECRET=secret,
        )
        provider = RazorpayBillingProvider(settings)

        payload_bytes = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_test_001"}}}}'
        expected_sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

        res = provider.verify_webhook_signature(
            payload_bytes,
            {"x-razorpay-signature": expected_sig},
        )
        assert res.is_valid is True
        assert res.event_type == "payment.captured"
        assert res.event_id == "pay_test_001"

    def test_invalid_razorpay_signature(self):
        secret = "rzp_secret_webhook_key_xyz"
        settings = Settings(
            RAZORPAY_KEY_ID="rzp_test_1234567890",
            RAZORPAY_KEY_SECRET="fake_secret_key_123",
            RAZORPAY_WEBHOOK_SECRET=secret,
        )
        provider = RazorpayBillingProvider(settings)

        payload_bytes = b'{"event":"payment.captured"}'
        res = provider.verify_webhook_signature(
            payload_bytes,
            {"x-razorpay-signature": "bogus_signature_attempt"},
        )
        assert res.is_valid is False
        assert "Invalid" in res.error


class TestUsageLedgerIdempotency:
    """Validate that duplicate operational ledger entries are deduplicated."""

    def test_record_usage_idempotency(self):
        mock_db = MagicMock()
        workspace_id = uuid.uuid4()
        operation_id = "op_id_unique_123"

        # Mock existing record
        existing_entry = MagicMock(spec=UsageLedgerEntry)
        existing_entry.operation_id = operation_id
        existing_entry.event_type = "agent_run_started"

        mock_db.scalar.return_value = existing_entry

        service = BillingService(mock_db)
        entry = service.record_usage(
            workspace_id=workspace_id,
            event_type="agent_run_started",
            operation_id=operation_id,
        )

        assert entry == existing_entry
        mock_db.add.assert_not_called()
