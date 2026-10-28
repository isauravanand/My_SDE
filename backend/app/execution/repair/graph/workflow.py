import logging

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.execution.repair.generator import RepairGenerator
from app.execution.repair.graph.nodes import RepairNodes
from app.execution.repair.graph.state import RepairState
from app.execution.sandbox.base import BaseSandbox

logger = logging.getLogger(__name__)


def build_repair_graph(
    db: Session,
    sandbox_override: BaseSandbox | None = None,
    repair_generator: RepairGenerator | None = None,
):
    """
    Constructs and compiles the deterministic LangGraph workflow for automated bounded repair.
    Guarantees termination through server-side attempt limits, deadlines, and model call bounds.
    """
    nodes = RepairNodes(
        db=db,
        sandbox_override=sandbox_override,
        repair_generator=repair_generator,
    )

    workflow = StateGraph(RepairState)

    # 1. Add all 10 explicit nodes
    workflow.add_node("load_execution_run", nodes.load_execution_run)
    workflow.add_node("collect_failure_evidence", nodes.collect_failure_evidence)
    workflow.add_node("classify_failure", nodes.classify_failure)
    workflow.add_node("retrieve_relevant_context", nodes.retrieve_relevant_context)
    workflow.add_node("propose_repair", nodes.propose_repair)
    workflow.add_node("validate_repair_patch", nodes.validate_repair_patch)
    workflow.add_node("apply_repair_patch", nodes.apply_repair_patch)
    workflow.add_node("rerun_verification", nodes.rerun_verification)
    workflow.add_node("evaluate_outcome", nodes.evaluate_outcome)
    workflow.add_node("finalize_repair_run", nodes.finalize_repair_run)

    # 2. Set entry point
    workflow.set_entry_point("load_execution_run")

    # 3. Conditional after load_execution_run
    def route_after_load(state: RepairState) -> str:
        if state.get("status") in {"failed", "cancelled"}:
            return "finalize_repair_run"
        return "collect_failure_evidence"

    workflow.add_conditional_edges(
        "load_execution_run",
        route_after_load,
        {
            "finalize_repair_run": "finalize_repair_run",
            "collect_failure_evidence": "collect_failure_evidence",
        },
    )

    # 4. Direct: collect_failure_evidence -> classify_failure
    workflow.add_edge("collect_failure_evidence", "classify_failure")

    # 5. Conditional after classify_failure
    def route_after_classify(state: RepairState) -> str:
        if state.get("status") in {"non_repairable", "failed"}:
            return "finalize_repair_run"
        return "retrieve_relevant_context"

    workflow.add_conditional_edges(
        "classify_failure",
        route_after_classify,
        {
            "finalize_repair_run": "finalize_repair_run",
            "retrieve_relevant_context": "retrieve_relevant_context",
        },
    )

    # 6. Direct: retrieve_relevant_context -> propose_repair
    workflow.add_edge("retrieve_relevant_context", "propose_repair")

    # 7. Conditional after propose_repair
    def route_after_propose(state: RepairState) -> str:
        if state.get("status") == "budget_exhausted" or not state.get("proposal_valid"):
            return "evaluate_outcome"
        return "validate_repair_patch"

    workflow.add_conditional_edges(
        "propose_repair",
        route_after_propose,
        {
            "evaluate_outcome": "evaluate_outcome",
            "validate_repair_patch": "validate_repair_patch",
        },
    )

    # 8. Conditional after validate_repair_patch
    def route_after_validate(state: RepairState) -> str:
        if not state.get("proposal_valid"):
            return "evaluate_outcome"
        return "apply_repair_patch"

    workflow.add_conditional_edges(
        "validate_repair_patch",
        route_after_validate,
        {
            "evaluate_outcome": "evaluate_outcome",
            "apply_repair_patch": "apply_repair_patch",
        },
    )

    # 9. Direct: apply_repair_patch -> rerun_verification
    workflow.add_edge("apply_repair_patch", "rerun_verification")

    # 10. Direct: rerun_verification -> evaluate_outcome
    workflow.add_edge("rerun_verification", "evaluate_outcome")

    # 11. Conditional after evaluate_outcome (Loop back vs Complete vs Exhausted)
    def route_after_evaluate(state: RepairState) -> str:
        status = state.get("status")
        if status in {"completed", "budget_exhausted", "failed", "cancelled"}:
            return "finalize_repair_run"
        # If budget remains and still analyzing, loop back to collect evidence & attempt again
        return "collect_failure_evidence"

    workflow.add_conditional_edges(
        "evaluate_outcome",
        route_after_evaluate,
        {
            "finalize_repair_run": "finalize_repair_run",
            "collect_failure_evidence": "collect_failure_evidence",
        },
    )

    # 12. Direct: finalize_repair_run -> END
    workflow.add_edge("finalize_repair_run", END)

    return workflow.compile()
