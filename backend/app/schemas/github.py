import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GitHubIntegrationStatusResponse(BaseModel):
    """Safe metadata describing GitHub App connection state for a workspace."""

    model_config = ConfigDict(from_attributes=True)

    is_configured: bool = Field(description="Whether the GitHub App credentials are set in environment")
    is_connected: bool = Field(description="Whether an active GitHub App installation is linked")
    installation_id: int | None = Field(default=None, description="GitHub App installation identifier")
    account_login: str | None = Field(default=None, description="GitHub user or organization name")
    account_type: str | None = Field(default=None, description="GitHub account type (User or Organization)")
    account_avatar_url: str | None = Field(default=None, description="Avatar URL of the linked account")
    status: str | None = Field(default=None, description="Installation status (active, uninstalled)")
    total_repositories: int = Field(default=0, description="Total repositories accessible to the installation")
    selected_repositories: int = Field(default=0, description="Total repositories selected for this workspace")
    last_synced_at: datetime | None = Field(default=None, description="Timestamp of the most recent sync")
    app_slug: str | None = Field(default=None, description="GitHub App slug for installation links")


class GitHubInstallUrlResponse(BaseModel):
    """Response containing a cryptographically secure installation URL."""

    install_url: str = Field(description="URL to redirect user to GitHub App installation flow")
    state: str = Field(description="Cryptographically secure single-use state token")


class GitHubRepositoryResponse(BaseModel):
    """Metadata for a connected GitHub repository."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    installation_id: uuid.UUID
    github_repo_id: int
    owner_login: str
    name: str
    full_name: str
    default_branch: str
    is_private: bool
    is_archived: bool
    is_selected: bool
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GitHubRepositoryListResponse(BaseModel):
    """Paginated list of repositories for a workspace."""

    items: list[GitHubRepositoryResponse]
    total: int
    limit: int
    offset: int


class GitHubRepositorySelectRequest(BaseModel):
    """Request payload to select or deselect a repository for use."""

    is_selected: bool = Field(description="Whether this repository should be active for workspace projects")
