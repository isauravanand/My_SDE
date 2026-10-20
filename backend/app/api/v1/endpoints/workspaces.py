import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import (
    get_current_user,
    get_workspace_membership,
    validate_csrf,
)
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.workspace import (
    UpdateMemberRoleRequest,
    WorkspaceCreateRequest,
    WorkspaceMemberResponse,
    WorkspaceResponse,
)
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.get(
    "",
    response_model=list[WorkspaceResponse],
    summary="List all workspaces accessible to current user",
)
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[WorkspaceResponse]:
    workspaces_with_roles = WorkspaceService.list_user_workspaces(db=db, user=current_user)
    return [
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            role=role,
            created_at=ws.created_at,
        )
        for ws, role in workspaces_with_roles
    ]


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_csrf)],
    summary="Create a new workspace",
)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> WorkspaceResponse:
    workspace, role = WorkspaceService.create_workspace(
        db=db, user=current_user, name=payload.name
    )
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        owner_id=workspace.owner_id,
        role=role,
        created_at=workspace.created_at,
    )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Get single workspace details (requires membership)",
)
async def get_workspace(
    workspace_and_membership: tuple[Workspace, WorkspaceMembership] = Depends(
        get_workspace_membership
    ),
) -> WorkspaceResponse:
    workspace, membership = workspace_and_membership
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        owner_id=workspace.owner_id,
        role=membership.role,
        created_at=workspace.created_at,
    )


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberResponse],
    summary="List workspace members (requires membership)",
)
async def list_workspace_members(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[WorkspaceMemberResponse]:
    members = WorkspaceService.list_members(
        db=db, user=current_user, workspace_id=workspace_id
    )
    return [
        WorkspaceMemberResponse(
            id=membership.id,
            workspace_id=membership.workspace_id,
            user_id=member_user.id,
            email=member_user.email,
            full_name=member_user.full_name,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, member_user in members
    ]


@router.patch(
    "/{workspace_id}/members/{membership_id}",
    response_model=WorkspaceMemberResponse,
    dependencies=[Depends(validate_csrf)],
    summary="Update member role in workspace (requires owner or admin privileges)",
)
async def update_member_role(
    workspace_id: uuid.UUID,
    membership_id: uuid.UUID,
    payload: UpdateMemberRoleRequest,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> WorkspaceMemberResponse:
    updated_membership = WorkspaceService.update_member_role(
        db=db,
        actor_user=current_user,
        workspace_id=workspace_id,
        membership_id=membership_id,
        new_role=payload.role,
    )
    member_user = db.get(User, updated_membership.user_id)
    return WorkspaceMemberResponse(
        id=updated_membership.id,
        workspace_id=updated_membership.workspace_id,
        user_id=updated_membership.user_id,
        email=member_user.email if member_user else "",
        full_name=member_user.full_name if member_user else None,
        role=updated_membership.role,
        created_at=updated_membership.created_at,
    )
