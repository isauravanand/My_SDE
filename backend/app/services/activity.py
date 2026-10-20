import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.activity import ActivityLog


class ActivityService:
    """Service for logging workspace activity and audit events."""

    @staticmethod
    def log_activity(
        db: Session,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        event_type: str,
        resource_type: str,
        resource_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """Record an activity log entry without committing (participates in current transaction)."""
        clean_metadata = metadata or {}
        # Sanitize metadata: ensure no credentials/tokens are ever saved
        for key in list(clean_metadata.keys()):
            if any(s in key.lower() for s in ("token", "password", "secret", "cookie")):
                clean_metadata[key] = "[REDACTED]"

        activity = ActivityLog(
            workspace_id=workspace_id,
            actor_id=actor_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=clean_metadata,
        )
        db.add(activity)
        return activity
