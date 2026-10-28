from typing import Any, TypedDict


class PlanningState(TypedDict, total=False):
    """
    Typed graph state passed between nodes in the LangGraph planning workflow.
    Carries only necessary context, identifiers, normalized evidence, and validation feedback.
    """

    # Identifiers & Ownership
    run_id: str
    task_id: str
    workspace_id: str
    repository_id: str | None
    user_id: str

    # Task Context
    task_title: str
    task_description: str

    # Repository & Retrieval State
    base_commit_sha: str | None
    is_repo_indexed: bool
    evidence: list[dict[str, Any]]  # List of PlanEvidenceItem dictionaries
    prompt_text: str

    # Plan Generation & Validation State
    plan: dict[str, Any] | None  # Serialized ImplementationPlanSchema
    validation_errors: list[str]
    retry_count: int
    max_retries: int

    # Execution Status & Observability
    status: str  # queued, running, completed, failed, cancelled, needs_context
    error_summary: str | None
    model_metadata: dict[str, Any]
    timings: dict[str, float]
