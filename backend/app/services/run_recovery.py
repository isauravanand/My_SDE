import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.execution import ExecutionRun
from app.models.publishing import PublishingRun
from app.models.repair import RepairRun
from app.schemas.observability import RecoverStaleRunsResponse

logger = logging.getLogger(__name__)


class RunRecoveryService:
    """Service to detect and safely transition abandoned or interrupted agent runs into terminal states."""

    def __init__(self, db: Session | None = None):
        self.db = db

    @staticmethod
    def recover_stale_runs(
        db: Session,
        workspace_id: uuid.UUID | None = None,
        timeout_minutes: int = 15,
        actor_id: uuid.UUID | None = None,
    ) -> RecoverStaleRunsResponse:
        """
        Scans for execution, repair, and publishing runs left in active/in-flight states past timeout.
        Transitions them safely to terminal states (timed_out or failed) with explanatory summaries.
        """
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(minutes=timeout_minutes)

        recovered_execs = 0
        recovered_repairs = 0
        recovered_pubs = 0

        # 1. Recover stale ExecutionRun items
        exec_stmt = select(ExecutionRun).where(
            ExecutionRun.status.in_([
                "queued", "preparing", "applying_patch", "running_checks", "cancel_requested"
            ]),
            ExecutionRun.started_at < cutoff_time,
        )
        if workspace_id:
            exec_stmt = exec_stmt.where(ExecutionRun.workspace_id == workspace_id)

        stale_executions = db.scalars(exec_stmt).all()
        for run in stale_executions:
            old_status = run.status
            run.status = "cancelled" if old_status == "cancel_requested" else "timed_out"
            run.completed_at = now
            run.safe_error_summary = (
                "Execution run timed out or was interrupted by a system restart. You can safely retry."
            )
            recovered_execs += 1
            logger.info("Recovered stale execution run %s (from %s to %s)", run.id, old_status, run.status)

        # 2. Recover stale RepairRun items
        repair_stmt = select(RepairRun).where(
            RepairRun.status.in_(["queued", "running"]),
            (RepairRun.started_at < cutoff_time) | (RepairRun.deadline_at < now),
        )
        if workspace_id:
            repair_stmt = repair_stmt.where(RepairRun.workspace_id == workspace_id)

        stale_repairs = db.scalars(repair_stmt).all()
        for repair in stale_repairs:
            repair.status = "failed"
            repair.final_outcome = "timed_out"
            repair.completed_at = now
            repair.safe_error_summary = (
                "Repair run exceeded maximum duration limit or was interrupted. You can safely retry."
            )
            recovered_repairs += 1
            logger.info("Recovered stale repair run %s", repair.id)

        # 3. Recover stale PublishingRun items
        pub_stmt = select(PublishingRun).where(
            PublishingRun.status.in_(["preparing", "pushing_branch", "creating_pr"]),
            PublishingRun.pr_url.is_(None),
            PublishingRun.created_at < cutoff_time,
        )
        if workspace_id:
            pub_stmt = pub_stmt.where(PublishingRun.workspace_id == workspace_id)

        stale_pubs = db.scalars(pub_stmt).all()
        for pub in stale_pubs:
            pub.status = "failed"
            pub.safe_error_summary = (
                "Publishing operation was interrupted before completion. You can safely retry."
            )
            recovered_pubs += 1
            logger.info("Recovered stale publishing run %s", pub.id)

        if recovered_execs > 0 or recovered_repairs > 0 or recovered_pubs > 0:
            db.commit()

        # Audit log if workspace_id is provided
        if workspace_id and (recovered_execs > 0 or recovered_repairs > 0 or recovered_pubs > 0):
            db.add(
                ActivityLog(
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    event_type="stale_runs_recovered",
                    resource_type="workspace",
                    resource_id=workspace_id,
                    metadata_json={
                        "recovered_executions": recovered_execs,
                        "recovered_repairs": recovered_repairs,
                        "recovered_publishing": recovered_pubs,
                    },
                )
            )
            db.commit()

        return RecoverStaleRunsResponse(
            recovered_executions=recovered_execs,
            recovered_repairs=recovered_repairs,
            recovered_publishing=recovered_pubs,
            message=(
                f"Recovered {recovered_execs} execution(s), {recovered_repairs} repair(s), "
                f"and {recovered_pubs} publishing run(s)."
            ),
        )
