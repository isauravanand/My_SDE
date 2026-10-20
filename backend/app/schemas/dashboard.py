import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DashboardSummaryResponse(BaseModel):
    total_projects: int
    open_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    agent_runs: int = 0


class ActivityLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    event_type: str
    resource_type: str
    resource_id: uuid.UUID
    metadata_json: dict[str, Any]
    created_at: datetime
