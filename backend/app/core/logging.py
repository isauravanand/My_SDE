import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

# Regex patterns matching sensitive information (passwords in URLs, Bearer tokens, GitHub tokens, etc.)
SENSITIVE_PATTERNS = [
    # Database URLs with passwords: postgresql://user:password@host
    (re.compile(r"://([^:]+):([^@]+)@"), r"://\1:[REDACTED_PASSWORD]@"),
    # Bearer tokens
    (re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{15,})", re.IGNORECASE), r"Bearer [REDACTED_TOKEN]"),
    # GitHub Personal Access / OAuth / Installation tokens (ghp_, gho_, ghs_, etc.)
    (re.compile(r"gh[posra]_[A-Za-z0-9_]{20,}"), r"[REDACTED_GITHUB_TOKEN]"),
    # Generic API Key / Secret assignments: api_key=xyz, secret_key=xyz
    (
        re.compile(r"(api[_-]?key|secret[_-]?key|password|token)\s*=\s*['\"]?([^'\"\s&]+)['\"]?", re.IGNORECASE),
        r"\1=[REDACTED]",
    ),
]


def redact_sensitive_data(text: str) -> str:
    """Mask sensitive tokens, passwords, and secrets in strings."""
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class RedactingFormatter(logging.Formatter):
    """Log formatter that automatically masks credentials and formats in structured JSON."""

    def __init__(self, is_json: bool = True):
        super().__init__()
        self.is_json = is_json

    def format(self, record: logging.LogRecord) -> str:
        # Redact msg and args if they are strings
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_data(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_sensitive_data(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_sensitive_data(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )

        standard_message = super().format(record)

        if not self.is_json:
            return standard_message

        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields if present
        extra_keys = set(record.__dict__.keys()) - {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message"
        }
        for key in extra_keys:
            val = getattr(record, key)
            log_data[key] = redact_sensitive_data(str(val)) if isinstance(val, str) else val

        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO", is_json: bool = False) -> None:
    """Configure root and application loggers with redacting formatter."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to prevent duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(RedactingFormatter(is_json=is_json))
    root_logger.addHandler(console_handler)

    # Suppress overly chatty third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
