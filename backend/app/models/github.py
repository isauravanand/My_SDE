import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class GitHubInstallation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Represents a GitHub App installation linked to a MySDE workspace."""

    __tablename__ = "github_installations"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_workspace_github_installation"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    installation_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(64), default="User", nullable=False)
    account_avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="active", index=True, nullable=False
    )  # "active", "uninstalled", "suspended"
    permissions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    uninstalled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", backref="github_installation")
    repositories: Mapped[list["GitHubRepository"]] = relationship(
        "GitHubRepository",
        back_populates="installation",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<GitHubInstallation id={self.id} installation_id={self.installation_id} account={self.account_login}>"


class GitHubRepository(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Metadata for a repository accessible through a workspace's GitHub App installation."""

    __tablename__ = "github_repositories"
    __table_args__ = (
        UniqueConstraint("workspace_id", "github_repo_id", name="uq_workspace_github_repo_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    installation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("github_installations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    github_repo_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )
    owner_login: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), default="main", nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_selected: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True, nullable=False
    )  # Whether chosen for MySDE workspace projects
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    installation: Mapped["GitHubInstallation"] = relationship(
        "GitHubInstallation", back_populates="repositories"
    )

    def __repr__(self) -> str:
        return f"<GitHubRepository id={self.id} full_name={self.full_name} selected={self.is_selected}>"


class GitHubOAuthState(Base, UUIDPrimaryKeyMixin):
    """Cryptographically secure, short-lived single-use state for GitHub App install flow."""

    __tablename__ = "github_oauth_states"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    state_token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    user: Mapped["User"] = relationship("User")
    workspace: Mapped["Workspace"] = relationship("Workspace")

    def __repr__(self) -> str:
        return f"<GitHubOAuthState token={self.state_token[:8]}... expired={self.consumed_at is not None}>"


class GitHubWebhookDelivery(Base, UUIDPrimaryKeyMixin):
    """Durable record of received GitHub webhook delivery IDs for idempotency."""

    __tablename__ = "github_webhook_deliveries"

    delivery_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="processed", nullable=False
    )  # "processed", "ignored", "failed"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<GitHubWebhookDelivery delivery_id={self.delivery_id} event={self.event_type}>"
