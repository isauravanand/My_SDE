import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StageTimelineEvent(BaseModel):
    """Discrete lifecycle event in an agent run timeline."""
    stage: str = Field(..., description="Stage name (planning, execution, verification, repair, publishing)")
    event: str = Field(..., description="Description of lifecycle transition")
    status: str = Field(..., description="Status at this event")
    timestamp: datetime = Field(..., description="Timestamp of event occurrence")
    duration_seconds: float | None = Field(default=None, description="Stage duration if completed")
    details: dict[str, Any] = Field(default_factory=dict, description="Sanitized non-sensitive event details")


class ModelUsageMetadata(BaseModel):
    """Metadata regarding model provider invocations. Honest representation of missing/unavailable tokens."""
    model_name: str | None = None
    calls_count: int = 0
    prompt_tokens: int | str = "unavailable"
    completion_tokens: int | str = "unavailable"
    estimated_cost_usd: float | str = "unavailable"


class RunTraceResponse(BaseModel):
    """End-to-end tracing view of an agent execution run from planning to publishing."""
    execution_run_id: uuid.UUID
    workspace_id: uuid.UUID
    task_id: uuid.UUID
    task_title: str
    task_type: str
    repository_name: str | None = None
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    sandbox_provider: str
    sandbox_image: str
    safe_error_summary: str | None = None

    planning: dict[str, Any] | None = None
    patch: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    repair: dict[str, Any] | None = None
    publishing: dict[str, Any] | None = None

    timeline: list[StageTimelineEvent] = Field(default_factory=list)
    model_usage: dict[str, ModelUsageMetadata] = Field(default_factory=dict)


class ObservabilityMetricsResponse(BaseModel):
    """Aggregate reliability and performance metrics for an authorized workspace."""
    workspace_id: uuid.UUID
    time_window_days: int
    total_runs: int
    successful_runs: int
    failed_runs: int
    cancelled_runs: int
    timed_out_runs: int
    success_rate_percent: float | None = Field(
        default=None,
        description="Calculated as (successful_runs / total_terminal_runs) * 100",
    )
    failure_categories: dict[str, int] = Field(default_factory=dict)
    total_repairs: int
    repairs_succeeded: int
    average_durations_seconds: dict[str, float] = Field(default_factory=dict)
    model_usage_summary: dict[str, int] = Field(default_factory=dict)


class ObservabilityRunSummary(BaseModel):
    """Summary item for the workspace agent runs list."""
    id: uuid.UUID
    task_id: uuid.UUID
    task_title: str
    task_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    verification_passed: bool | None = None
    repair_attempts: int = 0
    pr_number: int | None = None
    pr_url: str | None = None
    safe_error_summary: str | None = None


class RecoverStaleRunsResponse(BaseModel):
    """Outcome of recovering abandoned or interrupted agent runs."""
    recovered_executions: int
    recovered_repairs: int
    recovered_publishing: int
    message: str
