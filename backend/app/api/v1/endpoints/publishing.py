import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, validate_csrf
from app.db.session import get_db
from app.models.execution import ExecutionRun
from app.models.publishing import PublishingRun
from app.models.user import User
from app.schemas.publishing import (
    PublishingApprovalRequest,
    PublishingPrecheckResponse,
    PublishingRunResponse,
    StartPublishingRequest,
)
from app.services.publishing_service import publishing_service
from app.services.workspace import WorkspaceService

router = APIRouter(tags=["publishing"])


def _resolve_workspace_id_from_run(db: Session, run_id: uuid.UUID, ws_id: uuid.UUID | None) -> uuid.UUID:
    if ws_id:
        return ws_id
    run_ws = db.scalar(select(ExecutionRun.workspace_id).where(ExecutionRun.id == run_id))
    if not run_ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution run not found.",
        )
    return run_ws


@router.get(
    "/executions/{run_id}/publish/precheck",
    response_model=PublishingPrecheckResponse,
    summary="Evaluate prerequisites for publishing to GitHub",
)
def precheck_publishing(
    run_id: uuid.UUID,
    workspace_id: uuid.UUID | None = Query(default=None, description="Active workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assess whether an execution run meets all safety, verification, and approval requirements for publishing."""
    resolved_ws_id = _resolve_workspace_id_from_run(db, run_id, workspace_id)
    WorkspaceService.get_workspace_for_user(db, current_user, resolved_ws_id)
    return publishing_service.precheck_publishing(
        db=db,
        execution_run_id=run_id,
        workspace_id=resolved_ws_id,
        user=current_user,
    )


@router.post(
    "/executions/{run_id}/publish/approve",
    response_model=PublishingRunResponse,
    summary="Approve verified patch for GitHub publication",
)
def approve_publishing(
    run_id: uuid.UUID,
    payload: PublishingApprovalRequest | None = None,
    workspace_id: uuid.UUID | None = Query(default=None, description="Active workspace ID"),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    """Explicitly approve the exact verified patch artifact hash for Git branch publishing and PR creation."""
    resolved_ws_id = _resolve_workspace_id_from_run(db, run_id, workspace_id)
    workspace, membership = WorkspaceService.get_workspace_for_user(db, current_user, resolved_ws_id)
    patch_hash = payload.patch_hash if payload else None
    return publishing_service.approve_publishing(
        db=db,
        execution_run_id=run_id,
        patch_hash=patch_hash,
        workspace_id=workspace.id,
        user=current_user,
    )


@router.post(
    "/executions/{run_id}/publish",
    response_model=PublishingRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish approved patch to GitHub branch and create Pull Request",
)
def publish_to_github(
    run_id: uuid.UUID,
    payload: StartPublishingRequest | None = None,
    workspace_id: uuid.UUID | None = Query(default=None, description="Active workspace ID"),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    """Execute Git branch creation, commit push, and Pull Request creation for an approved execution."""
    resolved_ws_id = _resolve_workspace_id_from_run(db, run_id, workspace_id)
    workspace, membership = WorkspaceService.get_workspace_for_user(db, current_user, resolved_ws_id)
    base_branch = payload.base_branch if payload else None
    pr_title = payload.pr_title if payload else None
    pr_body = payload.pr_body if payload else None
    return publishing_service.publish_to_github(
        db=db,
        execution_run_id=run_id,
        workspace_id=workspace.id,
        user=current_user,
        base_branch_override=base_branch,
        custom_pr_title=pr_title,
        custom_pr_body=pr_body,
    )


@router.get(
    "/executions/{run_id}/publish",
    response_model=PublishingRunResponse | None,
    summary="Get publishing and Pull Request status for an execution run",
)
def get_execution_publishing(
    run_id: uuid.UUID,
    workspace_id: uuid.UUID | None = Query(default=None, description="Active workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve the current publishing run and GitHub Pull Request metadata."""
    resolved_ws_id = _resolve_workspace_id_from_run(db, run_id, workspace_id)
    WorkspaceService.get_workspace_for_user(db, current_user, resolved_ws_id)
    publishing_run = db.scalar(
        select(PublishingRun)
        .where(
            PublishingRun.execution_run_id == run_id,
            PublishingRun.workspace_id == resolved_ws_id,
        )
        .order_by(PublishingRun.created_at.desc())
    )
    return publishing_run


@router.post(
    "/publishing/{publishing_id}/retry",
    response_model=PublishingRunResponse,
    summary="Retry a failed or interrupted publishing run",
)
def retry_publishing(
    publishing_id: uuid.UUID,
    workspace_id: uuid.UUID | None = Query(default=None, description="Active workspace ID"),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
):
    """Safely retry publishing after a recoverable API timeout or failure."""
    publishing_run = db.scalar(
        select(PublishingRun).where(PublishingRun.id == publishing_id)
    )
    if not publishing_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publishing run not found.",
        )
    resolved_ws_id = workspace_id or publishing_run.workspace_id
    workspace, membership = WorkspaceService.get_workspace_for_user(db, current_user, resolved_ws_id)

    return publishing_service.publish_to_github(
        db=db,
        execution_run_id=publishing_run.execution_run_id,
        workspace_id=workspace.id,
        user=current_user,
        base_branch_override=publishing_run.base_branch,
        custom_pr_title=publishing_run.pr_title,
        custom_pr_body=publishing_run.pr_body,
    )
