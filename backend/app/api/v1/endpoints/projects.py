import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import (
    get_current_user,
    resolve_project_workspace,
    validate_csrf,
)
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from app.schemas.task import TaskCreateRequest, TaskListResponse, TaskResponse
from app.services.project import ProjectService
from app.services.task import TaskService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get(
    "",
    response_model=list[ProjectResponse],
    summary="List all projects in an authorized workspace",
)
async def list_projects(
    workspace_id: uuid.UUID = Query(..., description="Target workspace ID"),
    status: str | None = Query(default="active", description="Filter by status ('active', 'archived', 'all')"),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[ProjectResponse]:
    return ProjectService.list_projects(
        db=db, user=current_user, workspace_id=workspace_id, status_filter=status
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_csrf)],
    summary="Create a new project in the workspace",
)
async def create_project(
    payload: ProjectCreateRequest,
    workspace_id: uuid.UUID = Query(..., description="Target workspace ID"),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> ProjectResponse:
    return ProjectService.create_project(
        db=db, user=current_user, workspace_id=workspace_id, payload=payload
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get single project details (requires workspace membership)",
)
async def get_project(
    project_and_workspace: tuple[Project, uuid.UUID] = Depends(resolve_project_workspace),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> ProjectResponse:
    project, workspace_id = project_and_workspace
    _, response = ProjectService.get_project(
        db=db, user=current_user, workspace_id=workspace_id, project_id=project.id
    )
    return response


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    dependencies=[Depends(validate_csrf)],
    summary="Update project name or description",
)
async def update_project(
    payload: ProjectUpdateRequest,
    project_and_workspace: tuple[Project, uuid.UUID] = Depends(resolve_project_workspace),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> ProjectResponse:
    project, workspace_id = project_and_workspace
    return ProjectService.update_project(
        db=db,
        user=current_user,
        workspace_id=workspace_id,
        project_id=project.id,
        payload=payload,
    )


@router.post(
    "/{project_id}/archive",
    response_model=ProjectResponse,
    dependencies=[Depends(validate_csrf)],
    summary="Archive a project",
)
async def archive_project(
    project_and_workspace: tuple[Project, uuid.UUID] = Depends(resolve_project_workspace),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> ProjectResponse:
    project, workspace_id = project_and_workspace
    return ProjectService.archive_project(
        db=db, user=current_user, workspace_id=workspace_id, project_id=project.id
    )


@router.post(
    "/{project_id}/restore",
    response_model=ProjectResponse,
    dependencies=[Depends(validate_csrf)],
    summary="Restore an archived project",
)
async def restore_project(
    project_and_workspace: tuple[Project, uuid.UUID] = Depends(resolve_project_workspace),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> ProjectResponse:
    project, workspace_id = project_and_workspace
    return ProjectService.restore_project(
        db=db, user=current_user, workspace_id=workspace_id, project_id=project.id
    )


@router.get(
    "/{project_id}/tasks",
    response_model=TaskListResponse,
    summary="List tasks for a project with optional filters and pagination",
)
async def list_project_tasks(
    project_and_workspace: tuple[Project, uuid.UUID] = Depends(resolve_project_workspace),
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
    project, workspace_id = project_and_workspace
    items, total = TaskService.list_tasks(
        db=db,
        user=current_user,
        workspace_id=workspace_id,
        project_id=project.id,
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


@router.post(
    "/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_csrf)],
    summary="Create a new task under a project",
)
async def create_project_task(
    payload: TaskCreateRequest,
    project_and_workspace: tuple[Project, uuid.UUID] = Depends(resolve_project_workspace),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> TaskResponse:
    project, workspace_id = project_and_workspace
    return TaskService.create_task(
        db=db,
        user=current_user,
        workspace_id=workspace_id,
        project_id=project.id,
        payload=payload,
    )
