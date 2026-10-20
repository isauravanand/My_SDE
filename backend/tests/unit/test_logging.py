from app.core.logging import redact_sensitive_data


def test_redact_database_password():
    raw = "Connecting to postgresql://admin:SuperSecretPass123!@db.internal:5432/mysde"
    redacted = redact_sensitive_data(raw)
    assert "SuperSecretPass123!" not in redacted
    assert "admin:[REDACTED_PASSWORD]@db.internal:5432" in redacted


def test_redact_bearer_token():
    raw = "Authorization header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token"
    redacted = redact_sensitive_data(raw)
    assert "eyJhbGciOi" not in redacted
    assert "Bearer [REDACTED_TOKEN]" in redacted


def test_redact_github_token():
    raw = "Using token ghp_1234567890abcdefghijklmnopqrstuvwxyz to fetch repo"
    redacted = redact_sensitive_data(raw)
    assert "ghp_1234567890" not in redacted
    assert "[REDACTED_GITHUB_TOKEN]" in redacted
