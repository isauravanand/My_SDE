import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class ActivityLog(Base, UUIDPrimaryKeyMixin):
    """Immutable audit/activity log for workspace events."""

    __tablename__ = "activity_logs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )  # e.g., "project_created", "task_created", "task_status_changed"
    resource_type: Mapped[str] = mapped_column(
        String(32), index=True, nullable=False
    )  # "project", "task"
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        index=True,
        nullable=False,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", backref="activities")
    actor: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<ActivityLog id={self.id} event={self.event_type} res={self.resource_type}:{self.resource_id}>"
