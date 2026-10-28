import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, validate_csrf
from app.db.session import get_db
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.code_rag import (
    IndexingJobResponse,
    IndexingTriggerRequest,
    RetrievalQueryRequest,
    RetrievalResultResponse,
)
from app.services.indexing_service import IndexingService
from app.services.retrieval_service import RetrievalService
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/rag", tags=["code-rag"])
indexing_service = IndexingService()
retrieval_service = RetrievalService()


@router.post(
    "/repositories/{repo_id}/index",
    response_model=IndexingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue repository ingestion and code embedding job",
)
async def trigger_indexing(
    repo_id: uuid.UUID,
    payload: IndexingTriggerRequest | None = None,
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(validate_csrf),
    db: Session = Depends(get_db),
) -> IndexingJobResponse:
    """Queue an asynchronous repository indexing run to chunk and embed source files."""
    workspace, membership = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    if membership.role not in {"owner", "admin", "member"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to trigger repository indexing in this workspace.",
        )

    req = payload or IndexingTriggerRequest()
    job = indexing_service.enqueue_indexing_job(
        db=db,
        workspace_id=workspace.id,
        repository_id=repo_id,
        target_ref=req.target_ref,
        force_reindex=req.force_reindex,
    )
    return IndexingJobResponse.model_validate(job)


@router.get(
    "/repositories/{repo_id}/index/status",
    response_model=IndexingJobResponse | None,
    summary="Get status of latest indexing job for a repository",
)
def get_indexing_status(
    repo_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IndexingJobResponse | None:
    """Retrieve the status and statistics of the most recent indexing run."""
    workspace, _ = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    job = indexing_service.get_latest_status(db, workspace.id, repo_id)
    if not job:
        return None
    return IndexingJobResponse.model_validate(job)


@router.get(
    "/repositories/{repo_id}/index/jobs",
    response_model=list[IndexingJobResponse],
    summary="List recent indexing jobs for a repository",
)
def list_indexing_jobs(
    repo_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IndexingJobResponse]:
    """Retrieve recent indexing runs for a repository."""
    workspace, _ = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    jobs = indexing_service.list_jobs(db, workspace.id, repo_id, limit=limit)
    return [IndexingJobResponse.model_validate(j) for j in jobs]


@router.post(
    "/repositories/{repo_id}/retrieve",
    response_model=RetrievalResultResponse,
    summary="Query repository Code RAG with natural-language task description",
)
async def retrieve_code(
    repo_id: uuid.UUID,
    payload: RetrievalQueryRequest,
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RetrievalResultResponse:
    """Search indexed repository code chunks using semantic vector search with lexical boosting."""
    workspace, _ = WorkspaceService.get_workspace_for_user(db, current_user, workspace_id)
    try:
        results = await retrieval_service.retrieve_chunks(
            db=db,
            workspace_id=workspace.id,
            repository_id=repo_id,
            query=payload.query,
            commit_sha=payload.commit_sha,
            top_k=payload.top_k,
            file_path_pattern=payload.file_path_pattern,
            language=payload.language,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return RetrievalResultResponse.model_validate(results)


@router.get(
    "/tasks/{task_id}/retrieve-context",
    response_model=RetrievalResultResponse,
    summary="Retrieve relevant code context for a task automatically",
)
async def retrieve_task_context(
    task_id: uuid.UUID,
    top_k: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RetrievalResultResponse:
    """Find relevant repository code for a task based on its title, description, and connected repository."""
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Authorize workspace
    WorkspaceService.get_workspace_for_user(db, current_user, task.workspace_id)

    # Resolve connected repository
    repo_id = task.repository_id
    if not repo_id:
        # Check parent project's connected repository
        project = db.get(Project, task.project_id)
        if project and project.repository_id:
            repo_id = project.repository_id

    if not repo_id:
        return RetrievalResultResponse(
            repository_id="",
            repository_name="",
            commit_sha="",
            is_indexed=False,
            message="Neither this task nor its parent project is linked to a connected GitHub repository.",
            results=[],
            total_results=0,
        )

    # Formulate retrieval query from task title + description
    search_query = task.title
    if task.description:
        search_query = f"{task.title}\n{task.description}"

    try:
        results = await retrieval_service.retrieve_chunks(
            db=db,
            workspace_id=task.workspace_id,
            repository_id=repo_id,
            query=search_query,
            top_k=top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return RetrievalResultResponse.model_validate(results)
