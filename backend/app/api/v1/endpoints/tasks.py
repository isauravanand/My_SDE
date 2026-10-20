import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from app.api.deps import (
    get_current_user,
    resolve_task_workspace,
    validate_csrf,
)
from app.db.session import get_db
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskListResponse, TaskResponse, TaskUpdateRequest
from app.services.task import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks across a workspace with filters, search, and pagination",
)
async def list_tasks(
    workspace_id: uuid.UUID = Query(..., description="Target workspace ID"),
    project_id: uuid.UUID | None = Query(default=None, description="Optional project ID filter"),
    status: str | None = Query(default=None, description="Filter by status"),
    priority: str | None = Query(default=None, description="Filter by priority"),
    assignee_id: uuid.UUID | None = Query(default=None, description="Filter by assignee user ID"),
    search: str | None = Query(default=None, description="Search term for title or description"),
    include_archived: bool = Query(default=False, description="Include archived tasks"),
    sort_by: str = Query(default="created_at", description="Field to sort by"),
    sort_dir: str = Query(default="desc", description="Sort direction ('asc' or 'desc')"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> TaskListResponse:
    items, total = TaskService.list_tasks(
        db=db,
        user=current_user,
        workspace_id=workspace_id,
        project_id=project_id,
        status_filter=status,
        priority_filter=priority,
        assignee_id=assignee_id,
        search=search,
        include_archived=include_archived,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    return TaskListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get single task details (requires workspace membership)",
)
async def get_task(
    task_and_workspace: tuple[Task, uuid.UUID] = Depends(resolve_task_workspace),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> TaskResponse:
    task, workspace_id = task_and_workspace
    _, response = TaskService.get_task(
        db=db, user=current_user, workspace_id=workspace_id, task_id=task.id
    )
    return response


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(validate_csrf)],
    summary="Update task fields, status, or assignee",
)
async def update_task(
    payload: TaskUpdateRequest,
    task_and_workspace: tuple[Task, uuid.UUID] = Depends(resolve_task_workspace),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> TaskResponse:
    task, workspace_id = task_and_workspace
    return TaskService.update_task(
        db=db,
        user=current_user,
        workspace_id=workspace_id,
        task_id=task.id,
        payload=payload,
    )


@router.post(
    "/{task_id}/archive",
    response_model=TaskResponse,
    dependencies=[Depends(validate_csrf)],
    summary="Archive a task",
)
async def archive_task(
    task_and_workspace: tuple[Task, uuid.UUID] = Depends(resolve_task_workspace),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> TaskResponse:
    task, workspace_id = task_and_workspace
    return TaskService.archive_task(
        db=db, user=current_user, workspace_id=workspace_id, task_id=task.id
    )


@router.post(
    "/{task_id}/restore",
    response_model=TaskResponse,
    dependencies=[Depends(validate_csrf)],
    summary="Restore an archived task",
)
async def restore_task(
    task_and_workspace: tuple[Task, uuid.UUID] = Depends(resolve_task_workspace),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> TaskResponse:
    task, workspace_id = task_and_workspace
    return TaskService.restore_task(
        db=db, user=current_user, workspace_id=workspace_id, task_id=task.id
    )
