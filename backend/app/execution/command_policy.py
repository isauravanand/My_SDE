import re
from typing import Any

# Disallowed shell metacharacters that indicate command chaining or shell injection
FORBIDDEN_SHELL_PATTERN = re.compile(r"[;&|`$<>()\r\n]")

# Common secret regex patterns for redaction
SECRET_PATTERNS = [
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_\.=]+"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)password\s*[:=]\s*['\"]?[^\s'\"]+"), "password=[REDACTED]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
]


class CommandPolicyViolation(Exception):
    """Raised when an execution command violates server-side security policy."""

    pass


# Strict server-side allowlist of permitted verification operations
ALLOWED_COMMAND_DEFINITIONS: dict[str, dict[str, Any]] = {
    "pytest": {
        "description": "Run pytest test suite",
        "verification_type": "test",
        "default_command": ["python", "-m", "pytest", "-v"],
        "allowed_extra_flags": {"-v", "-q", "--tb=short", "--maxfail=5", "-s"},
    },
    "ruff_check": {
        "description": "Run Ruff linter",
        "verification_type": "lint",
        "default_command": ["python", "-m", "ruff", "check", "."],
        "allowed_extra_flags": {"--isolated", "--select=E,F,W"},
    },
    "npm_test": {
        "description": "Run npm test suite",
        "verification_type": "test",
        "default_command": ["npm", "test", "--", "--run"],
        "allowed_extra_flags": {"--passWithNoTests", "--silent"},
    },
    "npm_lint": {
        "description": "Run npm linter",
        "verification_type": "lint",
        "default_command": ["npm", "run", "lint"],
        "allowed_extra_flags": set(),
    },
    "syntax_check": {
        "description": "Compile Python files to verify syntax",
        "verification_type": "syntax",
        "default_command": ["python", "-m", "py_compile"],
        "allowed_extra_flags": set(),
    },
}


class CommandPolicy:
    """Enforces strict server-side command validation and output sanitization."""

    @staticmethod
    def get_allowed_commands() -> list[str]:
        return list(ALLOWED_COMMAND_DEFINITIONS.keys())

    @classmethod
    def resolve_and_validate(
        cls,
        command_key: str,
        extra_args: list[str] | None = None,
    ) -> tuple[str, list[str]]:
        """
        Validates command against the server allowlist.
        Returns (verification_type, safe_argv_list).
        Raises CommandPolicyViolation if forbidden.
        """
        if command_key not in ALLOWED_COMMAND_DEFINITIONS:
            raise CommandPolicyViolation(
                f"Command '{command_key}' is not in the server-side allowlist. "
                f"Permitted commands: {list(ALLOWED_COMMAND_DEFINITIONS.keys())}"
            )

        cmd_def = ALLOWED_COMMAND_DEFINITIONS[command_key]
        base_argv = list(cmd_def["default_command"])
        allowed_flags = cmd_def.get("allowed_extra_flags", set())

        if extra_args:
            for arg in extra_args:
                # Check for forbidden shell metacharacters
                if FORBIDDEN_SHELL_PATTERN.search(arg):
                    raise CommandPolicyViolation(
                        f"Argument '{arg}' contains disallowed shell metacharacters."
                    )
                # Check against allowlist of flags if not a standard safe relative path
                if arg.startswith("-"):
                    if arg not in allowed_flags:
                        raise CommandPolicyViolation(
                            f"Flag '{arg}' is not permitted for command '{command_key}'."
                        )
                else:
                    # Non-flag arguments must not escape workspace
                    if ".." in arg or arg.startswith("/") or arg.startswith("\\"):
                        raise CommandPolicyViolation(
                            f"Path argument '{arg}' is invalid or attempts directory traversal."
                        )
                base_argv.append(arg)

        return cmd_def["verification_type"], base_argv

    @staticmethod
    def sanitize_and_truncate_output(
        output: str,
        max_bytes: int = 20480,
    ) -> str:
        """
        Redacts known secret patterns and bounds output length.
        """
        if not output:
            return ""

        # Redact secrets
        sanitized = output
        for pattern, replacement in SECRET_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)

        # Truncate if exceeds max_bytes
        encoded = sanitized.encode("utf-8", errors="replace")
        if len(encoded) > max_bytes:
            truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
            sanitized = truncated + f"\n... [TRUNCATED: Exceeded {max_bytes} byte limit]"

        return sanitized
