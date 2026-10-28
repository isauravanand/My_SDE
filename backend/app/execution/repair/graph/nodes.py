import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.execution.command_policy import CommandPolicyViolation
from app.execution.patch.validator import PatchValidationError, PatchValidator
from app.execution.repair.classifier import FailureClassifier
from app.execution.repair.generator import RepairGenerator, RepairPolicyViolation
from app.execution.repair.graph.state import RepairState
from app.execution.sandbox.base import BaseSandbox, SandboxTimeoutError
from app.execution.sandbox.factory import get_sandbox
from app.execution.snapshot import SnapshotError, SnapshotManager
from app.models.execution import ExecutionRun, PatchArtifact, VerificationResult
from app.models.repair import RepairAttempt, RepairRun
from app.models.task import Task
from app.schemas.repair import FailureClassification

logger = logging.getLogger(__name__)


class RepairNodes:
    """Encapsulates node execution steps for the LangGraph bounded repair workflow."""

    def __init__(
        self,
        db: Session,
        sandbox_override: BaseSandbox | None = None,
        repair_generator: RepairGenerator | None = None,
    ):
        self.db = db
        self.settings = get_settings()
        self.sandbox = sandbox_override or get_sandbox()
        self.repair_generator = repair_generator or RepairGenerator()
        self.snapshot_manager = SnapshotManager(db)

    def load_execution_run(self, state: RepairState) -> dict[str, Any]:
        """Loads execution run, repair run, and verified patch artifact from DB."""
        repair_run_id = uuid.UUID(state["repair_run_id"])
        repair_run = self.db.execute(
            select(RepairRun).where(RepairRun.id == repair_run_id)
        ).scalar_one_or_none()

        if not repair_run:
            return {
                "status": "failed",
                "final_outcome": "failed",
                "safe_error_summary": f"RepairRun {repair_run_id} not found.",
            }

        execution_run_id = repair_run.execution_run_id
        execution_run = self.db.execute(
            select(ExecutionRun).where(ExecutionRun.id == execution_run_id)
        ).scalar_one_or_none()

        if not execution_run:
            return {
                "status": "failed",
                "final_outcome": "failed",
                "safe_error_summary": f"ExecutionRun {execution_run_id} not found.",
            }

        # Check if cancelled
        if repair_run.status == "cancelled":
            return {
                "status": "cancelled",
                "final_outcome": "cancelled",
                "safe_error_summary": "Repair run cancelled by user.",
            }

        repair_run.status = "analyzing"
        self.db.commit()

        # Load applied or existing patch
        patch_art = self.db.execute(
            select(PatchArtifact).where(PatchArtifact.execution_run_id == execution_run_id)
        ).scalar_one_or_none()
        current_patch = patch_art.raw_diff if patch_art else ""

        return {
            "execution_run_id": str(execution_run.id),
            "task_id": str(repair_run.task_id),
            "workspace_id": str(repair_run.workspace_id),
            "user_id": str(repair_run.requested_by_user_id),
            "max_attempts": repair_run.max_attempts,
            "consumed_attempts": repair_run.consumed_attempts,
            "max_model_calls": repair_run.max_model_calls,
            "consumed_model_calls": repair_run.consumed_model_calls,
            "deadline_at_iso": repair_run.deadline_at.isoformat(),
            "current_patch": current_patch,
            "status": "analyzing",
        }

    def collect_failure_evidence(self, state: RepairState) -> dict[str, Any]:
        """Gathers latest verification check outputs and excerpts for diagnosis."""
        execution_run_id = uuid.UUID(state["execution_run_id"])
        results = self.db.execute(
            select(VerificationResult).where(VerificationResult.execution_run_id == execution_run_id)
        ).scalars().all()

        v_ids = [str(r.id) for r in results]
        evidence_items = []
        for r in results:
            evidence_items.append({
                "id": str(r.id),
                "command_name": r.command_name,
                "exit_code": r.exit_code,
                "status": r.status,
                "duration_seconds": r.duration_seconds,
                "stdout_excerpt": r.stdout_excerpt,
                "stderr_excerpt": r.stderr_excerpt,
            })

        return {
            "verification_result_ids": v_ids,
            "evidence": evidence_items,
        }

    def classify_failure(self, state: RepairState) -> dict[str, Any]:
        """Applies FailureClassifier to categorize defects and check repairability."""
        execution_run_id = uuid.UUID(state["execution_run_id"])
        results = list(self.db.execute(
            select(VerificationResult).where(VerificationResult.execution_run_id == execution_run_id)
        ).scalars().all())

        classification = FailureClassifier.classify(results)

        if not classification.is_repairable:
            return {
                "failure_classification": classification.model_dump(mode="json"),
                "status": "non_repairable",
                "final_outcome": "non_repairable",
                "safe_error_summary": f"Failure is non-repairable: {classification.reason}",
            }

        return {
            "failure_classification": classification.model_dump(mode="json"),
            "status": "analyzing",
        }

    def retrieve_relevant_context(self, state: RepairState) -> dict[str, Any]:
        """Extracts relevant code context for the failing files."""
        task_id = uuid.UUID(state["task_id"])
        task = self.db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()

        code_context = ""
        if task and task.description:
            code_context = f"Task Context: {task.description}"

        return {
            "code_context": code_context,
        }

    def propose_repair(self, state: RepairState) -> dict[str, Any]:
        """Calls RepairGenerator to hypothesize root cause and produce corrective patch."""
        # 1. Budget & Deadline check
        consumed_attempts = state.get("consumed_attempts", 0)
        max_attempts = state.get("max_attempts", 3)
        consumed_model_calls = state.get("consumed_model_calls", 0)
        max_model_calls = state.get("max_model_calls", 6)

        deadline_dt = datetime.fromisoformat(state["deadline_at_iso"])
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        if now >= deadline_dt:
            return {
                "status": "budget_exhausted",
                "final_outcome": "repair_exhausted",
                "safe_error_summary": "Repair run exceeded maximum allowable duration deadline.",
            }

        if consumed_attempts >= max_attempts:
            return {
                "status": "budget_exhausted",
                "final_outcome": "repair_exhausted",
                "safe_error_summary": f"Maximum repair attempts reached ({max_attempts}).",
            }

        if consumed_model_calls >= max_model_calls:
            return {
                "status": "budget_exhausted",
                "final_outcome": "repair_exhausted",
                "safe_error_summary": f"Maximum model call budget reached ({max_model_calls}).",
            }

        # 2. Retrieve task title and plan summary
        task_id = uuid.UUID(state["task_id"])
        task = self.db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
        task_title = task.title if task else "Task"
        task_desc = task.description if task else ""

        classification_dict = state["failure_classification"]
        classification = FailureClassification.model_validate(classification_dict)

        # 3. Generate proposal
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            proposal, validation = loop.run_until_complete(
                self.repair_generator.generate_proposal(
                    task_title=task_title,
                    task_description=task_desc,
                    plan_summary="Implementation fix plan",
                    current_patch=state.get("current_patch", ""),
                    classification=classification,
                    attempt_number=state.get("attempt_number", 1),
                    max_attempts=max_attempts,
                    code_context=state.get("code_context", ""),
                )
            )

            consumed_model_calls += 1
            return {
                "consumed_model_calls": consumed_model_calls,
                "proposal": proposal.model_dump(mode="json"),
                "proposal_valid": True,
                "patch_hash": validation.patch_hash,
                "status": "repairing",
            }

        except RepairPolicyViolation as e:
            logger.warning(f"Repair proposal rejected by policy: {e}")
            consumed_model_calls += 1
            return {
                "consumed_model_calls": consumed_model_calls,
                "proposal": None,
                "proposal_valid": False,
                "validation_error": str(e),
                "safe_error_summary": f"Repair policy violation: {str(e)}",
            }
        except Exception as e:
            logger.error(f"Repair proposal generation error: {e}", exc_info=True)
            consumed_model_calls += 1
            return {
                "consumed_model_calls": consumed_model_calls,
                "proposal": None,
                "proposal_valid": False,
                "validation_error": str(e),
                "safe_error_summary": f"Repair generation failed: {str(e)}",
            }

    def validate_repair_patch(self, state: RepairState) -> dict[str, Any]:
        """Validates proposed repair patch against security and syntax boundaries."""
        proposal_dict = state.get("proposal")
        if not proposal_dict or not state.get("proposal_valid"):
            return {
                "proposal_valid": False,
                "validation_error": state.get("validation_error", "No proposal generated"),
            }

        patch_text = proposal_dict.get("unified_diff", "")
        try:
            validation = PatchValidator.validate_patch(
                patch_text=patch_text,
                max_bytes=self.settings.SANDBOX_MAX_PATCH_BYTES,
                max_files=self.settings.SANDBOX_MAX_PATCH_FILES,
            )
            return {
                "proposal_valid": True,
                "patch_hash": validation.patch_hash,
            }
        except PatchValidationError as e:
            return {
                "proposal_valid": False,
                "validation_error": str(e),
            }

    def apply_repair_patch(self, state: RepairState) -> dict[str, Any]:
        """Applies the verified repair patch into the disposable sandbox working copy."""
        proposal_dict = state.get("proposal")
        if not proposal_dict:
            return {"application_result": "skipped"}

        diff = proposal_dict.get("unified_diff", "")
        sandbox = self.sandbox

        # Ensure sandbox is prepared
        try:
            sandbox.create()
            # If fresh sandbox, provision initial repository snapshot
            execution_run_id = uuid.UUID(state["execution_run_id"])
            exec_run = self.db.execute(
                select(ExecutionRun).where(ExecutionRun.id == execution_run_id)
            ).scalar_one_or_none()

            files_dict: dict[str, bytes] = {}
            if exec_run and exec_run.repository_id:
                try:
                    files_dict = self.snapshot_manager.prepare_snapshot(
                        repository_id=exec_run.repository_id,
                        expected_commit_sha=exec_run.base_commit_sha,
                    )
                except SnapshotError:
                    files_dict = {"src/main.py": b"def run():\n    return False\n"}
            else:
                files_dict = {"src/main.py": b"def run():\n    return False\n"}

            sandbox.provision_working_copy(files_dict)

            # Apply previous patch first if present
            current_patch = state.get("current_patch")
            if current_patch and current_patch.strip():
                sandbox.apply_patch(current_patch)

            # Now apply repair patch
            ok, msg = sandbox.apply_patch(diff)
            if not ok:
                return {
                    "application_result": "failed",
                    "safe_error_summary": f"Patch application failed in sandbox: {msg}",
                }

            return {"application_result": "success"}

        except Exception as e:
            logger.error(f"Sandbox patch application error: {e}", exc_info=True)
            return {
                "application_result": "failed",
                "safe_error_summary": f"Sandbox error: {str(e)}",
            }

    def rerun_verification(self, state: RepairState) -> dict[str, Any]:
        """Reruns permitted checks and records actual execution exit codes and excerpts."""
        sandbox = self.sandbox
        checks_to_run = state.get("checks_to_run") or ["syntax_check"]

        results: list[dict[str, Any]] = []
        all_passed = True

        for cmd_name in checks_to_run:
            try:
                exit_code, stdout, stderr, duration = sandbox.run_permitted_command(
                    command_key=cmd_name,
                    timeout=self.settings.SANDBOX_TIMEOUT_SECONDS,
                )
                status = "passed" if exit_code == 0 else "failed"
                if exit_code != 0:
                    all_passed = False
            except SandboxTimeoutError as e:
                exit_code = 124
                stdout = ""
                stderr = str(e)
                duration = float(self.settings.SANDBOX_TIMEOUT_SECONDS)
                status = "timed_out"
                all_passed = False
            except CommandPolicyViolation as e:
                exit_code = 126
                stdout = ""
                stderr = f"Policy violation: {e}"
                duration = 0.0
                status = "error"
                all_passed = False

            results.append({
                "command_name": cmd_name,
                "exit_code": exit_code,
                "status": status,
                "duration_seconds": duration,
                "stdout_excerpt": stdout,
                "stderr_excerpt": stderr,
            })

        consumed_attempts = state.get("consumed_attempts", 0) + 1

        return {
            "consumed_attempts": consumed_attempts,
            "verification_results": results,
            "all_passed": all_passed,
            "status": "running_checks",
        }

    def evaluate_outcome(self, state: RepairState) -> dict[str, Any]:
        """Persists the repair attempt and determines if loop terminates or repeats."""
        repair_run_id = uuid.UUID(state["repair_run_id"])
        attempt_number = state.get("attempt_number", 1)
        proposal_dict = state.get("proposal")
        all_passed = state.get("all_passed", False)
        proposal_valid = state.get("proposal_valid", False)
        app_result = state.get("application_result", "skipped")

        # Determine proposal status
        if not proposal_valid:
            proposal_status = "invalid"
        elif app_result == "failed":
            proposal_status = "failed"
        elif all_passed:
            proposal_status = "applied"
        else:
            proposal_status = "valid"

        # Record RepairAttempt in DB
        attempt = RepairAttempt(
            repair_run_id=repair_run_id,
            attempt_number=attempt_number,
            failure_classification=state.get("failure_classification", {}),
            evidence_references=state.get("evidence", []),
            root_cause_hypothesis=proposal_dict.get("root_cause_hypothesis") if proposal_dict else None,
            proposal_status=proposal_status,
            proposed_change_summary=proposal_dict.get("change_summary") if proposal_dict else None,
            patch_hash=state.get("patch_hash"),
            validation_result={"valid": proposal_valid, "error": state.get("validation_error")},
            application_result=app_result,
            verification_results_summary=state.get("verification_results"),
            duration_seconds=sum(r.get("duration_seconds", 0.0) for r in state.get("verification_results", [])),
        )
        self.db.add(attempt)
        self.db.commit()

        # Update RepairRun consumed counters in DB
        repair_run = self.db.execute(select(RepairRun).where(RepairRun.id == repair_run_id)).scalar_one_or_none()
        if repair_run:
            repair_run.consumed_attempts = state.get("consumed_attempts", attempt_number)
            repair_run.consumed_model_calls = state.get("consumed_model_calls", 0)
            self.db.commit()

        # If all checks passed -> Complete
        if all_passed and proposal_valid and app_result == "success":
            return {
                "status": "completed",
                "final_outcome": "passed",
                "safe_error_summary": None,
            }

        # Check termination constraints
        max_attempts = state.get("max_attempts", 3)
        consumed_attempts = max(state.get("consumed_attempts", 0), attempt_number)
        max_model_calls = state.get("max_model_calls", 6)
        consumed_model_calls = state.get("consumed_model_calls", 0)
        deadline_dt = datetime.fromisoformat(state["deadline_at_iso"])
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        if now >= deadline_dt:
            return {
                "status": "budget_exhausted",
                "final_outcome": "repair_exhausted",
                "safe_error_summary": "Repair deadline exceeded.",
                "consumed_attempts": consumed_attempts,
            }

        if consumed_attempts >= max_attempts:
            return {
                "status": "budget_exhausted",
                "final_outcome": "repair_exhausted",
                "safe_error_summary": f"Budget exhausted: {consumed_attempts}/{max_attempts} attempts used.",
                "consumed_attempts": consumed_attempts,
            }

        if consumed_model_calls >= max_model_calls:
            return {
                "status": "budget_exhausted",
                "final_outcome": "repair_exhausted",
                "safe_error_summary": f"Model call budget exhausted ({consumed_model_calls}/{max_model_calls}).",
                "consumed_attempts": consumed_attempts,
            }

        # Increment attempt number for the next bounded iteration
        return {
            "attempt_number": attempt_number + 1,
            "consumed_attempts": consumed_attempts,
            "status": "analyzing",
        }

    def finalize_repair_run(self, state: RepairState) -> dict[str, Any]:
        """Marks repair run terminal status and outcome in the database."""
        repair_run_id = uuid.UUID(state["repair_run_id"])
        repair_run = self.db.execute(
            select(RepairRun).where(RepairRun.id == repair_run_id)
        ).scalar_one_or_none()

        if repair_run:
            repair_run.status = state.get("status", "completed")
            repair_run.final_outcome = state.get("final_outcome", "failed")
            repair_run.safe_error_summary = state.get("safe_error_summary")
            repair_run.consumed_attempts = state.get("consumed_attempts", repair_run.consumed_attempts)
            repair_run.consumed_model_calls = state.get("consumed_model_calls", repair_run.consumed_model_calls)
            repair_run.completed_at = datetime.now(timezone.utc)

            # If all passed, update execution run
            if state.get("all_passed"):
                exec_run = self.db.execute(
                    select(ExecutionRun).where(ExecutionRun.id == repair_run.execution_run_id)
                ).scalar_one_or_none()
                if exec_run:
                    exec_run.status = "completed"
                    exec_run.safe_error_summary = "Resolved by automated repair loop."

            self.db.commit()

        # Teardown sandbox if one was allocated
        if self.sandbox:
            self.sandbox.destroy()

        return state
