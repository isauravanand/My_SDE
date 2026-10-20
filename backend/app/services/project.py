import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.project import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from app.services.activity import ActivityService
from app.services.auth import slugify
from app.services.workspace import WorkspaceService


class ProjectService:
    """Service handling multi-tenant project lifecycle and querying."""

    @staticmethod
    def list_projects(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        status_filter: str | None = "active",
    ) -> list[ProjectResponse]:
        """List all projects in the workspace with task counts (requires workspace membership)."""
        # Ensure user belongs to workspace
        WorkspaceService.get_workspace_for_user(db, user, workspace_id)

        query = select(Project).where(Project.workspace_id == workspace_id)
        if status_filter and status_filter.lower() != "all":
            query = query.where(Project.status == status_filter.lower())
        query = query.order_by(Project.created_at.desc())

        projects = db.scalars(query).all()

        # Aggregate task counts
        result: list[ProjectResponse] = []
        for p in projects:
            total_tasks = db.scalar(
                select(func.count(Task.id)).where(
                    Task.project_id == p.id, Task.archived_at.is_(None)
                )
            ) or 0
            open_tasks = db.scalar(
                select(func.count(Task.id)).where(
                    Task.project_id == p.id,
                    Task.status.in_(["backlog", "todo", "in_progress", "in_review"]),
                    Task.archived_at.is_(None),
                )
            ) or 0

            result.append(
                ProjectResponse(
                    id=p.id,
                    workspace_id=p.workspace_id,
                    name=p.name,
                    slug=p.slug,
                    description=p.description,
                    status=p.status,
                    repository_id=p.repository_id,
                    created_by=p.created_by,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                    archived_at=p.archived_at,
                    task_count=total_tasks,
                    open_task_count=open_tasks,
                )
            )
        return result

    @staticmethod
    def create_project(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        payload: ProjectCreateRequest,
    ) -> ProjectResponse:
        """Create a new project in the specified workspace."""
        WorkspaceService.get_workspace_for_user(db, user, workspace_id)

        base_slug = slugify(payload.name)
        # Ensure slug uniqueness within the workspace
        slug = base_slug
        existing = db.scalar(
            select(Project).where(
                Project.workspace_id == workspace_id, Project.slug == slug
            )
        )
        if existing:
            slug = f"{base_slug}-{secrets.token_hex(2)}"

        if payload.repository_id:
            from app.models.github import GitHubRepository

            repo = db.scalar(
                select(GitHubRepository).where(
                    GitHubRepository.id == payload.repository_id,
                    GitHubRepository.workspace_id == workspace_id,
                )
            )
            if not repo:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selected repository does not exist in this workspace.",
                )

        project = Project(
            workspace_id=workspace_id,
            name=payload.name.strip(),
            slug=slug,
            description=payload.description.strip() if payload.description else None,
            repository_id=payload.repository_id,
            status="active",
            created_by=user.id,
        )
        db.add(project)
        db.flush()

        # Log activity
        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user.id,
            event_type="project_created",
            resource_type="project",
            resource_id=project.id,
            metadata={"name": project.name, "slug": project.slug},
        )

        db.commit()
        db.refresh(project)

        return ProjectResponse(
            id=project.id,
            workspace_id=project.workspace_id,
            name=project.name,
            slug=project.slug,
            description=project.description,
            status=project.status,
            repository_id=project.repository_id,
            created_by=project.created_by,
            created_at=project.created_at,
            updated_at=project.updated_at,
            archived_at=project.archived_at,
            task_count=0,
            open_task_count=0,
        )

    @staticmethod
    def get_project(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> tuple[Project, ProjectResponse]:
        """Fetch project ensuring user has workspace access (returns 404 on mismatch)."""
        WorkspaceService.get_workspace_for_user(db, user, workspace_id)

        project = db.scalar(
            select(Project).where(
                Project.id == project_id, Project.workspace_id == workspace_id
            )
        )
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        total_tasks = db.scalar(
            select(func.count(Task.id)).where(
                Task.project_id == project.id, Task.archived_at.is_(None)
            )
        ) or 0
        open_tasks = db.scalar(
            select(func.count(Task.id)).where(
                Task.project_id == project.id,
                Task.status.in_(["backlog", "todo", "in_progress", "in_review"]),
                Task.archived_at.is_(None),
            )
        ) or 0

        response = ProjectResponse(
            id=project.id,
            workspace_id=project.workspace_id,
            name=project.name,
            slug=project.slug,
            description=project.description,
            status=project.status,
            repository_id=project.repository_id,
            created_by=project.created_by,
            created_at=project.created_at,
            updated_at=project.updated_at,
            archived_at=project.archived_at,
            task_count=total_tasks,
            open_task_count=open_tasks,
        )
        return project, response

    @staticmethod
    def update_project(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        payload: ProjectUpdateRequest,
    ) -> ProjectResponse:
        """Update project details."""
        project, _ = ProjectService.get_project(db, user, workspace_id, project_id)

        if payload.name is not None:
            project.name = payload.name.strip()
        if payload.description is not None:
            project.description = (
                payload.description.strip() if payload.description else None
            )
        if payload.repository_id is not None:
            from app.models.github import GitHubRepository

            repo = db.scalar(
                select(GitHubRepository).where(
                    GitHubRepository.id == payload.repository_id,
                    GitHubRepository.workspace_id == workspace_id,
                )
            )
            if not repo:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selected repository does not exist in this workspace.",
                )
            project.repository_id = payload.repository_id

        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user.id,
            event_type="project_updated",
            resource_type="project",
            resource_id=project.id,
            metadata={"name": project.name},
        )

        db.commit()
        db.refresh(project)
        _, response = ProjectService.get_project(db, user, workspace_id, project_id)
        return response

    @staticmethod
    def archive_project(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> ProjectResponse:
        """Mark project as archived."""
        project, _ = ProjectService.get_project(db, user, workspace_id, project_id)
        project.status = "archived"
        project.archived_at = datetime.now(timezone.utc)

        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user.id,
            event_type="project_archived",
            resource_type="project",
            resource_id=project.id,
            metadata={"name": project.name},
        )

        db.commit()
        db.refresh(project)
        _, response = ProjectService.get_project(db, user, workspace_id, project_id)
        return response

    @staticmethod
    def restore_project(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> ProjectResponse:
        """Restore archived project to active status."""
        project, _ = ProjectService.get_project(db, user, workspace_id, project_id)
        project.status = "active"
        project.archived_at = None

        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user.id,
            event_type="project_restored",
            resource_type="project",
            resource_id=project.id,
            metadata={"name": project.name},
        )

        db.commit()
        db.refresh(project)
        _, response = ProjectService.get_project(db, user, workspace_id, project_id)
        return response
