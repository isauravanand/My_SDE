import uuid
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.security import (
    CSRF_HEADER_NAME,
    constant_time_compare,
    hash_token,
)
from app.db.session import get_db
from app.models.project import Project
from app.models.session import Session as UserSession
from app.models.task import Task
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.workspace import WorkspaceService

settings = get_settings()


def get_current_session(
    mysde_session: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
) -> tuple[UserSession, User]:
    """Validate server-side session cookie and return active session and user."""
    if not mysde_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    token_digest = hash_token(mysde_session)
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_digest)
    )

    if not session or not session.is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or was revoked. Please log in again.",
        )

    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or disabled.",
        )

    return session, user


def get_current_user(
    session_and_user: tuple[UserSession, User] = Depends(get_current_session),
) -> User:
    """Dependency returning the authenticated user."""
    return session_and_user[1]


def get_current_user_session(
    session_and_user: tuple[UserSession, User] = Depends(get_current_session),
) -> UserSession:
    """Dependency returning the active session object."""
    return session_and_user[0]


def validate_csrf(
    request: Request,
    mysde_csrf: Annotated[str | None, Cookie()] = None,
    x_csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> None:
    """Verify CSRF token on state-changing requests authenticated via cookies.

    Requires X-CSRF-Token header matching the mysde_csrf cookie in constant time.
    """
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not mysde_csrf or not x_csrf_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing from cookie or request header.",
            )

        if not constant_time_compare(mysde_csrf, x_csrf_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token mismatch.",
            )


def get_workspace_membership(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> tuple[Workspace, WorkspaceMembership]:
    """Resolve workspace and verify the current user is an authorized member."""
    return WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)


def require_role(allowed_roles: list[str]):
    """Dependency factory checking that user holds one of the specified roles in the workspace."""

    def role_checker(
        workspace_and_membership: tuple[Workspace, WorkspaceMembership] = Depends(
            get_workspace_membership
        ),
    ) -> tuple[Workspace, WorkspaceMembership]:
        workspace, membership = workspace_and_membership
        if membership.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This operation requires one of the following roles: {', '.join(allowed_roles)}.",
            )
        return workspace, membership

    return role_checker


def resolve_project_workspace(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> tuple[Project, uuid.UUID]:
    """Resolve project and verify current user is a member of its owning workspace."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    WorkspaceService.get_workspace_for_user(db, current_user, project.workspace_id)
    return project, project.workspace_id


def resolve_task_workspace(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> tuple[Task, uuid.UUID]:
    """Resolve task and verify current user is a member of its owning workspace."""
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )
    WorkspaceService.get_workspace_for_user(db, current_user, task.workspace_id)
    return task, task.workspace_id
