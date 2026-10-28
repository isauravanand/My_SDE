import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PublishingApprovalRequest(BaseModel):
    """Payload to explicitly approve a verified patch artifact for publishing."""

    patch_hash: str | None = Field(default=None, description="Exact SHA-256 hash of the patch artifact being approved")


class StartPublishingRequest(BaseModel):
    """Payload to initiate Git branch pushing and PR creation."""

    base_branch: str | None = Field(default=None, description="Target base branch on repository (defaults to repo default or main)")
    pr_title: str | None = Field(default=None, description="Optional custom Pull Request title")
    pr_body: str | None = Field(default=None, description="Optional custom Pull Request description")


class PublishingRunResponse(BaseModel):
    """Details and status of a Git publishing and Pull Request creation lifecycle."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    task_id: uuid.UUID
    execution_run_id: uuid.UUID
    repository_id: uuid.UUID
    patch_artifact_id: uuid.UUID
    status: str = Field(..., description="Status: pending_approval, approved, preparing, pushing_branch, creating_pr, completed, failed, stale_base_conflict")
    base_branch: str
    base_commit_sha: str
    head_branch: str
    head_commit_sha: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    pr_state: str = "open"
    safe_error_summary: str | None = None
    changed_files: list[dict[str, Any]] = Field(default_factory=list)
    approved_patch_hash: str
    approved_at: datetime | None = None
    published_at: datetime | None = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime


class PublishingPrecheckResponse(BaseModel):
    """Status assessment of all prerequisites required prior to publishing to GitHub."""

    can_publish: bool
    is_approved: bool
    approved_patch_hash: str | None = None
    current_patch_hash: str
    is_patch_stale: bool = False
    verification_passed: bool
    passed_checks_count: int
    failed_checks_count: int
    execution_base_sha: str
    remote_base_sha: str | None = None
    is_base_stale: bool = False
    blockers: list[str] = Field(default_factory=list)
    repository_full_name: str | None = None
    default_branch: str = "main"
