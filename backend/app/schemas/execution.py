from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ExecutionStatus = Literal[
    "queued",
    "preparing",
    "awaiting_patch_approval",
    "applying_patch",
    "running_checks",
    "completed",
    "failed",
    "cancel_requested",
    "cancelled",
    "timed_out",
    "cleanup_failed",
]

PatchValidationStatus = Literal["valid", "invalid", "rejected", "applied"]

VerificationCheckStatus = Literal["passed", "failed", "timed_out", "skipped", "error"]


class FileChangeMetadata(BaseModel):
    """Normalized metadata for a single file altered by a patch."""

    file_path: str = Field(..., description="Target file path relative to repository root")
    change_type: Literal["modify", "add", "delete", "rename"] = Field("modify")
    additions: int = Field(0, ge=0)
    deletions: int = Field(0, ge=0)
    old_path: str | None = None
    new_path: str | None = None


class PatchValidationResult(BaseModel):
    """Output produced by server-side patch syntax and security policy inspection."""

    is_valid: bool = Field(...)
    error_message: str | None = None
    patch_hash: str = Field(..., description="SHA-256 fingerprint of the patch text")
    changed_files: list[FileChangeMetadata] = Field(default_factory=list)
    changed_files_count: int = Field(0, ge=0)
    additions_count: int = Field(0, ge=0)
    deletions_count: int = Field(0, ge=0)


class PatchArtifactResponse(BaseModel):
    """Detailed representation of a validated unified diff patch."""

    id: UUID
    execution_run_id: UUID
    patch_hash: str
    validation_status: str
    validation_error: str | None = None
    raw_diff: str
    changed_files_count: int
    additions_count: int
    deletions_count: int
    changed_files: list[dict[str, Any]]
    is_approved: bool
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationResultResponse(BaseModel):
    """Recorded result of an approved verification command run in the sandbox."""

    id: UUID
    execution_run_id: UUID
    verification_type: str
    command_name: str
    command_args: list[str]
    exit_code: int
    status: str
    duration_seconds: float
    stdout_excerpt: str
    stderr_excerpt: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExecutionRunResponse(BaseModel):
    """Complete summary of an isolated execution and verification run."""

    id: UUID
    workspace_id: UUID
    task_id: UUID
    repository_id: UUID | None = None
    plan_id: UUID
    requested_by_user_id: UUID
    base_commit_sha: str
    status: ExecutionStatus
    sandbox_provider: str
    sandbox_image: str
    safe_error_summary: str | None = None
    cleanup_status: str
    started_at: datetime
    completed_at: datetime | None = None
    patches: list[PatchArtifactResponse] = Field(default_factory=list)
    verification_results: list[VerificationResultResponse] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StartExecutionRequest(BaseModel):
    """Payload to initiate a new execution preparation run from a validated plan."""

    plan_id: UUID | None = Field(None, description="Optional plan UUID. Defaults to task's latest active plan.")
    verification_commands: list[str] | None = Field(
        None,
        description="Optional list of permitted verification command identifiers (e.g. ['pytest', 'ruff_check'])",
    )


class ApprovePatchRequest(BaseModel):
    """Payload to approve a proposed patch and trigger sandbox application & checks."""

    run_checks: bool = Field(True, description="Whether to proceed with permitted verification checks after applying")
    verification_commands: list[str] | None = Field(
        None,
        description="Optional override list of permitted verification commands to execute",
    )


class RejectPatchRequest(BaseModel):
    """Payload to reject a proposed patch."""

    reason: str | None = Field(None, max_length=500, description="Optional rejection reason")
