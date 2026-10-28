import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FailureCategory = Literal[
    "test_assertion_failure",
    "import_or_dependency_error",
    "syntax_error",
    "type_or_static_analysis_error",
    "lint_failure",
    "configuration_error",
    "environment_failure",
    "timeout",
    "resource_limit_exceeded",
    "network_denied",
    "sandbox_failure",
    "unknown",
]


class FailureClassification(BaseModel):
    """Categorized failure diagnosis derived from verified execution evidence."""

    category: FailureCategory
    verification_result_ids: list[uuid.UUID] = Field(default_factory=list)
    evidence_excerpt: str = Field(default="")
    is_repairable: bool
    reason: str
    uncertainty_annotation: str = Field(
        default="heuristic_analysis",
        description="Confidence or uncertainty annotation (qualitative, not a fake probability)",
    )


class RepairProposalSchema(BaseModel):
    """Structured repair proposal produced by the AI repair model."""

    change_summary: str = Field(description="Concise description of the proposed fix")
    root_cause_hypothesis: str = Field(description="Evidence-supported explanation of defect cause")
    evidence_supporting_hypothesis: str = Field(description="Direct citations to failure evidence")
    proposed_files: list[str] = Field(description="File paths intended for modification")
    unified_diff: str = Field(description="Unified git diff to apply to current working copy")
    expected_effect: str = Field(description="Anticipated effect on failing checks")
    verification_checks: list[str] = Field(
        default_factory=list,
        description="Allowed verification checks expected to validate the fix",
    )
    known_risks: str = Field(description="Potential side-effects, regressions, or uncertainties")


class RepairAttemptResponse(BaseModel):
    """API representation of an individual repair attempt."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repair_run_id: uuid.UUID
    attempt_number: int
    failure_classification: dict[str, Any]
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    root_cause_hypothesis: str | None = None
    proposal_status: str
    proposed_change_summary: str | None = None
    patch_hash: str | None = None
    validation_result: dict[str, Any] | None = None
    application_result: str | None = None
    verification_results_summary: list[dict[str, Any]] | None = None
    duration_seconds: float
    created_at: datetime


class RepairRunResponse(BaseModel):
    """API representation of a bounded repair run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    execution_run_id: uuid.UUID
    task_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    status: str
    max_attempts: int
    consumed_attempts: int
    max_model_calls: int
    consumed_model_calls: int
    started_at: datetime
    deadline_at: datetime
    completed_at: datetime | None = None
    final_outcome: str | None = None
    safe_error_summary: str | None = None
    attempts: list[RepairAttemptResponse] = Field(default_factory=list)


class StartRepairRequest(BaseModel):
    """Payload to trigger an explicit bounded repair attempt for a failed execution."""

    verification_commands: list[str] | None = Field(
        default=None,
        description="Optional subset of permitted verification checks to rerun",
    )


class RepairSummaryResponse(BaseModel):
    """Summary of completed or terminal repair workflow."""

    repair_run_id: uuid.UUID
    final_outcome: str
    total_attempts: int
    duration_seconds: float
    initial_patch_hash: str | None = None
    final_patch_hash: str | None = None
    checks_summary: list[dict[str, Any]] = Field(default_factory=list)
