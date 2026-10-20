import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import ActivityLogResponse, DashboardSummaryResponse
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    summary="Get aggregated dashboard metrics for an authorized workspace",
)
async def get_dashboard_summary(
    workspace_id: uuid.UUID = Query(..., description="Target workspace ID"),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> DashboardSummaryResponse:
    return DashboardService.get_summary(
        db=db, user=current_user, workspace_id=workspace_id
    )


@router.get(
    "/recent-activity",
    response_model=list[ActivityLogResponse],
    summary="Get real chronological activity events for an authorized workspace",
)
async def get_recent_activity(
    workspace_id: uuid.UUID = Query(..., description="Target workspace ID"),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[ActivityLogResponse]:
    return DashboardService.get_recent_activity(
        db=db, user=current_user, workspace_id=workspace_id, limit=limit
    )
