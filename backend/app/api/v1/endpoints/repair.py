import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, validate_csrf
from app.db.session import get_db
from app.models.user import User
from app.schemas.repair import (
    RepairRunResponse,
    RepairSummaryResponse,
    StartRepairRequest,
)
from app.services.repair_service import RepairService, RepairServiceError

router = APIRouter(tags=["Bounded AI Repair Loops"])


@router.post(
    "/executions/{run_id}/repair",
    response_model=RepairRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start an automated bounded repair run for a failed execution",
    dependencies=[Depends(validate_csrf)],
)
def start_execution_repair(
    run_id: uuid.UUID,
    payload: StartRepairRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RepairService(db)
    req_commands = payload.verification_commands if payload else None
    try:
        repair_run = service.start_repair_run(
            execution_run_id=run_id,
            user_id=current_user.id,
            verification_commands=req_commands,
        )
        return repair_run
    except RepairServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/executions/{run_id}/repair",
    response_model=RepairRunResponse | None,
    summary="Get the latest repair run for an execution run",
)
def get_latest_repair_for_execution(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RepairService(db)
    try:
        latest = service.get_latest_repair_for_execution(
            execution_run_id=run_id,
            user_id=current_user.id,
        )
        return latest
    except RepairServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/repairs/{repair_id}",
    response_model=RepairRunResponse,
    summary="Get a specific repair run and its attempt history",
)
def get_repair_run(
    repair_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RepairService(db)
    try:
        repair_run = service.get_repair_run(
            repair_run_id=repair_id,
            user_id=current_user.id,
        )
        return repair_run
    except RepairServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post(
    "/repairs/{repair_id}/cancel",
    response_model=RepairRunResponse,
    summary="Cancel an active repair run",
    dependencies=[Depends(validate_csrf)],
)
def cancel_repair_run(
    repair_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RepairService(db)
    try:
        repair_run = service.cancel_repair_run(
            repair_run_id=repair_id,
            user_id=current_user.id,
        )
        return repair_run
    except RepairServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/repairs/{repair_id}/summary",
    response_model=RepairSummaryResponse,
    summary="Get summary metrics and check outcome for a repair run",
)
def get_repair_summary(
    repair_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RepairService(db)
    try:
        summary = service.get_repair_summary(
            repair_run_id=repair_id,
            user_id=current_user.id,
        )
        return summary
    except RepairServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
