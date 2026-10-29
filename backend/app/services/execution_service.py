import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.execution.command_policy import CommandPolicy, CommandPolicyViolation
from app.execution.patch.generator import PatchGenerator
from app.execution.sandbox.base import BaseSandbox, SandboxTimeoutError
from app.execution.sandbox.factory import get_sandbox
from app.execution.snapshot import SnapshotError, SnapshotManager
from app.models.execution import ExecutionRun, PatchArtifact, VerificationResult
from app.models.github import GitHubRepository
from app.models.planning import ImplementationPlan
from app.models.task import Task
from app.models.workspace import WorkspaceMembership

logger = logging.getLogger(__name__)

ACTIVE_RUN_STATUSES = {
    "queued",
    "preparing",
    "awaiting_patch_approval",
    "applying_patch",
    "running_checks",
}


class ExecutionServiceError(Exception):
    """Base exception for execution service failures."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ExecutionService:
    """Orchestrates secure code execution runs, patch proposals, and sandboxed checks."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.snapshot_manager = SnapshotManager(db)
        self.patch_generator = PatchGenerator()

    def _verify_workspace_access(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Ensures requesting user has an active membership in the target workspace."""
        membership = self.db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        ).scalar_one_or_none()

        if not membership:
            raise ExecutionServiceError("Access denied: You do not belong to this workspace.", status_code=403)

    def start_execution_run(
        self,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        plan_id: uuid.UUID | None = None,
        verification_commands: list[str] | None = None,
    ) -> ExecutionRun:
        """
        Initiates a new execution preparation run linked to an approved implementation plan.
        """
        task = self.db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
        if not task:
            raise ExecutionServiceError(f"Task {task_id} not found.", status_code=404)

        workspace_id = task.workspace_id
        self._verify_workspace_access(workspace_id, user_id)

        # Prevent duplicate concurrent computing runs on the same task
        existing_active = self.db.execute(
            select(ExecutionRun).where(
                ExecutionRun.task_id == task_id,
                ExecutionRun.status.in_(ACTIVE_RUN_STATUSES),
            )
        ).scalar_one_or_none()

        if existing_active:
            raise ExecutionServiceError(
                f"An active execution run ({existing_active.id}) is already in progress with status '{existing_active.status}'.",
                status_code=400,
            )


        # Enforce subscription plan quota & concurrency limits
        from app.services.billing_service import BillingService
        billing_service = BillingService(self.db)
        billing_service.enforce_quota(workspace_id, quota_type="agent_runs", quantity=1)

        # Resolve target plan
        if plan_id:
            plan = self.db.execute(
                select(ImplementationPlan).where(
                    ImplementationPlan.id == plan_id,
                    ImplementationPlan.task_id == task_id,
                )
            ).scalar_one_or_none()
        else:
            plan = self.db.execute(
                select(ImplementationPlan)
                .where(ImplementationPlan.task_id == task_id)
                .order_by(desc(ImplementationPlan.created_at))
            ).scalars().first()

        if not plan:
            raise ExecutionServiceError(
                "No implementation plan found for this task. Generate and approve a plan first.",
                status_code=400,
            )

        # Base commit resolution
        base_commit_sha = plan.plan_data.get("base_commit_sha")
        repo_id = task.repository_id or (task.project.repository_id if task.project else None)
        if not base_commit_sha and repo_id:
            repo = self.db.execute(
                select(GitHubRepository).where(GitHubRepository.id == repo_id)
            ).scalar_one_or_none()
            if repo:
                base_commit_sha = getattr(repo, "default_branch_commit_sha", None)
                if not base_commit_sha and repo.installation:
                    try:
                        base_commit_sha = self.snapshot_manager.github_client.get_ref_commit(
                            installation_id=repo.installation.installation_id,
                            owner=repo.owner_login,
                            repo=repo.name,
                            ref=repo.default_branch or "main",
                        )
                    except Exception as e:
                        logger.warning(f"Could not fetch commit sha from GitHub for base_commit_sha: {e}")

        if not base_commit_sha:
            base_commit_sha = "0000000000000000000000000000000000000000"

        # Create ExecutionRun in preparing status
        run = ExecutionRun(
            workspace_id=workspace_id,
            task_id=task_id,
            repository_id=task.repository_id or (task.project.repository_id if task.project else None),
            plan_id=plan.id,
            requested_by_user_id=user_id,
            base_commit_sha=base_commit_sha,
            status="preparing",
            sandbox_provider=self.settings.SANDBOX_PROVIDER,
            sandbox_image=self.settings.SANDBOX_DOCKER_IMAGE,
            cleanup_status="pending",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        # Record usage ledger event
        billing_service.record_usage(
            workspace_id=workspace_id,
            user_id=user_id,
            event_type="agent_run_started",
            operation_id=str(run.id),
            run_id=run.id,
            metadata={"task_id": str(task_id), "plan_id": str(plan.id)},
        )
        self.db.commit()

        # Launch preparation
        try:
            self._prepare_patch_for_run(run, task, plan)
        except Exception as e:
            logger.error(f"Execution preparation failed for run {run.id}: {e}", exc_info=True)
            run.status = "failed"
            run.safe_error_summary = f"Preparation failed: {str(e)}"
            run.completed_at = datetime.now(timezone.utc)
            self.db.commit()

        return run

    def _prepare_patch_for_run(
        self,
        run: ExecutionRun,
        task: Task,
        plan: ImplementationPlan,
    ) -> None:
        """Materializes snapshot files and generates proposed patch proposal."""
        repo_name = "connected-repo"
        if task.repository:
            repo_name = task.repository.full_name

        # 1. Evidence snippets from plan
        evidence_list = plan.plan_data.get("evidence", [])
        evidence_snippets = []
        if evidence_list:
            evidence_snippets = [
                f"File: {e.get('file_path')} (Lines {e.get('start_line')}-{e.get('end_line')}):\n{e.get('excerpt')}"
                for e in evidence_list[:5]
            ]

        # 2. Load actual files from snapshot to give full context (e.g. index.html, index.css)
        snapshot_files: dict[str, bytes] = {}
        if run.repository_id and run.base_commit_sha and run.base_commit_sha != "0000000000000000000000000000000000000000":
            try:
                snapshot_files = self.snapshot_manager.prepare_snapshot(run.repository_id, run.base_commit_sha)
            except Exception as e:
                logger.warning(f"Could not load full snapshot for patch context: {e}")

        # Build prioritized, token-budgeted context using enhanced context builder
        from app.execution.context_builder import build_execution_context
        evidence_context = "\n\n".join(evidence_snippets) if evidence_snippets else ""
        try:
            code_context = build_execution_context(
                task_title=task.title,
                task_description=task.description or "",
                plan_data=plan.plan_data,
                snapshot=snapshot_files,
            )
            if evidence_context:
                code_context = code_context + "\n\n" + evidence_context
        except Exception as e:
            logger.warning(f"Context builder failed: {e}; falling back to evidence only")
            code_context = evidence_context or "No repository code context provided"

        # Generate patch using PatchGenerator
        # Run synchronously via loop or new loop if in thread
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        raw_diff, validation = loop.run_until_complete(
            self.patch_generator.generate_patch(
                task_title=task.title,
                task_description=task.description or "",
                plan_data=plan.plan_data,
                repo_name=repo_name,
                base_commit_sha=run.base_commit_sha,
                code_context=code_context,
                snapshot=snapshot_files,
            )
        )

        # Run feedback loop verification before presenting to user
        from app.execution.feedback_loop import verify_patch
        feedback = verify_patch(raw_diff, snapshot_files)
        if not feedback.passed:
            logger.warning(
                "Patch verification found %d error(s) in run %s: %s",
                len(feedback.errors),
                run.id,
                "; ".join(feedback.errors[:3]),
            )
            # Store feedback errors in the artifact but still present to user
            # (the user sees the errors as warnings, can still approve or reject)
            feedback_summary = "Verification warnings:\n" + "\n".join(feedback.errors[:5])
        else:
            feedback_summary = None

        patch_artifact = PatchArtifact(
            execution_run_id=run.id,
            patch_hash=validation.patch_hash,
            validation_status="valid" if validation.is_valid else "invalid",
            validation_error=validation.error_message or feedback_summary,
            raw_diff=raw_diff,
            changed_files_count=validation.changed_files_count,
            additions_count=validation.additions_count,
            deletions_count=validation.deletions_count,
            changed_files=[f.model_dump() for f in validation.changed_files],
            is_approved=False,
        )
        self.db.add(patch_artifact)

        run.status = "awaiting_patch_approval"
        self.db.commit()
        self.db.refresh(run)

    def approve_and_execute(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
        run_checks: bool = True,
        verification_commands: list[str] | None = None,
        sandbox_override: BaseSandbox | None = None,
    ) -> ExecutionRun:
        """
        User explicitly approves the proposed patch, triggering sandboxed application and checks.
        """
        run = self.db.execute(select(ExecutionRun).where(ExecutionRun.id == run_id)).scalar_one_or_none()
        if not run:
            raise ExecutionServiceError(f"Execution run {run_id} not found.", status_code=404)

        self._verify_workspace_access(run.workspace_id, user_id)

        if run.status != "awaiting_patch_approval":
            raise ExecutionServiceError(
                f"Cannot approve patch for run in status '{run.status}'. Must be 'awaiting_patch_approval'.",
                status_code=400,
            )

        patch = self.db.execute(
            select(PatchArtifact).where(PatchArtifact.execution_run_id == run.id)
        ).scalar_one_or_none()

        if not patch:
            raise ExecutionServiceError("No patch found for this execution run.", status_code=400)

        if patch.validation_status != "valid":
            raise ExecutionServiceError("Cannot apply an invalid or rejected patch.", status_code=400)

        # Mark approval
        patch.is_approved = True
        patch.approved_by_user_id = user_id
        patch.approved_at = datetime.now(timezone.utc)
        run.status = "applying_patch"
        self.db.commit()

        # Execute in sandbox
        sandbox = sandbox_override or get_sandbox()
        all_passed = True
        cleanup_success = False

        try:
            sandbox.create()

            # Provision working copy
            files_dict: dict[str, bytes] = {}
            if run.repository_id:
                try:
                    files_dict = self.snapshot_manager.prepare_snapshot(
                        repository_id=run.repository_id,
                        expected_commit_sha=run.base_commit_sha,
                    )
                except SnapshotError as e:
                    logger.warning(f"Snapshot acquisition: {e}. Using minimal baseline.")
                    files_dict = {"README.md": b"# Baseline repository\n"}
            else:
                files_dict = {"README.md": b"# Standalone repository\n"}

            sandbox.provision_working_copy(files_dict)

            # Apply patch
            apply_ok, apply_msg = sandbox.apply_patch(patch.raw_diff)
            if not apply_ok:
                patch.validation_status = "invalid"
                patch.validation_error = f"Patch application failed in sandbox: {apply_msg}"
                run.status = "failed"
                run.safe_error_summary = "Patch failed to apply to repository snapshot."
                self.db.commit()
                return run

            patch.validation_status = "applied"

            # Execute verification checks if requested
            commands_to_run = verification_commands or ["syntax_check"]
            if run_checks and commands_to_run:
                run.status = "running_checks"
                self.db.commit()

                for cmd_name in commands_to_run:
                    try:
                        exit_code, stdout, stderr, duration = sandbox.run_permitted_command(
                            command_key=cmd_name,
                            timeout=self.settings.SANDBOX_TIMEOUT_SECONDS,
                        )
                        check_status = "passed" if exit_code == 0 else "failed"
                        if exit_code != 0:
                            all_passed = False

                    except SandboxTimeoutError as e:
                        exit_code = 124
                        stdout = ""
                        stderr = str(e)
                        duration = float(self.settings.SANDBOX_TIMEOUT_SECONDS)
                        check_status = "timed_out"
                        all_passed = False
                        run.status = "timed_out"

                    except CommandPolicyViolation as e:
                        exit_code = 126
                        stdout = ""
                        stderr = f"Policy violation: {e}"
                        duration = 0.0
                        check_status = "error"
                        all_passed = False

                    cmd_def = CommandPolicy.resolve_and_validate(cmd_name)[0] if cmd_name in CommandPolicy.get_allowed_commands() else "test"
                    v_res = VerificationResult(
                        execution_run_id=run.id,
                        verification_type=cmd_def,
                        command_name=cmd_name,
                        command_args=[cmd_name],
                        exit_code=exit_code,
                        status=check_status,
                        duration_seconds=duration,
                        stdout_excerpt=stdout,
                        stderr_excerpt=stderr,
                    )
                    self.db.add(v_res)
                    self.db.commit()

            # Set terminal status
            if run.status != "timed_out":
                run.status = "completed" if all_passed else "failed"
            run.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"Error during sandbox execution: {e}", exc_info=True)
            run.status = "failed"
            run.safe_error_summary = f"Sandbox execution failed: {str(e)}"
            run.completed_at = datetime.now(timezone.utc)

        finally:
            # Cleanup sandbox
            cleanup_success = sandbox.destroy()
            run.cleanup_status = "cleaned" if cleanup_success else "cleanup_failed"
            self.db.commit()
            self.db.refresh(run)

        return run

    def reject_patch(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str | None = None,
    ) -> ExecutionRun:
        """Rejects a proposed patch, canceling the execution run."""
        run = self.db.execute(select(ExecutionRun).where(ExecutionRun.id == run_id)).scalar_one_or_none()
        if not run:
            raise ExecutionServiceError(f"Execution run {run_id} not found.", status_code=404)

        self._verify_workspace_access(run.workspace_id, user_id)

        patch = self.db.execute(
            select(PatchArtifact).where(PatchArtifact.execution_run_id == run.id)
        ).scalar_one_or_none()

        if patch:
            patch.validation_status = "rejected"
            patch.validation_error = reason or "Rejected by user."

        run.status = "cancelled"
        run.safe_error_summary = f"Patch rejected: {reason or 'User rejected changes.'}"
        run.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(run)
        return run

    def cancel_execution_run(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ExecutionRun:
        """Requests cancellation of an ongoing or queued execution run."""
        run = self.db.execute(select(ExecutionRun).where(ExecutionRun.id == run_id)).scalar_one_or_none()
        if not run:
            raise ExecutionServiceError(f"Execution run {run_id} not found.", status_code=404)

        self._verify_workspace_access(run.workspace_id, user_id)

        if run.status in {"completed", "failed", "cancelled", "timed_out"}:
            return run

        run.status = "cancelled"
        run.safe_error_summary = "Execution run cancelled by user."
        run.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_execution_run(
        self,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ExecutionRun:
        """Fetches an execution run with workspace authorization enforcement."""
        run = self.db.execute(select(ExecutionRun).where(ExecutionRun.id == run_id)).scalar_one_or_none()
        if not run:
            raise ExecutionServiceError(f"Execution run {run_id} not found.", status_code=404)

        self._verify_workspace_access(run.workspace_id, user_id)
        return run

    def list_task_execution_runs(
        self,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 10,
        offset: int = 0,
    ) -> list[ExecutionRun]:
        """Lists execution runs for a task with pagination."""
        task = self.db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
        if not task:
            raise ExecutionServiceError(f"Task {task_id} not found.", status_code=404)

        self._verify_workspace_access(task.workspace_id, user_id)

        runs = self.db.execute(
            select(ExecutionRun)
            .where(ExecutionRun.task_id == task_id)
            .order_by(desc(ExecutionRun.created_at))
            .limit(limit)
            .offset(offset)
        ).scalars().all()

        return list(runs)
