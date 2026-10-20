from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core Application
    APP_NAME: str = Field(default="MySDE Backend", description="Application display name")
    APP_ENV: Literal["development", "staging", "production", "test"] = Field(
        default="development", description="Runtime environment"
    )
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    API_V1_PREFIX: str = Field(default="/api/v1", description="Prefix for API v1 routes")
    FRONTEND_URL: str = Field(default="http://localhost:5173", description="Frontend origin URL")

    # Security & Sessions
    SECRET_KEY: str = Field(
        default="development-insecure-secret-key-replace-in-production-min32chars",
        description="Secret key used for cryptographic signatures",
    )
    SESSION_MAX_AGE_DAYS: int = Field(default=7, ge=1, le=90)
    COOKIE_SECURE: bool = Field(
        default=False,
        description="Set Secure flag on cookies. Enforced True in production.",
    )
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = Field(default="lax")

    # GitHub App Integration
    GITHUB_APP_ID: str | None = Field(default=None, description="GitHub App ID")
    GITHUB_APP_CLIENT_ID: str | None = Field(default=None, description="GitHub App Client ID")
    GITHUB_APP_CLIENT_SECRET: str | None = Field(default=None, description="GitHub App Client Secret")
    GITHUB_APP_PRIVATE_KEY_PATH: str | None = Field(
        default=None, description="Path to PEM private key file"
    )
    GITHUB_APP_PRIVATE_KEY: str | None = Field(
        default=None, description="Raw PEM private key string (alternative to path)"
    )
    GITHUB_WEBHOOK_SECRET: str | None = Field(default=None, description="GitHub Webhook Secret")
    GITHUB_CALLBACK_URL: str | None = Field(
        default=None, description="Callback URL for GitHub App installation redirect"
    )
    GITHUB_APP_SLUG: str | None = Field(
        default=None, description="GitHub App slug for direct installation URLs"
    )

    @property
    def is_github_configured(self) -> bool:
        """Return True if GitHub App integration is fully configured."""
        has_key = bool(self.GITHUB_APP_PRIVATE_KEY or self.GITHUB_APP_PRIVATE_KEY_PATH)
        return bool(self.GITHUB_APP_ID and self.GITHUB_APP_CLIENT_ID and has_key)

    # Email Service
    EMAIL_PROVIDER: Literal["development", "smtp", "console"] = Field(
        default="development",
        description="Email service provider. Defaults to development adapter.",
    )
    EMAIL_FROM: str = Field(default="noreply@mysde.local")
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/mysde_dev",
        description="SQLAlchemy database connection URI",
    )
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50)
    DB_POOL_PRE_PING: bool = Field(default=True)
    DB_POOL_TIMEOUT: int = Field(default=10, ge=1, le=60)

    # CORS
    CORS_ORIGINS: list[str] | str = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            origins = [
                origin.strip().rstrip("/")
                for origin in value.split(",")
                if origin.strip()
            ]
            return origins
        if isinstance(value, list):
            return [str(origin).strip().rstrip("/") for origin in value if str(origin).strip()]
        return ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        clean_val = value.strip()
        allowed_schemes = (
            "postgresql://",
            "postgresql+psycopg://",
            "postgresql+psycopg2://",
            "postgresql+asyncpg://",
            "sqlite://",
            "sqlite+aiosqlite://",
        )
        if not any(clean_val.startswith(scheme) for scheme in allowed_schemes):
            raise ValueError(
                f"DATABASE_URL must start with one of {allowed_schemes}. Got: {clean_val.split('://')[0]}://"
            )
        return clean_val

    @model_validator(mode="after")
    def validate_production_constraints(self) -> "Settings":
        if self.APP_ENV == "production":
            if len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 characters long in production environments"
                )
            # Enforce cookie security in production
            self.COOKIE_SECURE = True
        return self

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        val_upper = value.upper()
        if val_upper not in levels:
            raise ValueError(f"LOG_LEVEL must be one of {levels}. Got '{value}'")
        return val_upper


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings loaded from environment/.env."""
    return Settings()
