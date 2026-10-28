import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.planning import ImplementationPlan, PlanningRun
from app.models.task import Task
from app.planning.graph.state import PlanningState
from app.planning.graph.workflow import build_planning_graph
from app.planning.llm.base import BaseLLMProvider
from app.planning.llm.factory import get_llm_provider
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


class PlanningService:
    """Service layer managing LangGraph planning execution, persistence, and querying."""

    def __init__(
        self,
        llm_provider: BaseLLMProvider | None = None,
        retrieval_service: RetrievalService | None = None,
    ):
        self.llm_provider = llm_provider
        self.retrieval_service = retrieval_service

    async def trigger_planning_run(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        force_new: bool = False,
        run_synchronous: bool = False,
    ) -> PlanningRun:
        """
        Creates and queues a planning run.
        If force_new is False and an active run exists (queued/running), returns the existing run.
        If run_synchronous is True (e.g., for deterministic tests), awaits execution before returning.
        """
        # 1. Verify task belongs to workspace
        task = db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.workspace_id == workspace_id,
            )
        )
        if not task:
            raise ValueError("Task not found in authorized workspace")

        # 2. Check for active run
        if not force_new:
            active_run = db.scalar(
                select(PlanningRun)
                .where(
                    PlanningRun.task_id == task_id,
                    PlanningRun.workspace_id == workspace_id,
                    PlanningRun.status.in_(["queued", "running"]),
                )
                .order_by(desc(PlanningRun.started_at))
            )
            if active_run:
                logger.info(f"Returning existing active planning run {active_run.id} for task {task_id}")
                return active_run

        # 3. Create queued run record
        repo_id = task.repository_id
        if not repo_id and task.project and task.project.repository_id:
            repo_id = task.project.repository_id

        run = PlanningRun(
            workspace_id=workspace_id,
            task_id=task_id,
            repository_id=repo_id,
            requested_by_user_id=user_id,
            status="queued",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        run_id = run.id

        if run_synchronous:
            await self._execute_run(run_id, workspace_id, task_id, user_id, db)
            db.refresh(run)
        else:
            # Spawn non-blocking background task
            asyncio.create_task(
                self._execute_run_background(run_id, workspace_id, task_id, user_id)
            )

        return run

    async def _execute_run_background(
        self,
        run_id: uuid.UUID,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Background runner acquiring a dedicated DB session."""
        db: Session = SessionLocal()
        try:
            await self._execute_run(run_id, workspace_id, task_id, user_id, db)
        except Exception as e:
            logger.error(f"Unhandled error in background planning run {run_id}: {e}", exc_info=True)
            try:
                run = db.scalar(select(PlanningRun).where(PlanningRun.id == run_id))
                if run and run.status not in ["completed", "failed", "needs_context"]:
                    run.status = "failed"
                    run.error_summary = f"Background execution failed: {str(e)}"
                    run.completed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:
                db.rollback()
        finally:
            db.close()

    async def _execute_run(
        self,
        run_id: uuid.UUID,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        db: Session,
    ) -> PlanningState:
        """Executes the compiled LangGraph workflow."""
        llm = self.llm_provider or get_llm_provider()
        retrieval = self.retrieval_service or RetrievalService()

        graph = build_planning_graph(
            db=db,
            llm_provider=llm,
            retrieval_service=retrieval,
        )

        initial_state: PlanningState = {
            "run_id": str(run_id),
            "task_id": str(task_id),
            "workspace_id": str(workspace_id),
            "repository_id": None,
            "user_id": str(user_id),
            "task_title": "",
            "task_description": "",
            "base_commit_sha": None,
            "is_repo_indexed": False,
            "evidence": [],
            "prompt_text": "",
            "plan": None,
            "validation_errors": [],
            "retry_count": 0,
            "max_retries": getattr(settings, "PLANNING_MAX_RETRIES", 2),
            "status": "queued",
            "error_summary": None,
            "model_metadata": {},
            "timings": {},
        }

        final_state = await graph.ainvoke(initial_state)
        return final_state

    def get_run(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> PlanningRun | None:
        """Fetch a single planning run enforcing workspace isolation."""
        return db.scalar(
            select(PlanningRun).where(
                PlanningRun.id == run_id,
                PlanningRun.workspace_id == workspace_id,
            )
        )

    def get_plan(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        plan_id: uuid.UUID,
    ) -> ImplementationPlan | None:
        """Fetch an implementation plan by ID enforcing workspace isolation."""
        return db.scalar(
            select(ImplementationPlan).where(
                ImplementationPlan.id == plan_id,
                ImplementationPlan.workspace_id == workspace_id,
            )
        )

    def get_latest_plan_for_task(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> ImplementationPlan | None:
        """Fetch the latest implementation plan for a task in workspace."""
        return db.scalar(
            select(ImplementationPlan)
            .where(
                ImplementationPlan.task_id == task_id,
                ImplementationPlan.workspace_id == workspace_id,
            )
            .order_by(desc(ImplementationPlan.created_at))
        )

    def list_plans_for_task(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[list[ImplementationPlan], int]:
        """List historical implementation plans for a task with pagination."""
        query = (
            select(ImplementationPlan)
            .where(
                ImplementationPlan.task_id == task_id,
                ImplementationPlan.workspace_id == workspace_id,
            )
            .order_by(desc(ImplementationPlan.created_at))
        )

        total_plans = len(list(db.scalars(query).all()))
        paginated_plans = list(db.scalars(query.limit(limit).offset(offset)).all())

        return paginated_plans, total_plans

    def cancel_run(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> PlanningRun:
        """Cancel an in-progress or queued planning run."""
        run = self.get_run(db, workspace_id, run_id)
        if not run:
            raise ValueError("Planning run not found in authorized workspace")

        if run.status in ["completed", "failed", "cancelled"]:
            return run

        run.status = "cancelled"
        run.completed_at = datetime.now(timezone.utc)
        run.error_summary = "Planning run was cancelled by user."
        db.commit()
        db.refresh(run)
        return run
