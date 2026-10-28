import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.execution import ExecutionRun
    from app.models.github import GitHubRepository
    from app.models.project import Project
    from app.models.user import User
    from app.models.workspace import Workspace

TASK_STATUSES = {"backlog", "todo", "in_progress", "in_review", "done", "cancelled"}
TASK_PRIORITIES = {"low", "medium", "high", "critical"}
TASK_TYPES = {"feature", "bug", "improvement", "chore"}


class Task(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Development task tracked under a project and workspace."""

    __tablename__ = "tasks"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="todo", index=True, nullable=False
    )
    priority: Mapped[str] = mapped_column(
        String(32), default="medium", index=True, nullable=False
    )
    task_type: Mapped[str] = mapped_column(
        String(32), default="feature", nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("github_repositories.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    github_issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_issue_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    github_issue_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", backref="tasks")
    project: Mapped["Project"] = relationship("Project", back_populates="tasks")
    repository: Mapped["GitHubRepository | None"] = relationship(
        "GitHubRepository", foreign_keys=[repository_id]
    )
    creator: Mapped["User | None"] = relationship("User", foreign_keys=[created_by])
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_id])
    execution_runs: Mapped[list["ExecutionRun"]] = relationship(
        "ExecutionRun",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title[:30]} status={self.status}>"
