import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.schemas.task import TaskCreateRequest, TaskResponse, TaskUpdateRequest
from app.services.activity import ActivityService
from app.services.workspace import WorkspaceService


class TaskService:
    """Service handling multi-tenant task lifecycle, querying, and verification."""

    @staticmethod
    def _to_response(task: Task, project_name: str | None = None) -> TaskResponse:
        """Helper to build TaskResponse including relational metadata."""
        p_name = project_name or (task.project.name if task.project else None)
        assignee_name = task.assignee.full_name if task.assignee else None
        assignee_email = task.assignee.email if task.assignee else None

        return TaskResponse(
            id=task.id,
            workspace_id=task.workspace_id,
            project_id=task.project_id,
            project_name=p_name,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            task_type=task.task_type,
            created_by=task.created_by,
            assignee_id=task.assignee_id,
            assignee_name=assignee_name,
            assignee_email=assignee_email,
            due_at=task.due_at,
            completed_at=task.completed_at,
            archived_at=task.archived_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @staticmethod
    def _verify_assignee(db: Session, workspace_id: uuid.UUID, assignee_id: uuid.UUID) -> User:
        """Verify that an assigned user is an active member of the workspace."""
        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == assignee_id,
            )
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignee must be a member of the workspace.",
            )
        user = db.get(User, assignee_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignee account is inactive or not found.",
            )
        return user

    @staticmethod
    def list_tasks(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        status_filter: str | None = None,
        priority_filter: str | None = None,
        assignee_id: uuid.UUID | None = None,
        search: str | None = None,
        include_archived: bool = False,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TaskResponse], int]:
        """List and filter tasks within a workspace or project with pagination."""
        WorkspaceService.get_workspace_for_user(db, user, workspace_id)

        query = select(Task).where(Task.workspace_id == workspace_id)

        if project_id:
            # Verify project belongs to workspace
            proj = db.scalar(
                select(Project).where(
                    Project.id == project_id, Project.workspace_id == workspace_id
                )
            )
            if not proj:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found in this workspace.",
                )
            query = query.where(Task.project_id == project_id)

        if not include_archived:
            query = query.where(Task.archived_at.is_(None))

        if status_filter and status_filter.lower() != "all":
            query = query.where(Task.status == status_filter.lower())

        if priority_filter and priority_filter.lower() != "all":
            query = query.where(Task.priority == priority_filter.lower())

        if assignee_id:
            query = query.where(Task.assignee_id == assignee_id)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(or_(Task.title.ilike(term), Task.description.ilike(term)))

        # Total count before pagination
        count_query = select(func.count()).select_from(query.subquery())
        total = db.scalar(count_query) or 0

        # Sorting
        sort_column = getattr(Task, sort_by, Task.created_at)
        if sort_dir.lower() == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Pagination
        query = query.limit(min(limit, 100)).offset(max(offset, 0))
        tasks = db.scalars(query).all()

        return [TaskService._to_response(t) for t in tasks], total

    @staticmethod
    def create_task(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        payload: TaskCreateRequest,
    ) -> TaskResponse:
        """Create a new task under a project."""
        WorkspaceService.get_workspace_for_user(db, user, workspace_id)

        # Check project belongs to workspace
        project = db.scalar(
            select(Project).where(
                Project.id == project_id, Project.workspace_id == workspace_id
            )
        )
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found in this workspace.",
            )

        # Check project is not archived
        if project.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create tasks in an archived project. Restore the project first.",
            )

        # Check assignee
        if payload.assignee_id:
            TaskService._verify_assignee(db, workspace_id, payload.assignee_id)

        now = datetime.now(timezone.utc)
        completed_at = now if payload.status == "done" else None

        task = Task(
            workspace_id=workspace_id,
            project_id=project_id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            status=payload.status,
            priority=payload.priority,
            task_type=payload.task_type,
            created_by=user.id,
            assignee_id=payload.assignee_id,
            due_at=payload.due_at,
            completed_at=completed_at,
        )
        db.add(task)
        db.flush()

        # Activity log
        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user.id,
            event_type="task_created",
            resource_type="task",
            resource_id=task.id,
            metadata={"title": task.title, "project_name": project.name, "status": task.status},
        )

        db.commit()
        db.refresh(task)
        return TaskService._to_response(task, project_name=project.name)

    @staticmethod
    def get_task(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> tuple[Task, TaskResponse]:
        """Fetch task ensuring workspace access (returns 404 on mismatch)."""
        WorkspaceService.get_workspace_for_user(db, user, workspace_id)

        task = db.scalar(
            select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
        )
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found.",
            )
        return task, TaskService._to_response(task)

    @staticmethod
    def update_task(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
        payload: TaskUpdateRequest,
    ) -> TaskResponse:
        """Apply partial updates to a task, enforcing status and assignee rules."""
        task, _ = TaskService.get_task(db, user, workspace_id, task_id)
        old_status = task.status
        old_assignee_id = task.assignee_id

        if payload.title is not None:
            task.title = payload.title.strip()
        if payload.description is not None:
            task.description = payload.description.strip() if payload.description else None
        if payload.priority is not None:
            task.priority = payload.priority
        if payload.task_type is not None:
            task.task_type = payload.task_type
        if payload.due_at is not None:
            task.due_at = payload.due_at

        if payload.assignee_id is not None:
            TaskService._verify_assignee(db, workspace_id, payload.assignee_id)
            task.assignee_id = payload.assignee_id

        # Status transition handling
        if payload.status is not None and payload.status != old_status:
            task.status = payload.status
            now = datetime.now(timezone.utc)
            if payload.status == "done":
                task.completed_at = now
                ActivityService.log_activity(
                    db=db,
                    workspace_id=workspace_id,
                    actor_id=user.id,
                    event_type="task_completed",
                    resource_type="task",
                    resource_id=task.id,
                    metadata={"title": task.title},
                )
            else:
                if old_status == "done":
                    task.completed_at = None
                    ActivityService.log_activity(
                        db=db,
                        workspace_id=workspace_id,
                        actor_id=user.id,
                        event_type="task_reopened",
                        resource_type="task",
                        resource_id=task.id,
                        metadata={"title": task.title, "new_status": payload.status},
                    )
                ActivityService.log_activity(
                    db=db,
                    workspace_id=workspace_id,
                    actor_id=user.id,
                    event_type="task_status_changed",
                    resource_type="task",
                    resource_id=task.id,
                    metadata={"title": task.title, "old_status": old_status, "new_status": payload.status},
                )
        else:
            if payload.assignee_id is not None and payload.assignee_id != old_assignee_id:
                ActivityService.log_activity(
                    db=db,
                    workspace_id=workspace_id,
                    actor_id=user.id,
                    event_type="task_assigned",
                    resource_type="task",
                    resource_id=task.id,
                    metadata={"title": task.title},
                )
            else:
                ActivityService.log_activity(
                    db=db,
                    workspace_id=workspace_id,
                    actor_id=user.id,
                    event_type="task_updated",
                    resource_type="task",
                    resource_id=task.id,
                    metadata={"title": task.title},
                )

        db.commit()
        db.refresh(task)
        return TaskService._to_response(task)

    @staticmethod
    def archive_task(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        """Archive task."""
        task, _ = TaskService.get_task(db, user, workspace_id, task_id)
        task.archived_at = datetime.now(timezone.utc)

        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user.id,
            event_type="task_archived",
            resource_type="task",
            resource_id=task.id,
            metadata={"title": task.title},
        )

        db.commit()
        db.refresh(task)
        return TaskService._to_response(task)

    @staticmethod
    def restore_task(
        db: Session,
        user: User,
        workspace_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        """Restore archived task."""
        task, _ = TaskService.get_task(db, user, workspace_id, task_id)
        task.archived_at = None

        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user.id,
            event_type="task_restored",
            resource_type="task",
            resource_id=task.id,
            metadata={"title": task.title},
        )

        db.commit()
        db.refresh(task)
        return TaskService._to_response(task)
