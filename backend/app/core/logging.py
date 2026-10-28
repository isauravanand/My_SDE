import json
import logging
import os
import re
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Context variables for distributed tracing & structured logging
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)
operation_ctx: ContextVar[str | None] = ContextVar("operation", default=None)
task_id_ctx: ContextVar[str | None] = ContextVar("task_id", default=None)
run_id_ctx: ContextVar[str | None] = ContextVar("run_id", default=None)


@contextmanager
def set_log_context(
    correlation_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
    operation: str | None = None,
):
    """Scoped context manager for attaching tracing and run context to log records."""
    tokens = []
    if correlation_id is not None:
        tokens.append((correlation_id_ctx, correlation_id_ctx.set(correlation_id)))
    if task_id is not None:
        tokens.append((task_id_ctx, task_id_ctx.set(str(task_id))))
    if run_id is not None:
        tokens.append((run_id_ctx, run_id_ctx.set(str(run_id))))
    if operation is not None:
        tokens.append((operation_ctx, operation_ctx.set(operation)))
    try:
        yield
    finally:
        for ctx_var, token in reversed(tokens):
            ctx_var.reset(token)


# Regex patterns matching sensitive credentials, tokens, private keys, and connection strings
SENSITIVE_PATTERNS = [
    # Database URLs with passwords: postgresql://user:password@host
    (re.compile(r"://([^:]+):([^@]+)@", re.IGNORECASE), r"://\1:[REDACTED_PASSWORD]@"),
    # Bearer tokens
    (re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{15,})", re.IGNORECASE), r"Bearer [REDACTED_TOKEN]"),
    # GitHub Personal Access / OAuth / Installation tokens (ghp_, gho_, ghs_, etc.)
    (re.compile(r"\bgh[posra]_[A-Za-z0-9_]{20,}\b"), r"[REDACTED_GITHUB_TOKEN]"),
    # Anthropic API Keys (sk-ant-...) - must be matched before generic sk-
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), r"[REDACTED_ANTHROPIC_KEY]"),
    # OpenAI API Keys (sk-...)
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), r"[REDACTED_OPENAI_KEY]"),
    # Groq API Keys (gsk_...)
    (re.compile(r"\bgsk_[A-Za-z0-9_]{20,}\b"), r"[REDACTED_GROQ_KEY]"),
    # Razorpay API Keys (rzp_test_..., rzp_live_...)
    (re.compile(r"\brzp_(?:test|live)_[A-Za-z0-9_]{14,}\b"), r"[REDACTED_RAZORPAY_KEY]"),
    # RSA / EC / OPENSSH Private Keys (single-line or multiline)
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        r"[REDACTED_PRIVATE_KEY]",
    ),
    # Generic API Key / Secret / Webhook / JWT assignments
    (
        re.compile(
            r"(api[_-]?key|secret[_-]?key|client[_-]?secret|webhook[_-]?secret|password|access[_-]?token|private[_-]?key)\s*[:=]\s*['\"]?([^'\"\s&,]+)['\"]?",
            re.IGNORECASE,
        ),
        r"\1=[REDACTED]",
    ),
]


def redact_sensitive_data(text: str) -> str:
    """Mask sensitive tokens, passwords, private keys, and secrets in strings."""
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class RedactingFormatter(logging.Formatter):
    """
    Log formatter that automatically masks credentials and formats in structured JSON
    or enriched text format with correlation, environment, and task metadata.
    """

    def __init__(self, fmt: str | None = None, datefmt: str | None = None, is_json: bool = True):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.is_json = is_json
        self.app_env = os.environ.get("APP_ENV", "development")

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

        # Contextual metadata from contextvars or record overrides
        request_id = getattr(record, "request_id", None) or correlation_id_ctx.get() or "-"
        operation = getattr(record, "operation", None) or operation_ctx.get() or "-"
        task_id = getattr(record, "task_id", None) or task_id_ctx.get() or "-"
        run_id = getattr(record, "run_id", None) or run_id_ctx.get() or "-"

        # Inject into record attributes for standard %(...)s formatters
        record.request_id = request_id
        record.operation = operation
        record.task_id = task_id
        record.run_id = run_id

        standard_message = super().format(record)
        redacted_message = redact_sensitive_data(standard_message)

        if not self.is_json:
            if self._fmt and self._fmt != "%(message)s":
                return redacted_message

            # Enriched console message
            ctx_tags = []
            if request_id and request_id != "-":
                ctx_tags.append(f"req={request_id[:8]}")
            if operation and operation != "-":
                ctx_tags.append(f"op={operation}")
            if task_id and task_id != "-":
                ctx_tags.append(f"task={str(task_id)[:8]}")
            if run_id and run_id != "-":
                ctx_tags.append(f"run={str(run_id)[:8]}")

            tag_prefix = f" [{ ' '.join(ctx_tags) }]" if ctx_tags else ""
            return f"{record.levelname:<7} {record.name}{tag_prefix}: {redact_sensitive_data(record.getMessage())}"

        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "environment": self.app_env,
            "logger": record.name,
            "message": redact_sensitive_data(record.getMessage()),
            "request_id": request_id,
            "operation": operation,
            "task_id": task_id,
            "run_id": run_id,
        }

        if record.exc_info:
            formatted_exc = self.formatException(record.exc_info)
            log_data["exception"] = redact_sensitive_data(formatted_exc)

        # Include custom extra fields if present
        extra_keys = set(record.__dict__.keys()) - {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "request_id", "operation", "task_id", "run_id"
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
