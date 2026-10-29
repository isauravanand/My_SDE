import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    validate_csrf,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.execution import (
    ApprovePatchRequest,
    ExecutionRunResponse,
    PatchArtifactResponse,
    RejectPatchRequest,
    StartExecutionRequest,
)
from app.services.execution_service import ExecutionService, ExecutionServiceError

router = APIRouter(tags=["Isolated Execution & Verification"])


# --- Task-scoped Execution Routes ---

@router.post(
    "/tasks/{task_id}/execution",
    response_model=ExecutionRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start an execution preparation run for a task",
    dependencies=[Depends(validate_csrf)],
)
def start_task_execution(
    task_id: uuid.UUID,
    payload: StartExecutionRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ExecutionService(db)
    req_plan_id = payload.plan_id if payload else None
    req_commands = payload.verification_commands if payload else None
    try:
        run = service.start_execution_run(
            task_id=task_id,
            user_id=current_user.id,
            plan_id=req_plan_id,
            verification_commands=req_commands,
        )
        return run
    except ExecutionServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/tasks/{task_id}/executions",
    response_model=list[ExecutionRunResponse],
    summary="List execution runs for a task",
)
def list_task_executions(
    task_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ExecutionService(db)
    try:
        runs = service.list_task_execution_runs(
            task_id=task_id,
            user_id=current_user.id,
            limit=limit,
            offset=offset,
        )
        return runs
    except ExecutionServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


# --- Run-scoped Execution Routes ---

@router.get(
    "/execution/runs/{run_id}",
    response_model=ExecutionRunResponse,
    summary="Get execution run details and results",
)
def get_execution_run_detail(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ExecutionService(db)
    try:
        run = service.get_execution_run(run_id=run_id, user_id=current_user.id)
        return run
    except ExecutionServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/execution/runs/{run_id}/patch",
    response_model=PatchArtifactResponse,
    summary="Get patch artifact and diff for an execution run",
)
def get_execution_patch_artifact(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ExecutionService(db)
    try:
        run = service.get_execution_run(run_id=run_id, user_id=current_user.id)
        if not run.patches:
            raise HTTPException(status_code=404, detail="No patch artifact found for this run.")
        return run.patches[0]
    except ExecutionServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/execution/runs/{run_id}/preview",
    summary="Get inlined live screen preview of patched repository HTML/CSS",
)
def get_execution_preview_endpoint(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ExecutionService(db)
    try:
        return service.get_execution_preview(run_id=run_id, user_id=current_user.id)
    except ExecutionServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post(
    "/execution/runs/{run_id}/approve",
    response_model=ExecutionRunResponse,
    summary="Approve patch proposal and trigger sandbox application & verification",
    dependencies=[Depends(validate_csrf)],
)
def approve_patch_and_run(
    run_id: uuid.UUID,
    payload: ApprovePatchRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ExecutionService(db)
    run_checks = payload.run_checks if payload else True
    commands = payload.verification_commands if payload else None
    try:
        run = service.approve_and_execute(
            run_id=run_id,
            user_id=current_user.id,
            run_checks=run_checks,
            verification_commands=commands,
        )
        return run
    except ExecutionServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post(
    "/execution/runs/{run_id}/reject",
    response_model=ExecutionRunResponse,
    summary="Reject proposed patch and terminate execution run",
    dependencies=[Depends(validate_csrf)],
)
def reject_patch_proposal(
    run_id: uuid.UUID,
    payload: RejectPatchRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ExecutionService(db)
    reason = payload.reason if payload else None
    try:
        run = service.reject_patch(
            run_id=run_id,
            user_id=current_user.id,
            reason=reason,
        )
        return run
    except ExecutionServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post(
    "/execution/runs/{run_id}/cancel",
    response_model=ExecutionRunResponse,
    summary="Cancel active execution run",
    dependencies=[Depends(validate_csrf)],
)
def cancel_execution_run_endpoint(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ExecutionService(db)
    try:
        run = service.cancel_execution_run(run_id=run_id, user_id=current_user.id)
        return run
    except ExecutionServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
