from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ChangeType = Literal["create", "modify", "delete", "test", "configuration", "investigation"]
LocationStatus = Literal["verified_existing", "proposed_new", "hypothetical_investigation"]
PlanningConfidence = Literal["high", "medium", "low", "unverified"]
PlanningRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "needs_context",
]


class PlanEvidenceItem(BaseModel):
    """Normalized evidence record extracted from Code RAG chunks."""

    evidence_id: str = Field(..., description="Unique evidence identifier within the plan, e.g. 'ev-1'")
    repository_id: str | None = Field(None, description="Repository UUID")
    commit_sha: str | None = Field(None, description="Indexed commit SHA of the source chunk")
    file_path: str = Field(..., description="Repository-relative file path")
    start_line: int = Field(..., ge=1, description="1-indexed starting line")
    end_line: int = Field(..., ge=1, description="1-indexed ending line")
    source_chunk_id: str | None = Field(None, description="UUID of source RepoCodeChunk in database")
    excerpt: str = Field(..., description="Short untrusted source code snippet")
    relevance_summary: str | None = Field(None, description="Why this evidence is relevant to the task")


class ImplementationStep(BaseModel):
    """Structured step within an implementation plan."""

    step_id: str = Field(..., description="Stable step identifier, e.g. 'step-1'")
    order: int = Field(..., ge=1, description="Execution sequence number")
    title: str = Field(..., min_length=3, description="Brief step title")
    description: str = Field(..., min_length=10, description="Detailed explanation of the change")
    rationale: str = Field(..., description="Why this step is necessary")
    relevant_files: list[str] = Field(default_factory=list, description="Target file paths")
    change_type: ChangeType = Field(..., description="Classification of the change")
    dependencies: list[str] = Field(default_factory=list, description="Step IDs that must complete first")
    verification_instructions: str = Field(..., description="Specific verification instructions or test commands")
    evidence_refs: list[str] = Field(default_factory=list, description="Referenced evidence_id items")
    confidence: PlanningConfidence = Field(
        ...,
        description="Qualitative assessment: high (supported by exact code), medium (partial code match), low (speculative), unverified",
    )
    location_status: LocationStatus = Field(
        ...,
        description="Location category: verified_existing (code cited), proposed_new (new file), hypothetical_investigation (needs inspection)",
    )


class ImplementationPlanSchema(BaseModel):
    """Strictly validated structured implementation plan produced by the LangGraph agent."""

    schema_version: str = Field(default="mysde.plan.v1", description="Plan schema specification version")
    task_id: str = Field(..., description="Task UUID")
    repository_id: str | None = Field(None, description="Repository UUID if repository-grounded")
    base_commit_sha: str | None = Field(None, description="Commit SHA used for retrieval grounding")
    summary: str = Field(..., min_length=10, description="Executive summary of the implementation strategy")
    task_understanding: str = Field(..., min_length=10, description="Structured interpretation of the requirements")
    assumptions: list[str] = Field(default_factory=list, description="Architectural or domain assumptions made")
    unknowns: list[str] = Field(default_factory=list, description="Unresolved questions or gaps in information")
    affected_components: list[str] = Field(default_factory=list, description="Modules, APIs, or layers touched")
    implementation_steps: list[ImplementationStep] = Field(..., min_length=1, description="Ordered steps")
    testing_strategy: str = Field(..., min_length=10, description="Comprehensive test and validation approach")
    risks: list[str] = Field(default_factory=list, description="Potential side effects or regression vectors")
    security_considerations: list[str] = Field(default_factory=list, description="Security, auth, and boundary notes")
    acceptance_criteria: list[str] = Field(default_factory=list, description="Checklist for task completion")
    evidence: list[PlanEvidenceItem] = Field(default_factory=list, description="Normalized evidence collection")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_metadata: dict[str, Any] = Field(default_factory=dict, description="Model, temperature, token counts")

    @model_validator(mode="after")
    def validate_plan_consistency(self) -> "ImplementationPlanSchema":
        """Validate evidence references and step ordering consistency."""
        valid_evidence_ids = {e.evidence_id for e in self.evidence}
        valid_step_ids = {s.step_id for s in self.implementation_steps}

        for step in self.implementation_steps:
            # Verify evidence references point to actual retrieved evidence
            for ref in step.evidence_refs:
                if ref not in valid_evidence_ids:
                    raise ValueError(
                        f"Step '{step.step_id}' references unknown evidence ID '{ref}'. "
                        f"Available: {sorted(valid_evidence_ids)}"
                    )

            # If location_status is verified_existing, require at least one valid evidence reference
            # unless no repository was connected
            if step.location_status == "verified_existing" and self.repository_id and not step.evidence_refs:
                raise ValueError(
                    f"Step '{step.step_id}' is marked as 'verified_existing' but contains no evidence_refs. "
                    "Existing code claims must reference retrieved evidence or be marked as proposed_new / hypothetical_investigation."
                )

            # Verify dependencies point to existing steps
            for dep in step.dependencies:
                if dep not in valid_step_ids:
                    raise ValueError(f"Step '{step.step_id}' references unknown dependency step '{dep}'.")

        return self


# --- API Request & Response Schemas ---

class PlanningRunTriggerRequest(BaseModel):
    """Request payload to initiate a planning run for a task."""

    force_new: bool = Field(default=False, description="If True, cancel or ignore existing active run")


class ImplementationPlanResponse(BaseModel):
    """Full implementation plan response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    planning_run_id: UUID
    schema_version: str
    plan_data: ImplementationPlanSchema
    created_at: datetime


class PlanningRunResponse(BaseModel):
    """Summary of a planning run execution."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    task_id: UUID
    repository_id: UUID | None
    requested_by_user_id: UUID
    status: PlanningRunStatus
    base_commit_sha: str | None
    model_version: str | None
    prompt_version: str | None
    error_summary: str | None
    started_at: datetime
    completed_at: datetime | None
    plan_id: UUID | None = None


class PlanningRunDetailResponse(PlanningRunResponse):
    """Detailed planning run response with associated plan if completed."""

    plan: ImplementationPlanResponse | None = None
