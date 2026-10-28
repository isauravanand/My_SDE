import logging

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.planning.graph.nodes import PlanningNodes
from app.planning.graph.state import PlanningState
from app.planning.llm.base import BaseLLMProvider
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


def build_planning_graph(
    db: Session,
    llm_provider: BaseLLMProvider | None = None,
    retrieval_service: RetrievalService | None = None,
):
    """
    Constructs and compiles the deterministic LangGraph workflow for implementation planning.
    Includes explicit conditional branching for missing context, unindexed repos, and bounded repair loops.
    """
    nodes = PlanningNodes(
        db=db,
        llm_provider=llm_provider,
        retrieval_service=retrieval_service,
    )

    workflow = StateGraph(PlanningState)

    # 1. Add all 8 explicit nodes
    workflow.add_node("load_task", nodes.load_task)
    workflow.add_node("validate_context", nodes.validate_context)
    workflow.add_node("retrieve_repository_context", nodes.retrieve_repository_context)
    workflow.add_node("analyze_task", nodes.analyze_task)
    workflow.add_node("generate_plan", nodes.generate_plan)
    workflow.add_node("validate_plan", nodes.validate_plan)
    workflow.add_node("persist_plan", nodes.persist_plan)
    workflow.add_node("finalize_run", nodes.finalize_run)

    # 2. Set entry point
    workflow.set_entry_point("load_task")

    # 3. Conditional routing after load_task
    def route_after_load_task(state: PlanningState) -> str:
        if state.get("status") == "failed":
            return "finalize_run"
        return "validate_context"

    workflow.add_conditional_edges(
        "load_task",
        route_after_load_task,
        {
            "finalize_run": "finalize_run",
            "validate_context": "validate_context",
        },
    )

    # 4. Conditional routing after validate_context
    def route_after_validate_context(state: PlanningState) -> str:
        status = state.get("status")
        if status in ["needs_context", "failed"]:
            return "finalize_run"
        if state.get("repository_id") and state.get("is_repo_indexed"):
            return "retrieve_repository_context"
        return "analyze_task"

    workflow.add_conditional_edges(
        "validate_context",
        route_after_validate_context,
        {
            "finalize_run": "finalize_run",
            "retrieve_repository_context": "retrieve_repository_context",
            "analyze_task": "analyze_task",
        },
    )

    # 5. Direct edge from retrieve_repository_context -> analyze_task
    workflow.add_edge("retrieve_repository_context", "analyze_task")

    # 6. Direct edge from analyze_task -> generate_plan
    workflow.add_edge("analyze_task", "generate_plan")

    # 7. Conditional edge after generate_plan (handle immediate fatal error)
    def route_after_generate_plan(state: PlanningState) -> str:
        if state.get("status") == "failed":
            return "finalize_run"
        return "validate_plan"

    workflow.add_conditional_edges(
        "generate_plan",
        route_after_generate_plan,
        {
            "finalize_run": "finalize_run",
            "validate_plan": "validate_plan",
        },
    )

    # 8. Conditional edge after validate_plan (repair loop vs persistence vs fatal)
    def route_after_validate_plan(state: PlanningState) -> str:
        status = state.get("status")
        if status == "validation_failed":
            return "generate_plan"
        if status == "failed":
            return "finalize_run"
        return "persist_plan"

    workflow.add_conditional_edges(
        "validate_plan",
        route_after_validate_plan,
        {
            "generate_plan": "generate_plan",
            "finalize_run": "finalize_run",
            "persist_plan": "persist_plan",
        },
    )

    # 9. Edge from persist_plan -> finalize_run
    workflow.add_edge("persist_plan", "finalize_run")

    # 10. Finalize run completes the graph
    workflow.add_edge("finalize_run", END)

    return workflow.compile()
