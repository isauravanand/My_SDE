import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.execution import ExecutionRun, PatchArtifact, VerificationResult
from app.models.publishing import PublishingRun
from app.models.repair import RepairRun
from app.schemas.observability import (
    ModelUsageMetadata,
    ObservabilityMetricsResponse,
    ObservabilityRunSummary,
    RunTraceResponse,
    StageTimelineEvent,
)


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ObservabilityService:
    """Service providing end-to-end run tracing, lifecycle timelines, and workspace reliability metrics."""

    @staticmethod
    def get_run_trace(
        db: Session,
        execution_run_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> RunTraceResponse:
        """
        Build an end-to-end trace aggregating Planning, Execution, Verification,
        Repair, and Publishing stages into a chronological lifecycle view.
        """
        run = db.scalar(
            select(ExecutionRun).where(
                ExecutionRun.id == execution_run_id,
                ExecutionRun.workspace_id == workspace_id,
            )
        )
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execution run not found in active workspace.",
            )

        task = run.task
        now = datetime.now(timezone.utc)
        exec_duration = (
            (_to_utc(run.completed_at) - _to_utc(run.started_at)).total_seconds()
            if run.completed_at and run.started_at
            else (_to_utc(now) - _to_utc(run.started_at)).total_seconds() if run.started_at else None
        )

        timeline_events: list[StageTimelineEvent] = []
        model_usage: dict[str, ModelUsageMetadata] = {}

        # ------------------------------------------------------------------
        # 1. Planning Stage
        # ------------------------------------------------------------------
        planning_data: dict[str, Any] | None = None
        plan = run.plan
        if plan:
            plan_run = plan.planning_run
            plan_duration = (
                (plan_run.completed_at - plan_run.started_at).total_seconds()
                if plan_run and plan_run.completed_at
                else None
            )
            steps_count = len(plan.plan_data.get("implementation_steps", [])) if plan.plan_data else 0

            planning_data = {
                "plan_id": str(plan.id),
                "planning_run_id": str(plan_run.id) if plan_run else None,
                "status": plan_run.status if plan_run else "completed",
                "model_version": plan_run.model_version if plan_run else "gpt-4o",
                "prompt_version": plan_run.prompt_version if plan_run else "mysde.plan.v1",
                "steps_count": steps_count,
                "duration_seconds": plan_duration,
                "started_at": plan_run.started_at if plan_run else None,
                "completed_at": plan_run.completed_at if plan_run else None,
            }

            if plan_run:
                timeline_events.append(
                    StageTimelineEvent(
                        stage="planning",
                        event="Planning initiated",
                        status="started",
                        timestamp=plan_run.started_at,
                    )
                )
                if plan_run.completed_at:
                    timeline_events.append(
                        StageTimelineEvent(
                            stage="planning",
                            event=f"Implementation plan generated ({steps_count} steps)",
                            status=plan_run.status,
                            timestamp=plan_run.completed_at,
                            duration_seconds=plan_duration,
                            details={"steps_count": steps_count, "schema_version": plan.schema_version},
                        )
                    )

                model_usage["planning"] = ModelUsageMetadata(
                    model_name=plan_run.model_version or "gpt-4o",
                    calls_count=1,
                    prompt_tokens="unavailable",
                    completion_tokens="unavailable",
                    estimated_cost_usd="unavailable",
                )

        # ------------------------------------------------------------------
        # 2. Execution Stage
        # ------------------------------------------------------------------
        timeline_events.append(
            StageTimelineEvent(
                stage="execution",
                event=f"Execution run started in sandbox ({run.sandbox_provider})",
                status="started",
                timestamp=run.started_at,
                details={"sandbox_image": run.sandbox_image, "base_commit_sha": run.base_commit_sha[:8]},
            )
        )

        patch_data: dict[str, Any] | None = None
        active_patch = db.scalar(
            select(PatchArtifact)
            .where(PatchArtifact.execution_run_id == run.id)
            .order_by(PatchArtifact.created_at.desc(), PatchArtifact.id.desc())
        )
        if active_patch:
            patch_data = {
                "id": str(active_patch.id),
                "patch_hash": active_patch.patch_hash,
                "validation_status": active_patch.validation_status,
                "changed_files_count": active_patch.changed_files_count,
                "additions_count": active_patch.additions_count,
                "deletions_count": active_patch.deletions_count,
                "changed_files": [f.get("file_path") for f in active_patch.changed_files] if active_patch.changed_files else [],
                "created_at": active_patch.created_at,
            }
            timeline_events.append(
                StageTimelineEvent(
                    stage="execution",
                    event=f"Patch proposal created ({active_patch.changed_files_count} files, +{active_patch.additions_count}/-{active_patch.deletions_count})",
                    status="patch_proposed",
                    timestamp=active_patch.created_at,
                    details={"patch_hash": active_patch.patch_hash[:12]},
                )
            )

        # ------------------------------------------------------------------
        # 3. Verification Stage
        # ------------------------------------------------------------------
        verification_results = db.scalars(
            select(VerificationResult)
            .where(VerificationResult.execution_run_id == run.id)
            .order_by(VerificationResult.created_at.asc())
        ).all()

        passed_checks = sum(1 for v in verification_results if v.status == "passed")
        failed_checks = sum(1 for v in verification_results if v.status != "passed")
        total_verif_duration = sum(v.duration_seconds for v in verification_results)

        verification_data = {
            "total_checks": len(verification_results),
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "all_passed": len(verification_results) > 0 and failed_checks == 0,
            "duration_seconds": total_verif_duration,
            "checks": [
                {
                    "check_type": v.verification_type,
                    "command_name": v.command_name,
                    "status": v.status,
                    "exit_code": v.exit_code,
                    "duration_seconds": v.duration_seconds,
                    "created_at": v.created_at,
                }
                for v in verification_results
            ],
        }

        for v in verification_results:
            timeline_events.append(
                StageTimelineEvent(
                    stage="verification",
                    event=f"Check '{v.command_name}' {v.status} (exit {v.exit_code})",
                    status=v.status,
                    timestamp=v.created_at,
                    duration_seconds=v.duration_seconds,
                    details={"verification_type": v.verification_type, "command": v.command_name},
                )
            )

        if run.completed_at:
            timeline_events.append(
                StageTimelineEvent(
                    stage="execution",
                    event=f"Execution run finished with status '{run.status}'",
                    status=run.status,
                    timestamp=run.completed_at,
                    duration_seconds=exec_duration,
                    details={"safe_error_summary": run.safe_error_summary},
                )
            )

        # ------------------------------------------------------------------
        # 4. Repair Stage (if present)
        # ------------------------------------------------------------------
        repair_data: dict[str, Any] | None = None
        latest_repair = db.scalar(
            select(RepairRun)
            .where(RepairRun.execution_run_id == run.id)
            .order_by(RepairRun.created_at.desc())
        )
        if latest_repair:
            repair_duration = (
                (latest_repair.completed_at - latest_repair.started_at).total_seconds()
                if latest_repair.completed_at
                else None
            )
            repair_data = {
                "repair_run_id": str(latest_repair.id),
                "status": latest_repair.status,
                "final_outcome": latest_repair.final_outcome,
                "consumed_attempts": latest_repair.consumed_attempts,
                "max_attempts": latest_repair.max_attempts,
                "consumed_model_calls": latest_repair.consumed_model_calls,
                "duration_seconds": repair_duration,
                "attempts": [
                    {
                        "attempt_number": a.attempt_number,
                        "failure_category": a.failure_category,
                        "proposal_status": a.proposal_status,
                        "duration_seconds": a.duration_seconds,
                    }
                    for a in latest_repair.attempts
                ],
            }

            timeline_events.append(
                StageTimelineEvent(
                    stage="repair",
                    event=f"Automated repair initiated (budget: {latest_repair.max_attempts} attempts)",
                    status="repair_started",
                    timestamp=latest_repair.started_at,
                )
            )
            if latest_repair.completed_at:
                timeline_events.append(
                    StageTimelineEvent(
                        stage="repair",
                        event=f"Repair completed: outcome '{latest_repair.final_outcome}' after {latest_repair.consumed_attempts} attempt(s)",
                        status=latest_repair.status,
                        timestamp=latest_repair.completed_at,
                        duration_seconds=repair_duration,
                        details={"final_outcome": latest_repair.final_outcome},
                    )
                )

            model_usage["repair"] = ModelUsageMetadata(
                model_name="gpt-4o",
                calls_count=latest_repair.consumed_model_calls,
                prompt_tokens="unavailable",
                completion_tokens="unavailable",
                estimated_cost_usd="unavailable",
            )

        # ------------------------------------------------------------------
        # 5. Publishing Stage (if present)
        # ------------------------------------------------------------------
        publishing_data: dict[str, Any] | None = None
        pub_run = db.scalar(
            select(PublishingRun)
            .where(PublishingRun.execution_run_id == run.id)
            .order_by(PublishingRun.created_at.desc())
        )
        if pub_run:
            pub_duration = (
                (pub_run.published_at - pub_run.approved_at).total_seconds()
                if pub_run.published_at and pub_run.approved_at
                else None
            )
            publishing_data = {
                "publishing_run_id": str(pub_run.id),
                "status": pub_run.status,
                "head_branch": pub_run.head_branch,
                "head_commit_sha": pub_run.head_commit_sha,
                "pr_number": pub_run.pr_number,
                "pr_url": pub_run.pr_url,
                "pr_title": pub_run.pr_title,
                "pr_state": pub_run.pr_state,
                "retry_count": pub_run.retry_count,
                "approved_at": pub_run.approved_at,
                "published_at": pub_run.published_at,
            }

            if pub_run.approved_at:
                timeline_events.append(
                    StageTimelineEvent(
                        stage="publishing",
                        event=f"Patch approved for branch '{pub_run.head_branch}'",
                        status="approved",
                        timestamp=pub_run.approved_at,
                        details={"approved_patch_hash": pub_run.approved_patch_hash[:12] if pub_run.approved_patch_hash else None},
                    )
                )
            if pub_run.published_at and pub_run.pr_url:
                timeline_events.append(
                    StageTimelineEvent(
                        stage="publishing",
                        event=f"Pull request #{pub_run.pr_number} successfully published",
                        status="completed",
                        timestamp=pub_run.published_at,
                        duration_seconds=pub_duration,
                        details={"pr_url": pub_run.pr_url, "pr_number": pub_run.pr_number},
                    )
                )

        # Sort timeline chronologically
        timeline_events.sort(key=lambda x: _to_utc(x.timestamp))

        return RunTraceResponse(
            execution_run_id=run.id,
            workspace_id=run.workspace_id,
            task_id=task.id,
            task_title=task.title,
            task_type=task.task_type,
            repository_name=run.repository.full_name if run.repository else None,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_seconds=exec_duration,
            sandbox_provider=run.sandbox_provider,
            sandbox_image=run.sandbox_image,
            safe_error_summary=run.safe_error_summary,
            planning=planning_data,
            patch=patch_data,
            verification=verification_data,
            repair=repair_data,
            publishing=publishing_data,
            timeline=timeline_events,
            model_usage=model_usage,
        )

    @staticmethod
    def get_workspace_metrics(
        db: Session,
        workspace_id: uuid.UUID,
        time_window_days: int = 30,
    ) -> ObservabilityMetricsResponse:
        """
        Calculates aggregate reliability, duration, and error category metrics
        with clearly defined denominators over the requested time window.
        """
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=time_window_days)

        # Query all execution runs in the time window for this workspace
        runs = db.scalars(
            select(ExecutionRun).where(
                ExecutionRun.workspace_id == workspace_id,
                ExecutionRun.started_at >= start_date,
            )
        ).all()

        # Terminal statuses define the denominator for reliability metrics
        terminal_statuses = {"completed", "failed", "cancelled", "timed_out"}
        terminal_runs = [r for r in runs if r.status in terminal_statuses]

        successful_runs = 0
        failed_runs = 0
        cancelled_runs = 0
        timed_out_runs = 0

        failure_categories: dict[str, int] = {
            "verification_failed": 0,
            "stale_base_conflict": 0,
            "timed_out": 0,
            "cancelled": 0,
            "infrastructure_error": 0,
        }

        durations_list: list[float] = []

        for r in runs:
            if r.status == "completed":
                successful_runs += 1
            elif r.status == "failed":
                failed_runs += 1
                summary = (r.safe_error_summary or "").lower()
                if "verification" in summary or "check" in summary:
                    failure_categories["verification_failed"] += 1
                elif "stale base" in summary or "conflict" in summary:
                    failure_categories["stale_base_conflict"] += 1
                else:
                    failure_categories["infrastructure_error"] += 1
            elif r.status == "cancelled":
                cancelled_runs += 1
                failure_categories["cancelled"] += 1
            elif r.status == "timed_out":
                timed_out_runs += 1
                failure_categories["timed_out"] += 1

            if r.completed_at and r.started_at:
                durations_list.append((_to_utc(r.completed_at) - _to_utc(r.started_at)).total_seconds())

        total_terminal = len(terminal_runs)
        success_rate = (
            round((successful_runs / total_terminal) * 100, 1)
            if total_terminal > 0
            else None
        )

        # Average duration calculations
        avg_exec_duration = (
            round(sum(durations_list) / len(durations_list), 2)
            if durations_list
            else 0.0
        )

        # Repair metrics in this workspace
        repair_runs = db.scalars(
            select(RepairRun).where(
                RepairRun.workspace_id == workspace_id,
                RepairRun.started_at >= start_date,
            )
        ).all()
        total_repairs = len(repair_runs)
        repairs_succeeded = sum(1 for rep in repair_runs if rep.final_outcome == "verified_success")

        # Model usage counts
        model_counts: dict[str, int] = {}
        for r in runs:
            if r.plan and r.plan.planning_run:
                m = r.plan.planning_run.model_version or "gpt-4o"
                model_counts[m] = model_counts.get(m, 0) + 1
        for rep in repair_runs:
            model_counts["gpt-4o"] = model_counts.get("gpt-4o", 0) + rep.consumed_model_calls

        return ObservabilityMetricsResponse(
            workspace_id=workspace_id,
            time_window_days=time_window_days,
            total_runs=total_terminal,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            cancelled_runs=cancelled_runs,
            timed_out_runs=timed_out_runs,
            success_rate_percent=success_rate,
            failure_categories={k: v for k, v in failure_categories.items() if v > 0},
            total_repairs=total_repairs,
            repairs_succeeded=repairs_succeeded,
            average_durations_seconds={"average_run_duration": avg_exec_duration},
            model_usage_summary=model_counts,
        )

    @staticmethod
    def list_workspace_runs(
        db: Session,
        workspace_id: uuid.UUID,
        status_filter: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
    ) -> list[ObservabilityRunSummary]:
        """List execution runs for an authorized workspace with multi-attribute filtering."""
        stmt = (
            select(ExecutionRun)
            .where(ExecutionRun.workspace_id == workspace_id)
            .order_by(ExecutionRun.created_at.desc())
        )

        if status_filter and status_filter != "all":
            stmt = stmt.where(ExecutionRun.status == status_filter)
        if date_from:
            stmt = stmt.where(ExecutionRun.created_at >= date_from)
        if date_to:
            stmt = stmt.where(ExecutionRun.created_at <= date_to)

        stmt = stmt.limit(min(limit, 100))
        runs = db.scalars(stmt).all()

        results: list[ObservabilityRunSummary] = []
        for r in runs:
            task = r.task
            duration = (
                (_to_utc(r.completed_at) - _to_utc(r.started_at)).total_seconds()
                if r.completed_at and r.started_at
                else None
            )

            # Verification status
            verif_results = db.scalars(
                select(VerificationResult).where(VerificationResult.execution_run_id == r.id)
            ).all()
            verif_passed = (
                (len(verif_results) > 0 and all(v.status == "passed" for v in verif_results))
                if verif_results
                else None
            )

            # Repair count
            rep_run = db.scalar(
                select(RepairRun).where(RepairRun.execution_run_id == r.id).order_by(RepairRun.created_at.desc())
            )
            repair_attempts = rep_run.consumed_attempts if rep_run else 0

            # Publishing PR details
            pub_run = db.scalar(
                select(PublishingRun).where(PublishingRun.execution_run_id == r.id).order_by(PublishingRun.created_at.desc())
            )
            pr_number = pub_run.pr_number if pub_run else None
            pr_url = pub_run.pr_url if pub_run else None

            results.append(
                ObservabilityRunSummary(
                    id=r.id,
                    task_id=task.id,
                    task_title=task.title,
                    task_type=task.task_type,
                    status=r.status,
                    started_at=r.started_at,
                    completed_at=r.completed_at,
                    duration_seconds=duration,
                    verification_passed=verif_passed,
                    repair_attempts=repair_attempts,
                    pr_number=pr_number,
                    pr_url=pr_url,
                    safe_error_summary=r.safe_error_summary,
                )
            )

        return results
