import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, validate_csrf
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.github import (
    GitHubInstallUrlResponse,
    GitHubIntegrationStatusResponse,
    GitHubRepositoryListResponse,
    GitHubRepositoryResponse,
    GitHubRepositorySelectRequest,
)
from app.services.github_service import GitHubService
from app.services.github_webhook import GitHubWebhookHandler
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/integrations/github", tags=["integrations-github"])
github_service = GitHubService()
webhook_handler = GitHubWebhookHandler()
settings = get_settings()


@router.get("/status", response_model=GitHubIntegrationStatusResponse)
def get_github_status(
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve the current GitHub App integration status for the authorized workspace."""
    # Ensure current user has membership in workspace
    WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    return github_service.get_integration_status(db, workspace_id)


@router.get("/install", response_model=GitHubInstallUrlResponse)
def initiate_github_install(
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate GitHub App installation by generating a cryptographically secure state."""
    workspace, membership = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners and administrators can connect GitHub integrations.",
        )
    return github_service.initiate_installation(db, workspace, current_user)


@router.get("/callback")
def github_callback(
    state: str = Query(..., description="Single-use OAuth state token"),
    installation_id: int = Query(..., description="GitHub installation ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Validate installation state and link GitHub App installation to the workspace."""
    github_service.handle_callback(
        db=db, state=state, installation_id=installation_id, user=current_user
    )

    # Redirect user back to repositories dashboard on frontend
    redirect_target = f"{settings.FRONTEND_URL}/repositories?installed=true"
    return RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)


@router.get("/repositories", response_model=GitHubRepositoryListResponse)
def list_repositories(
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    search: str | None = Query(None, description="Search term on repository name"),
    is_selected: bool | None = Query(None, description="Filter by selection status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List connected GitHub repositories for the workspace."""
    WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    repos, total = github_service.list_repositories(
        db=db,
        workspace_id=workspace_id,
        search=search,
        is_selected=is_selected,
        limit=limit,
        offset=offset,
    )
    return GitHubRepositoryListResponse(
        items=[GitHubRepositoryResponse.model_validate(r) for r in repos],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/repositories/sync")
def sync_repositories(
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(validate_csrf),
):
    """Fetch updated repository metadata from GitHub for the active installation."""
    workspace, membership = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners and administrators can synchronize repositories.",
        )
    synced_count = github_service.sync_repositories(db, workspace.id, user_id=current_user.id)
    return {"message": "Repositories synchronized successfully", "synced_count": synced_count}


@router.patch("/repositories/{repository_id}", response_model=GitHubRepositoryResponse)
def toggle_repository_selection(
    repository_id: uuid.UUID,
    payload: GitHubRepositorySelectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(validate_csrf),
):
    """Select or deselect a repository for active use in workspace projects."""
    from app.models.github import GitHubRepository

    repo = db.get(GitHubRepository, repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )
    workspace, membership = WorkspaceService.get_workspace_for_user(db, current_user, repo.workspace_id)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners and administrators can manage repository selections.",
        )

    updated_repo = github_service.toggle_repository_selection(
        db=db, workspace_id=repo.workspace_id, repo_id=repository_id, is_selected=payload.is_selected
    )
    return GitHubRepositoryResponse.model_validate(updated_repo)


@router.post("/disconnect")
def disconnect_github(
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(validate_csrf),
):
    """Disconnect the GitHub App integration for this workspace."""
    workspace, membership = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners and administrators can disconnect integrations.",
        )
    github_service.disconnect_installation(db, workspace.id, current_user.id)
    return {"message": "GitHub App disconnected successfully"}


@router.post("/webhook")
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_hub_signature_256: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
    x_github_delivery: Annotated[str | None, Header(alias="X-GitHub-Delivery")] = None,
    x_github_event: Annotated[str | None, Header(alias="X-GitHub-Event")] = None,
):
    """Public webhook receiver verifying HMAC SHA-256 signature and handling events idempotently."""
    raw_body = await request.body()

    # 1. Verify HMAC signature
    if not webhook_handler.verify_signature(raw_body, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Hub-Signature-256 signature.",
        )

    if not x_github_event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-GitHub-Event header.",
        )

    # 2. Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from e

    # 3. Process event
    result = webhook_handler.process_webhook(
        db=db,
        delivery_id=x_github_delivery,
        event_type=x_github_event,
        payload=payload,
    )
    return result
