import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.execution.repair.generator import RepairGenerator
from app.execution.repair.graph.state import RepairState
from app.execution.repair.graph.workflow import build_repair_graph
from app.execution.sandbox.base import BaseSandbox
from app.models.execution import ExecutionRun, VerificationResult
from app.models.repair import RepairRun
from app.models.workspace import WorkspaceMembership

logger = logging.getLogger(__name__)

ACTIVE_REPAIR_STATUSES = {"queued", "analyzing", "repairing", "running_checks"}


class RepairServiceError(Exception):
    """Base exception for repair service failures."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RepairService:
    """Manages bounded AI repair workflows, failure classification, and verification rerun."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _verify_workspace_access(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Ensures requesting user has an active membership in the target workspace."""
        membership = self.db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        ).scalar_one_or_none()

        if not membership:
            raise RepairServiceError("Access denied: You do not belong to this workspace.", status_code=403)

    def start_repair_run(
        self,
        execution_run_id: uuid.UUID,
        user_id: uuid.UUID,
        verification_commands: list[str] | None = None,
        sandbox_override: BaseSandbox | None = None,
        repair_generator: RepairGenerator | None = None,
    ) -> RepairRun:
        """
        Initiates a bounded automated repair run for a failed execution run.
        """
        exec_run = self.db.execute(
            select(ExecutionRun).where(ExecutionRun.id == execution_run_id)
        ).scalar_one_or_none()

        if not exec_run:
            raise RepairServiceError(f"Execution run {execution_run_id} not found.", status_code=404)

        workspace_id = exec_run.workspace_id
        self._verify_workspace_access(workspace_id, user_id)

        # 1. Eligibility Check: Must be in failed status or have failed checks
        if exec_run.status in {"preparing", "awaiting_patch_approval", "applying_patch", "running_checks"}:
            raise RepairServiceError(
                f"Cannot initiate repair: Execution run is still active with status '{exec_run.status}'.",
                status_code=400,
            )

        # 2. Check for verification results
        checks = list(self.db.execute(
            select(VerificationResult).where(VerificationResult.execution_run_id == execution_run_id)
        ).scalars().all())

        if not checks:
            raise RepairServiceError(
                "Execution run has no verification results to diagnose or repair.",
                status_code=400,
            )

        failed_checks = [c for c in checks if c.status in {"failed", "timed_out", "error"}]
        if not failed_checks and exec_run.status == "completed":
            raise RepairServiceError(
                "Execution run succeeded with all checks passing. Repair is not required.",
                status_code=400,
            )

        # 3. Concurrency Check: Prevent duplicate active repair runs
        existing_active = self.db.execute(
            select(RepairRun).where(
                RepairRun.execution_run_id == execution_run_id,
                RepairRun.status.in_(ACTIVE_REPAIR_STATUSES),
            )
        ).scalar_one_or_none()

        if existing_active:
            raise RepairServiceError(
                f"An active repair run ({existing_active.id}) is already in progress with status '{existing_active.status}'.",
                status_code=400,
            )

        # Enforce repair_runs quota
        from app.services.billing_service import BillingService
        billing_service = BillingService(self.db)
        billing_service.enforce_quota(workspace_id, quota_type="repair_runs", quantity=1)

        # 4. Create RepairRun record
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(seconds=self.settings.REPAIR_MAX_DURATION_SECONDS)

        repair_run = RepairRun(
            workspace_id=workspace_id,
            execution_run_id=execution_run_id,
            task_id=exec_run.task_id,
            requested_by_user_id=user_id,
            status="queued",
            max_attempts=self.settings.REPAIR_MAX_ATTEMPTS,
            consumed_attempts=0,
            max_model_calls=self.settings.REPAIR_MAX_MODEL_CALLS,
            consumed_model_calls=0,
            started_at=now,
            deadline_at=deadline,
        )
        self.db.add(repair_run)
        self.db.commit()
        self.db.refresh(repair_run)

        # Record usage ledger event
        billing_service.record_usage(
            workspace_id=workspace_id,
            user_id=user_id,
            event_type="repair_run_started",
            operation_id=str(repair_run.id),
            run_id=repair_run.id,
            metadata={"execution_run_id": str(execution_run_id), "task_id": str(exec_run.task_id)},
        )
        self.db.commit()

        # 5. Build and execute LangGraph workflow
        compiled_graph = build_repair_graph(
            db=self.db,
            sandbox_override=sandbox_override,
            repair_generator=repair_generator,
        )

        initial_state: RepairState = {
            "execution_run_id": str(exec_run.id),
            "repair_run_id": str(repair_run.id),
            "task_id": str(exec_run.task_id),
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
            "attempt_number": 1,
            "max_attempts": repair_run.max_attempts,
            "consumed_attempts": 0,
            "max_model_calls": repair_run.max_model_calls,
            "consumed_model_calls": 0,
            "deadline_at_iso": deadline.isoformat(),
            "checks_to_run": verification_commands or [c.command_name for c in checks],
            "status": "queued",
        }

        try:
            # Run the graph synchronously
            compiled_graph.invoke(initial_state)
        except Exception as e:
            logger.error(f"Error executing repair graph: {e}", exc_info=True)
            repair_run.status = "failed"
            repair_run.final_outcome = "failed"
            repair_run.safe_error_summary = f"Workflow error: {str(e)}"
            repair_run.completed_at = datetime.now(timezone.utc)
            self.db.commit()

        self.db.refresh(repair_run)
        return repair_run

    def get_repair_run(self, repair_run_id: uuid.UUID, user_id: uuid.UUID) -> RepairRun:
        """Fetches a repair run with workspace authorization check."""
        repair_run = self.db.execute(
            select(RepairRun).where(RepairRun.id == repair_run_id)
        ).scalar_one_or_none()

        if not repair_run:
            raise RepairServiceError(f"Repair run {repair_run_id} not found.", status_code=404)

        self._verify_workspace_access(repair_run.workspace_id, user_id)
        return repair_run

    def get_latest_repair_for_execution(
        self,
        execution_run_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> RepairRun | None:
        """Fetches the latest repair run for an execution run."""
        exec_run = self.db.execute(
            select(ExecutionRun).where(ExecutionRun.id == execution_run_id)
        ).scalar_one_or_none()

        if not exec_run:
            raise RepairServiceError(f"Execution run {execution_run_id} not found.", status_code=404)

        self._verify_workspace_access(exec_run.workspace_id, user_id)

        latest_repair = self.db.execute(
            select(RepairRun)
            .where(RepairRun.execution_run_id == execution_run_id)
            .order_by(desc(RepairRun.created_at))
        ).scalars().first()

        return latest_repair

    def cancel_repair_run(self, repair_run_id: uuid.UUID, user_id: uuid.UUID) -> RepairRun:
        """Requests cancellation of an ongoing repair run."""
        repair_run = self.db.execute(
            select(RepairRun).where(RepairRun.id == repair_run_id)
        ).scalar_one_or_none()

        if not repair_run:
            raise RepairServiceError(f"Repair run {repair_run_id} not found.", status_code=404)

        self._verify_workspace_access(repair_run.workspace_id, user_id)

        if repair_run.status in {"completed", "failed", "cancelled", "non_repairable", "budget_exhausted"}:
            return repair_run

        repair_run.status = "cancelled"
        repair_run.final_outcome = "cancelled"
        repair_run.safe_error_summary = "Repair run cancelled by user."
        repair_run.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(repair_run)
        return repair_run

    def get_repair_summary(self, repair_run_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
        """Calculates final outcome summary and check comparisons."""
        repair_run = self.get_repair_run(repair_run_id, user_id)

        attempts = repair_run.attempts
        total_attempts = len(attempts)
        duration = 0.0
        if repair_run.completed_at and repair_run.started_at:
            duration = (repair_run.completed_at - repair_run.started_at).total_seconds()

        initial_patch_hash = None
        final_patch_hash = None

        if attempts:
            initial_patch_hash = attempts[0].patch_hash
            final_patch_hash = attempts[-1].patch_hash

        last_attempt_checks = []
        if attempts and attempts[-1].verification_results_summary:
            last_attempt_checks = attempts[-1].verification_results_summary

        return {
            "repair_run_id": repair_run.id,
            "final_outcome": repair_run.final_outcome or "failed",
            "total_attempts": total_attempts,
            "duration_seconds": duration,
            "initial_patch_hash": initial_patch_hash,
            "final_patch_hash": final_patch_hash,
            "checks_summary": last_attempt_checks,
        }
