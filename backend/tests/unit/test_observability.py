import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx

from app.core.logging import (
    RedactingFormatter,
    correlation_id_ctx,
    redact_sensitive_data,
    set_log_context,
)
from app.integrations.github.client import GitHubApiClient
from app.models.execution import ExecutionRun
from app.services.run_recovery import RunRecoveryService


class TestSecretRedaction:
    """Validate comprehensive secret redaction across log outputs and error messages."""

    def test_redact_database_passwords(self):
        msg = "Connecting to postgresql+psycopg://postgres:SuperSecretP@ss123@127.0.0.1:5432/mysde_dev"
        redacted = redact_sensitive_data(msg)
        assert "SuperSecretP@ss123" not in redacted
        assert "[REDACTED_PASSWORD]" in redacted

    def test_redact_bearer_tokens(self):
        msg = "Header: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.saurav_token"
        redacted = redact_sensitive_data(msg)
        assert "eyJhbGci" not in redacted
        assert "saurav_token" not in redacted
        assert "Bearer [REDACTED_TOKEN]" in redacted

    def test_redact_openai_api_keys(self):
        msg = "Invoking model with key sk-proj-abc1234567890abcdefghijklmnopqrstuvwxyz12345678"
        redacted = redact_sensitive_data(msg)
        assert "abc1234567890abcdef" not in redacted
        assert "[REDACTED_OPENAI_KEY]" in redacted

    def test_redact_anthropic_api_keys(self):
        msg = "Invoking Anthropic provider sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        redacted = redact_sensitive_data(msg)
        assert "abcdefghijklmnopqrstuvwxyz" not in redacted
        assert "[REDACTED_ANTHROPIC_KEY]" in redacted

    def test_redact_github_personal_access_token(self):
        msg = "Cloning repository using token ghp_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8"
        redacted = redact_sensitive_data(msg)
        assert "A1B2C3D4E5F6G7H8I9J0" not in redacted
        assert "[REDACTED_GITHUB_TOKEN]" in redacted

    def test_redact_rsa_private_key_blocks(self):
        key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0Y3yABCDEF1234567890xyz\n"
            "ABCDEFGHIJKLM1234567890OPQRSTUVWXYZ\n"
            "-----END RSA PRIVATE KEY-----"
        )
        msg = f"App initialized with private key:\n{key}"
        redacted = redact_sensitive_data(msg)
        assert "MIIEowIBAAKCAQEA0Y3y" not in redacted
        assert "[REDACTED_PRIVATE_KEY]" in redacted


class TestStructuredLoggingContext:
    """Validate ContextVar propagation into structured log formatters."""

    def test_formatter_includes_correlation_fields_json(self):
        formatter = RedactingFormatter(is_json=True)
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=42,
            msg="Running stage with secret key sk-proj-1234567890abcdef1234567890",
            args=(),
            exc_info=None,
        )

        with set_log_context(
            correlation_id="req-uuid-123",
            task_id="task-uuid-456",
            run_id="run-uuid-789",
            operation="stage_execution",
        ):
            formatted = formatter.format(record)
            import json
            data = json.loads(formatted)
            assert data["request_id"] == "req-uuid-123"
            assert data["task_id"] == "task-uuid-456"
            assert data["run_id"] == "run-uuid-789"
            assert data["operation"] == "stage_execution"
            assert "[REDACTED_OPENAI_KEY]" in data["message"]
            assert "1234567890abcdef" not in data["message"]

    def test_formatter_includes_correlation_fields_text(self):
        formatter = RedactingFormatter(is_json=False)
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=42,
            msg="Running text stage",
            args=(),
            exc_info=None,
        )

        with set_log_context(
            correlation_id="req-uuid-123",
            task_id="task-uuid-456",
            run_id="run-uuid-789",
            operation="stage_execution",
        ):
            formatted = formatter.format(record)
            assert "req=req-uuid" in formatted
            assert "task=task-uui" in formatted
            assert "op=stage_execution" in formatted

    def test_log_context_resets_properly(self):
        with set_log_context(correlation_id="temp-id-999"):
            assert correlation_id_ctx.get() == "temp-id-999"
        assert correlation_id_ctx.get() is None


