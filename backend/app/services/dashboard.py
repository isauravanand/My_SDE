import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.execution import ExecutionRun
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.dashboard import ActivityLogResponse, DashboardSummaryResponse
from app.services.workspace import WorkspaceService


class DashboardService:
    """Service aggregating workspace dashboard metrics and recent activity."""

    @staticmethod
    def get_summary(
        db: Session, user: User, workspace_id: uuid.UUID
    ) -> DashboardSummaryResponse:
        """Calculate real statistics for the specified authorized workspace."""
        WorkspaceService.get_workspace_for_user(db, user, workspace_id)

        # 1. Total active projects
        total_projects = db.scalar(
            select(func.count(Project.id)).where(
                Project.workspace_id == workspace_id, Project.status == "active"
            )
        ) or 0

        # 2. Open tasks (backlog, todo, in_progress, in_review)
        open_tasks = db.scalar(
            select(func.count(Task.id)).where(
                Task.workspace_id == workspace_id,
                Task.status.in_(["backlog", "todo", "in_progress", "in_review"]),
                Task.archived_at.is_(None),
            )
        ) or 0

        # 3. Tasks in progress
        in_progress_tasks = db.scalar(
            select(func.count(Task.id)).where(
                Task.workspace_id == workspace_id,
                Task.status == "in_progress",
                Task.archived_at.is_(None),
            )
        ) or 0

        # 4. Completed tasks
        completed_tasks = db.scalar(
            select(func.count(Task.id)).where(
                Task.workspace_id == workspace_id,
                Task.status == "done",
                Task.archived_at.is_(None),
            )
        ) or 0

        # 5. Total agent execution runs
        total_agent_runs = db.scalar(
            select(func.count(ExecutionRun.id)).where(
                ExecutionRun.workspace_id == workspace_id,
            )
        ) or 0

        return DashboardSummaryResponse(
            total_projects=total_projects,
            open_tasks=open_tasks,
            in_progress_tasks=in_progress_tasks,
            completed_tasks=completed_tasks,
            agent_runs=total_agent_runs,
        )

    @staticmethod
    def get_recent_activity(
        db: Session, user: User, workspace_id: uuid.UUID, limit: int = 20
    ) -> list[ActivityLogResponse]:
        """Fetch recent activity logs within the workspace."""
        WorkspaceService.get_workspace_for_user(db, user, workspace_id)

        query = (
            select(ActivityLog)
            .where(ActivityLog.workspace_id == workspace_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(min(limit, 50))
        )
        logs = db.scalars(query).all()

        return [
            ActivityLogResponse(
                id=log.id,
                workspace_id=log.workspace_id,
                actor_id=log.actor_id,
                actor_name=log.actor.full_name if log.actor else None,
                actor_email=log.actor.email if log.actor else None,
                event_type=log.event_type,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                metadata_json=log.metadata_json,
                created_at=log.created_at,
            )
            for log in logs
        ]
