from typing import Any, TypedDict


class RepairState(TypedDict, total=False):
    """
    Typed graph state passed between nodes in the LangGraph repair workflow.
    Carries bounded metadata, attempt counters, failure classifications, and verification outcomes.
    Never stores secrets, raw tokens, or unbounded repository dumps.
    """

    # Identifiers & Tenancy
    execution_run_id: str
    repair_run_id: str
    task_id: str
    workspace_id: str
    user_id: str

    # Budget & Execution Bounds
    attempt_number: int
    max_attempts: int
    consumed_attempts: int
    max_model_calls: int
    consumed_model_calls: int
    deadline_at_iso: str

    # Working Copy & Patch State
    current_patch: str
    code_context: str

    # Failure Evidence & Classification
    verification_result_ids: list[str]
    failure_classification: dict[str, Any]
    evidence: list[dict[str, Any]]

    # Repair Proposal & Validation
    proposal: dict[str, Any] | None
    proposal_valid: bool
    validation_error: str | None
    patch_hash: str | None

    # Sandbox Verification State
    checks_to_run: list[str]
    application_result: str | None
    verification_results: list[dict[str, Any]]
    all_passed: bool

    # Workflow Status & Observability
    status: str  # analyzing, repairing, running_checks, completed, failed, budget_exhausted, non_repairable, cancelled
    final_outcome: str | None  # passed, failed, partially_verified, repair_exhausted, infrastructure_failure, cancelled, non_repairable
    safe_error_summary: str | None
