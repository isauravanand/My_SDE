import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128, description="Project display name")
    description: str | None = Field(default=None, max_length=2000)
    repository_id: uuid.UUID | None = Field(default=None, description="Optional connected repository ID")


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    repository_id: uuid.UUID | None = Field(default=None, description="Optional connected repository ID")


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    status: str
    repository_id: uuid.UUID | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    task_count: int = 0
    open_task_count: int = 0
