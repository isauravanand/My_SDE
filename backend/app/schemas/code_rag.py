import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IndexingTriggerRequest(BaseModel):
    target_ref: str | None = Field(default=None, description="Branch or git reference to index (defaults to repo default branch)")
    force_reindex: bool = Field(default=False, description="Force re-indexing even if this commit has already been indexed")


class IndexingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    repository_id: uuid.UUID
    target_ref: str
    commit_sha: str
    status: str
    files_discovered: int
    files_accepted: int
    files_excluded: int
    files_failed: int
    chunks_count: int
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    error_summary: str | None = None
    exclusions_summary: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class RetrievalQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="Natural language search query or task description")
    top_k: int = Field(default=5, ge=1, le=25, description="Maximum number of relevant chunks to return")
    language: str | None = Field(default=None, description="Filter results by programming language (e.g. 'python', 'javascript')")
    file_path_pattern: str | None = Field(default=None, description="Filter results by file path substring or glob")
    commit_sha: str | None = Field(default=None, description="Optional target commit SHA to query against")


class RetrievedChunkResponse(BaseModel):
    chunk_id: str
    file_path: str
    file_language: str
    start_line: int
    end_line: int
    symbol_name: str | None = None
    symbol_type: str | None = None
    chunk_content: str
    score: float
    commit_sha: str
    github_url: str


class RetrievalResultResponse(BaseModel):
    repository_id: str
    repository_name: str
    commit_sha: str
    is_indexed: bool
    message: str | None = None
    results: list[RetrievedChunkResponse] = Field(default_factory=list)
    total_results: int = 0
