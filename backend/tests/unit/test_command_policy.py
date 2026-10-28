import pytest

from app.execution.command_policy import CommandPolicy, CommandPolicyViolation


def test_command_allowlist_valid():
    allowed = CommandPolicy.get_allowed_commands()
    assert "pytest" in allowed
    assert "ruff_check" in allowed
    assert "syntax_check" in allowed
    assert "npm_test" in allowed
    assert "npm_lint" in allowed


def test_disallowed_command_rejection():
    for forbidden in ["curl", "rm", "sh", "bash", "python -c", "eval", "cat"]:
        with pytest.raises(CommandPolicyViolation, match="not in the server-side allowlist"):
            CommandPolicy.resolve_and_validate(forbidden)


@pytest.mark.parametrize(
    "injection_payload",
    [
        "; rm -rf /",
        "| cat /etc/passwd",
        "& whoami",
        "$(id)",
        "`id`",
        "> output.txt",
        "< input.txt",
        "test\nrm -rf /",
        "test\r\ncalc.exe",
    ],
)
def test_shell_injection_attempts_rejected(injection_payload):
    with pytest.raises(CommandPolicyViolation, match="disallowed shell metacharacters"):
        CommandPolicy.resolve_and_validate("pytest", extra_args=[injection_payload])


def test_path_traversal_argument_rejected():
    with pytest.raises(CommandPolicyViolation, match="directory traversal"):
        CommandPolicy.resolve_and_validate("pytest", extra_args=["../../etc/passwd"])


def test_flag_allowlist_enforcement():
    # Permitted flag
    v_type, args = CommandPolicy.resolve_and_validate("pytest", extra_args=["-v"])
    assert "-v" in args
    assert v_type == "test"

    # Disallowed flag
    with pytest.raises(CommandPolicyViolation, match="Flag '--arbitrary-flag' is not permitted"):
        CommandPolicy.resolve_and_validate("pytest", extra_args=["--arbitrary-flag"])


def test_output_truncation():
    large_stdout = "A" * 30000
    truncated = CommandPolicy.sanitize_and_truncate_output(large_stdout, max_bytes=20480)
    assert len(truncated.encode("utf-8")) <= 21000  # including truncation message
    assert "[TRUNCATED: Exceeded 20480 byte limit]" in truncated


def test_secret_redaction():
    text_with_secrets = (
        "Logs:\n"
        "Connecting with ghp_123456789012345678901234567890123456...\n"
        "Authorization: Bearer my-secret-jwt-token-value-12345\n"
        "DB connection: password='SuperSecretPassword123!'\n"
        "AWS credentials: AKIAIOSFODNN7EXAMPLE\n"
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----\n"
    )

    sanitized = CommandPolicy.sanitize_and_truncate_output(text_with_secrets)

    assert "ghp_123456789012345678901234567890123456" not in sanitized
    assert "[REDACTED_GITHUB_TOKEN]" in sanitized

    assert "my-secret-jwt-token-value-12345" not in sanitized
    assert "Bearer [REDACTED_TOKEN]" in sanitized

    assert "SuperSecretPassword123!" not in sanitized
    assert "password=[REDACTED]" in sanitized

    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
    assert "[REDACTED_AWS_KEY]" in sanitized

    assert "-----BEGIN RSA PRIVATE KEY-----" not in sanitized
    assert "[REDACTED_PRIVATE_KEY]" in sanitized