class TestGitHubClientResilience:
    """Validate exponential backoff, jitter, and Retry-After handling in GitHub App client."""

    @patch("app.integrations.github.client.httpx.Client")
    @patch("app.integrations.github.client.time.sleep")
    def test_retry_on_rate_limit_with_retry_after(self, mock_sleep, mock_client_cls):
        client = GitHubApiClient()

        resp_429 = httpx.Response(
            status_code=429,
            headers={"Retry-After": "3"},
            request=httpx.Request("GET", "https://api.github.com/installations"),
        )
        resp_200 = httpx.Response(
            status_code=200,
            json=[{"id": 999}],
            request=httpx.Request("GET", "https://api.github.com/installations"),
        )

        mock_instance = MagicMock()
        mock_instance.request.side_effect = [resp_429, resp_200]
        mock_client_cls.return_value.__enter__.return_value = mock_instance

        result = client._request_with_retry(
            method="GET",
            url="https://api.github.com/installations",
            headers={"Authorization": "Bearer fake"},
            max_retries=3,
        )

        assert result.status_code == 200
        assert mock_instance.request.call_count == 2
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] >= 3.0

    @patch("app.integrations.github.client.httpx.Client")
    @patch("app.integrations.github.client.time.sleep")
    def test_non_retryable_error_fails_immediately(self, mock_sleep, mock_client_cls):
        client = GitHubApiClient()

        resp_404 = httpx.Response(
            status_code=404,
            json={"message": "Not Found"},
            request=httpx.Request("GET", "https://api.github.com/repos/foo/bar"),
        )
        mock_instance = MagicMock()
        mock_instance.request.return_value = resp_404
        mock_client_cls.return_value.__enter__.return_value = mock_instance

        result = client._request_with_retry(
            method="GET",
            url="https://api.github.com/repos/foo/bar",
            headers={"Authorization": "Bearer fake"},
            max_retries=3,
        )

        assert result.status_code == 404
        assert mock_instance.request.call_count == 1
        mock_sleep.assert_not_called()

    @patch("app.integrations.github.client.httpx.Client")
    @patch("app.integrations.github.client.time.sleep")
    def test_retry_exhaustion_returns_last_response(self, mock_sleep, mock_client_cls):
        client = GitHubApiClient()

        resp_503 = httpx.Response(
            status_code=503,
            request=httpx.Request("GET", "https://api.github.com/meta"),
        )
        mock_instance = MagicMock()
        mock_instance.request.return_value = resp_503
        mock_client_cls.return_value.__enter__.return_value = mock_instance

        result = client._request_with_retry(
            method="GET",
            url="https://api.github.com/meta",
            headers={"Authorization": "Bearer fake"},
            max_retries=2,
        )

        assert result.status_code == 503
        assert mock_instance.request.call_count == 2
        assert mock_sleep.call_count == 1


class TestStaleRunRecovery:
    """Validate recovery and terminal state transition for interrupted agent runs."""

    def test_recover_stale_execution_runs(self):
        mock_db = MagicMock()
        workspace_id = uuid.uuid4()

        stale_run = MagicMock(spec=ExecutionRun)
        stale_run.id = uuid.uuid4()
        stale_run.status = "running"
        stale_run.started_at = datetime.now(timezone.utc) - timedelta(minutes=45)
        stale_run.completed_at = None
        stale_run.safe_error_summary = None

        # Return stale_run for executions, and empty lists for repairs and publishing
        mock_db.scalars.return_value.all.side_effect = [[stale_run], [], []]

        result = RunRecoveryService.recover_stale_runs(mock_db, workspace_id=workspace_id, timeout_minutes=15)

        assert result.recovered_executions == 1
        assert stale_run.status == "timed_out"
        assert stale_run.completed_at is not None
        assert "timed out or was interrupted" in stale_run.safe_error_summary
        assert mock_db.commit.call_count >= 1
