import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    resolve_task_workspace,
    validate_csrf,
)
from app.db.session import get_db
from app.models.planning import ImplementationPlan, PlanningRun
from app.models.task import Task
from app.models.user import User
from app.schemas.planning import (
    ImplementationPlanResponse,
    PlanningRunDetailResponse,
    PlanningRunResponse,
    PlanningRunTriggerRequest,
)
from app.services.planning_service import PlanningService
from app.services.workspace import WorkspaceService

router = APIRouter(tags=["Planning Orchestration"])
planning_service = PlanningService()


def _format_plan_response(plan: ImplementationPlan) -> ImplementationPlanResponse:
    return ImplementationPlanResponse(
        id=plan.id,
        planning_run_id=plan.planning_run_id,
        schema_version=plan.schema_version,
        plan_data=plan.plan_data,
        created_at=plan.created_at,
    )


def _format_run_response(run: PlanningRun) -> PlanningRunResponse:
    return PlanningRunResponse(
        id=run.id,
        workspace_id=run.workspace_id,
        task_id=run.task_id,
        repository_id=run.repository_id,
        requested_by_user_id=run.requested_by_user_id,
        status=run.status,
        base_commit_sha=run.base_commit_sha,
        model_version=run.model_version,
        prompt_version=run.prompt_version,
        error_summary=run.error_summary,
        started_at=run.started_at,
        completed_at=run.completed_at,
        plan_id=run.plan.id if run.plan else None,
    )


# --- Task-scoped Planning Endpoints ---

@router.post(
    "/tasks/{task_id}/plan",
    response_model=PlanningRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger implementation planning for a software task",
)
async def trigger_task_planning(
    task_id: uuid.UUID,
    payload: PlanningRunTriggerRequest | None = None,
    task_and_workspace: tuple[Task, uuid.UUID] = Depends(resolve_task_workspace),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
) -> PlanningRunResponse:
    """Enqueues an explicit LangGraph workflow run to generate an implementation plan."""
    task, workspace_id = task_and_workspace
    req = payload or PlanningRunTriggerRequest()

    try:
        run = await planning_service.trigger_planning_run(
            db=db,
            workspace_id=workspace_id,
            task_id=task.id,
            user_id=current_user.id,
            force_new=req.force_new,
        )
        return _format_run_response(run)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/tasks/{task_id}/plan",
    response_model=ImplementationPlanResponse | None,
    summary="Get the latest implementation plan for a task",
)
async def get_latest_task_plan(
    task_id: uuid.UUID,
    task_and_workspace: tuple[Task, uuid.UUID] = Depends(resolve_task_workspace),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImplementationPlanResponse | None:
    """Retrieve the most recent validated implementation plan for this task."""
    task, workspace_id = task_and_workspace
    plan = planning_service.get_latest_plan_for_task(db, workspace_id, task.id)
    if not plan:
        return None
    return _format_plan_response(plan)


@router.get(
    "/tasks/{task_id}/plans",
    response_model=list[ImplementationPlanResponse],
    summary="List prior implementation plans for a task",
)
async def list_task_plans(
    task_id: uuid.UUID,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    task_and_workspace: tuple[Task, uuid.UUID] = Depends(resolve_task_workspace),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ImplementationPlanResponse]:
    """List historical implementation plans for this task with pagination."""
    task, workspace_id = task_and_workspace
    plans, _ = planning_service.list_plans_for_task(
        db=db,
        workspace_id=workspace_id,
        task_id=task.id,
        limit=limit,
        offset=offset,
    )
    return [_format_plan_response(p) for p in plans]


# --- Planning Run Management Endpoints ---

@router.get(
    "/planning/runs/{run_id}",
    response_model=PlanningRunDetailResponse,
    summary="Get planning run status and details",
)
async def get_planning_run(
    run_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlanningRunDetailResponse:
    """Retrieve the execution status, timings, and attached plan of a planning run."""
    WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    run = planning_service.get_run(db, workspace_id, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning run not found in authorized workspace.",
        )

    base_resp = _format_run_response(run)
    plan_resp = _format_plan_response(run.plan) if run.plan else None

    return PlanningRunDetailResponse(
        **base_resp.model_dump(),
        plan=plan_resp,
    )


@router.post(
    "/planning/runs/{run_id}/cancel",
    response_model=PlanningRunResponse,
    summary="Cancel an active planning run",
)
async def cancel_planning_run(
    run_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
) -> PlanningRunResponse:
    """Cancel a running or queued planning orchestration run."""
    WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    try:
        run = planning_service.cancel_run(db, workspace_id, run_id)
        return _format_run_response(run)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get(
    "/planning/plans/{plan_id}",
    response_model=ImplementationPlanResponse,
    summary="Get validated implementation plan by ID",
)
async def get_implementation_plan(
    plan_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImplementationPlanResponse:
    """Fetch a validated implementation plan by its primary key with workspace verification."""
    WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    plan = planning_service.get_plan(db, workspace_id, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Implementation plan not found in authorized workspace.",
        )
    return _format_plan_response(plan)
