from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app_name: str
    environment: str
    version: str
    timestamp: datetime = Field(description="UTC timestamp of the health check")


class DatabaseComponentStatus(BaseModel):
    status: Literal["connected", "disconnected"]
    latency_ms: float | None = None
    error: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready", "unhealthy"]
    database: DatabaseComponentStatus
    timestamp: datetime = Field(description="UTC timestamp of the readiness check")
