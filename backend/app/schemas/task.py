import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.task import TASK_PRIORITIES, TASK_STATUSES, TASK_TYPES


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255, description="Task title")
    description: str | None = Field(default=None, max_length=10000)
    status: str = Field(default="todo")
    priority: str = Field(default="medium")
    task_type: str = Field(default="feature")
    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in TASK_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Must be one of: {sorted(TASK_STATUSES)}")
        return v_clean

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in TASK_PRIORITIES:
            raise ValueError(f"Invalid priority '{v}'. Must be one of: {sorted(TASK_PRIORITIES)}")
        return v_clean

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in TASK_TYPES:
            raise ValueError(f"Invalid task_type '{v}'. Must be one of: {sorted(TASK_TYPES)}")
        return v_clean


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    status: str | None = None
    priority: str | None = None
    task_type: str | None = None
    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v_clean = v.strip().lower()
        if v_clean not in TASK_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Must be one of: {sorted(TASK_STATUSES)}")
        return v_clean

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v_clean = v.strip().lower()
        if v_clean not in TASK_PRIORITIES:
            raise ValueError(f"Invalid priority '{v}'. Must be one of: {sorted(TASK_PRIORITIES)}")
        return v_clean

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v_clean = v.strip().lower()
        if v_clean not in TASK_TYPES:
            raise ValueError(f"Invalid task_type '{v}'. Must be one of: {sorted(TASK_TYPES)}")
        return v_clean


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str | None = None
    title: str
    description: str | None = None
    status: str
    priority: str
    task_type: str
    created_by: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    assignee_email: str | None = None
    due_at: datetime | None = None
    completed_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int
