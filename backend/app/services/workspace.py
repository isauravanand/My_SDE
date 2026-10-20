import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.auth import slugify


class WorkspaceService:
    """Service handling multi-tenant workspace lifecycle and membership permissions."""

    @staticmethod
    def list_user_workspaces(db: Session, user: User) -> list[tuple[Workspace, str]]:
        """Return all workspaces the user is a member of, along with their role."""
        query = (
            select(Workspace, WorkspaceMembership.role)
            .join(WorkspaceMembership, Workspace.id == WorkspaceMembership.workspace_id)
            .where(WorkspaceMembership.user_id == user.id)
            .order_by(Workspace.created_at.asc())
        )
        return list(db.execute(query).all())

    @staticmethod
    def create_workspace(db: Session, user: User, name: str) -> tuple[Workspace, str]:
        """Create a new workspace with the authenticated user as owner."""
        base_slug = slugify(name)
        slug = f"{base_slug}-{secrets.token_hex(3)}"

        workspace = Workspace(
            name=name.strip(),
            slug=slug,
            owner_id=user.id,
        )
        db.add(workspace)
        db.flush()

        membership = WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
        )
        db.add(membership)
        db.commit()
        db.refresh(workspace)

        return workspace, "owner"

    @staticmethod
    def get_workspace_for_user(
        db: Session, user: User, workspace_id: uuid.UUID
    ) -> tuple[Workspace, WorkspaceMembership]:
        """Fetch workspace and verify the user has membership.

        Returns 404 instead of 403 to prevent resource enumeration.
        """
        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user.id,
            )
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found.",
            )

        workspace = db.get(Workspace, workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found.",
            )

        return workspace, membership

    @staticmethod
    def list_members(
        db: Session, user: User, workspace_id: uuid.UUID
    ) -> list[tuple[WorkspaceMembership, User]]:
        """List all members of a workspace (requires membership)."""
        # Ensure user belongs to workspace
        WorkspaceService.get_workspace_for_user(db, user, workspace_id)

        query = (
            select(WorkspaceMembership, User)
            .join(User, WorkspaceMembership.user_id == User.id)
            .where(WorkspaceMembership.workspace_id == workspace_id)
            .order_by(WorkspaceMembership.created_at.asc())
        )
        return list(db.execute(query).all())

    @staticmethod
    def update_member_role(
        db: Session,
        actor_user: User,
        workspace_id: uuid.UUID,
        membership_id: uuid.UUID,
        new_role: str,
    ) -> WorkspaceMembership:
        """Update role of an existing member (requires owner or admin privileges)."""
        workspace, actor_membership = WorkspaceService.get_workspace_for_user(
            db, actor_user, workspace_id
        )

        # Only owners and admins can manage roles
        if actor_membership.role not in {"owner", "admin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify member roles.",
            )

        target_membership = db.get(WorkspaceMembership, membership_id)
        if not target_membership or target_membership.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership record not found.",
            )

        # Owner protection rule: Workspace owner cannot have their role modified
        if target_membership.user_id == workspace.owner_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The workspace owner's role cannot be modified.",
            )

        # Only owner can assign or modify other admins
        if target_membership.role == "admin" and actor_membership.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the workspace owner can modify an admin's role.",
            )

        target_membership.role = new_role
        db.commit()
        db.refresh(target_membership)
        return target_membership
