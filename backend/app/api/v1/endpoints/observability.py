import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, validate_csrf
from app.db.session import get_db
from app.models.user import User
from app.schemas.observability import (
    ObservabilityMetricsResponse,
    ObservabilityRunSummary,
    RecoverStaleRunsResponse,
    RunTraceResponse,
)
from app.services.observability_service import ObservabilityService
from app.services.run_recovery import RunRecoveryService
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/observability", tags=["Observability & Metrics"])


@router.get(
    "/runs/{run_id}/trace",
    response_model=RunTraceResponse,
    summary="Get end-to-end trace and timeline for an agent run",
)
def get_run_trace(
    run_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(..., description="Active workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RunTraceResponse:
    """Retrieve full lifecycle trace across planning, execution, verification, repair, and publishing."""
    workspace, _ = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    return ObservabilityService.get_run_trace(
        db=db,
        execution_run_id=run_id,
        workspace_id=workspace.id,
    )


@router.get(
    "/metrics",
    response_model=ObservabilityMetricsResponse,
    summary="Get aggregate reliability and performance metrics for a workspace",
)
def get_workspace_metrics(
    workspace_id: uuid.UUID = Query(..., description="Active workspace ID"),
    time_window_days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ObservabilityMetricsResponse:
    """Calculate reliability, success rates, failure categories, and model metrics for an authorized workspace."""
    workspace, _ = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    return ObservabilityService.get_workspace_metrics(
        db=db,
        workspace_id=workspace.id,
        time_window_days=time_window_days,
    )


@router.get(
    "/runs",
    response_model=list[ObservabilityRunSummary],
    summary="List agent runs for an authorized workspace with filtering",
)
def list_workspace_runs(
    workspace_id: uuid.UUID = Query(..., description="Active workspace ID"),
    status: str | None = Query(default=None, description="Filter by run status"),
    date_from: datetime | None = Query(default=None, description="Start date filter"),
    date_to: datetime | None = Query(default=None, description="End date filter"),
    limit: int = Query(default=50, ge=1, le=100, description="Max items to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ObservabilityRunSummary]:
    """Retrieve paginated and filtered agent execution runs for an authorized workspace."""
    workspace, _ = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    return ObservabilityService.list_workspace_runs(
        db=db,
        workspace_id=workspace.id,
        status_filter=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.post(
    "/recover-stale",
    response_model=RecoverStaleRunsResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger recovery of abandoned or interrupted agent runs",
    dependencies=[Depends(validate_csrf)],
)
def recover_stale_runs(
    workspace_id: uuid.UUID = Query(..., description="Active workspace ID"),
    timeout_minutes: int = Query(default=15, ge=5, le=120, description="Stale threshold in minutes"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecoverStaleRunsResponse:
    """Clean up and transition abandoned in-flight runs into safe terminal states."""
    workspace, _ = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    return RunRecoveryService.recover_stale_runs(
        db=db,
        workspace_id=workspace.id,
        timeout_minutes=timeout_minutes,
        actor_id=current_user.id,
    )
