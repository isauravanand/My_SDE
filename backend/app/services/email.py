import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class SentEmail:
    """Record of a dispatched email (primarily used in development and tests)."""
    to_email: str
    subject: str
    token: str
    purpose: str


class BaseEmailService(ABC):
    """Abstract interface for transactional email delivery."""

    @abstractmethod
    def send_verification_email(
        self, to_email: str, token: str, full_name: str | None = None
    ) -> bool:
        pass

    @abstractmethod
    def send_password_reset_email(
        self, to_email: str, token: str, full_name: str | None = None
    ) -> bool:
        pass


class DevelopmentEmailService(BaseEmailService):
    """Clearly marked development-only email adapter.

    Records dispatched emails in memory and logs verification links during development.
    Never used in production.
    """

    def __init__(self):
        self.sent_emails: list[SentEmail] = []

    def send_verification_email(
        self, to_email: str, token: str, full_name: str | None = None
    ) -> bool:
        self.sent_emails.append(
            SentEmail(
                to_email=to_email,
                subject="Verify your MySDE account",
                token=token,
                purpose="email_verification",
            )
        )
        verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        if settings.APP_ENV != "production":
            logger.info(
                "[DEV EMAIL ADAPTER] Verification link for %s: %s",
                to_email,
                verify_url,
            )
        else:
            logger.info("[DEV EMAIL ADAPTER] Verification email simulated for %s", to_email)
        return True

    def send_password_reset_email(
        self, to_email: str, token: str, full_name: str | None = None
    ) -> bool:
        self.sent_emails.append(
            SentEmail(
                to_email=to_email,
                subject="Reset your MySDE password",
                token=token,
                purpose="password_reset",
            )
        )
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        if settings.APP_ENV != "production":
            logger.info(
                "[DEV EMAIL ADAPTER] Password reset link for %s: %s",
                to_email,
                reset_url,
            )
        else:
            logger.info("[DEV EMAIL ADAPTER] Password reset simulated for %s", to_email)
        return True

    def get_last_token(self, to_email: str, purpose: str) -> str | None:
        """Helper for test assertions to retrieve dispatched tokens."""
        for email_record in reversed(self.sent_emails):
            if email_record.to_email == to_email and email_record.purpose == purpose:
                return email_record.token
        return None


# Global singleton instance for development service
_dev_email_service = DevelopmentEmailService()


def get_email_service() -> BaseEmailService:
    """Return the configured email adapter."""
    return _dev_email_service
