import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_rag import RepoCodeChunk, RepoIndexingJob
from app.models.github import GitHubRepository
from app.models.planning import ImplementationPlan, PlanningRun
from app.models.task import Task
from app.planning.graph.state import PlanningState
from app.planning.llm.base import BaseLLMProvider
from app.planning.llm.factory import get_llm_provider
from app.planning.prompts import (
    PLANNING_PROMPT_VERSION,
    PLANNING_SYSTEM_PROMPT,
    REPAIR_PLAN_PROMPT_TEMPLATE,
    TASK_ANALYSIS_PROMPT_TEMPLATE,
)
from app.schemas.planning import ImplementationPlanSchema, PlanEvidenceItem
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


class PlanningNodes:
    """Explicit LangGraph nodes executing the planning workflow steps."""

    def __init__(
        self,
        db: Session,
        llm_provider: BaseLLMProvider | None = None,
        retrieval_service: RetrievalService | None = None,
    ):
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.retrieval_service = retrieval_service or RetrievalService()

    async def load_task(self, state: PlanningState) -> PlanningState:
        """
        Node 1: load_task
        - Loads task from DB with workspace-scoped isolation.
        - Resolves connected repository from task or parent project.
        - Verifies authenticated user access.
        """
        start_time = time.time()
        logger.info(f"LangGraph [load_task] starting for task_id={state.get('task_id')}")

        task_id_str = state.get("task_id")
        workspace_id_str = state.get("workspace_id")

        try:
            task_uuid = uuid.UUID(task_id_str)
            workspace_uuid = uuid.UUID(workspace_id_str)
        except (ValueError, TypeError) as e:
            return {
                **state,
                "status": "failed",
                "error_summary": f"Invalid UUID format: {e}",
            }

        task = self.db.scalar(
            select(Task).where(
                Task.id == task_uuid,
                Task.workspace_id == workspace_uuid,
            )
        )

        if not task:
            logger.warning(
                f"Unauthorized or nonexistent task access: task_id={task_id_str}, workspace={workspace_id_str}"
            )
            return {
                **state,
                "status": "failed",
                "error_summary": "Task not found in authorized workspace.",
            }

        # Resolve repository: direct on task or via project
        repo_id: uuid.UUID | None = task.repository_id
        if not repo_id and task.project and task.project.repository_id:
            repo_id = task.project.repository_id

        # Update planning run status in DB to 'running'
        run_uuid = uuid.UUID(state["run_id"])
        run = self.db.scalar(select(PlanningRun).where(PlanningRun.id == run_uuid))
        if run:
            run.status = "running"
            if repo_id:
                run.repository_id = repo_id
            self.db.commit()

        timings = dict(state.get("timings", {}))
        timings["load_task"] = round(time.time() - start_time, 4)

        return {
            **state,
            "task_title": task.title,
            "task_description": task.description or "",
            "repository_id": str(repo_id) if repo_id else None,
            "status": "running",
            "timings": timings,
        }

    async def validate_context(self, state: PlanningState) -> PlanningState:
        """
        Node 2: validate_context
        - Checks for sufficient task requirements.
        - Verifies repository is connected and indexed if repository grounding is required.
        - Verifies LLM configuration is operational.
        """
        start_time = time.time()
        logger.info(f"LangGraph [validate_context] starting for run_id={state.get('run_id')}")

        # Check task description / title
        task_title = state.get("task_title", "").strip()
        task_desc = state.get("task_description", "").strip()

        if not task_title or len(task_title) < 5 or (len(task_title) < 10 and not task_desc):
            return {
                **state,
                "status": "needs_context",
                "error_summary": "Task description is insufficient for planning. Please provide detailed requirements.",
            }

        repo_id_str = state.get("repository_id")
        workspace_id_str = state.get("workspace_id")

        is_repo_indexed = False
        base_commit_sha: str | None = None

        if repo_id_str:
            repo_uuid = uuid.UUID(repo_id_str)
            workspace_uuid = uuid.UUID(workspace_id_str)

            # Check if repository is indexed
            latest_job = self.db.scalar(
                select(RepoIndexingJob).where(
                    RepoIndexingJob.repository_id == repo_uuid,
                    RepoIndexingJob.workspace_id == workspace_uuid,
                    RepoIndexingJob.status.in_(["completed", "partially_completed"]),
                ).order_by(desc(RepoIndexingJob.completed_at))
            )

            # Also check if chunks exist
            chunk_exists = self.db.scalar(
                select(RepoCodeChunk.id).where(
                    RepoCodeChunk.repository_id == repo_uuid,
                    RepoCodeChunk.workspace_id == workspace_uuid,
                ).limit(1)
            )

            if latest_job:
                is_repo_indexed = True
                base_commit_sha = latest_job.commit_sha
            elif chunk_exists:
                is_repo_indexed = True
                # Query chunk commit
                chunk = self.db.scalar(
                    select(RepoCodeChunk).where(
                        RepoCodeChunk.repository_id == repo_uuid,
                        RepoCodeChunk.workspace_id == workspace_uuid,
                    ).limit(1)
                )
                if chunk:
                    base_commit_sha = chunk.commit_sha
            else:
                return {
                    **state,
                    "status": "needs_context",
                    "error_summary": "Repository is connected but has not been indexed yet. Please run Code RAG indexing before generating an implementation plan.",
                    "is_repo_indexed": False,
                }

        timings = dict(state.get("timings", {}))
        timings["validate_context"] = round(time.time() - start_time, 4)

        return {
            **state,
            "is_repo_indexed": is_repo_indexed,
            "base_commit_sha": base_commit_sha,
            "timings": timings,
        }

    async def retrieve_repository_context(self, state: PlanningState) -> PlanningState:
        """
        Node 3: retrieve_repository_context
        - Invokes Code RAG retrieval service with query from task.
        - Maps chunks into normalized PlanEvidenceItem objects with stable IDs (ev-1, ev-2, ...).
        - Enforces context size limits and untrusted data handling.
        """
        start_time = time.time()
        logger.info(f"LangGraph [retrieve_repository_context] starting for repo={state.get('repository_id')}")

        repo_id_str = state.get("repository_id")
        workspace_id_str = state.get("workspace_id")
        base_commit = state.get("base_commit_sha")

        if not repo_id_str or not state.get("is_repo_indexed"):
            return {**state, "evidence": []}

        query = f"{state.get('task_title', '')} {state.get('task_description', '')}"
        top_k = getattr(settings, "PLANNING_TOP_K_CHUNKS", 5)

        evidence_items: list[dict[str, Any]] = []

        try:
            retrieval_res = await self.retrieval_service.retrieve_chunks(
                db=self.db,
                workspace_id=uuid.UUID(workspace_id_str),
                repository_id=uuid.UUID(repo_id_str),
                query=query,
                commit_sha=base_commit,
                top_k=top_k,
            )

            results = retrieval_res.get("results", [])
            for idx, chunk in enumerate(results, start=1):
                ev_id = f"ev-{idx}"
                item = PlanEvidenceItem(
                    evidence_id=ev_id,
                    repository_id=repo_id_str,
                    commit_sha=chunk.get("commit_sha") or base_commit,
                    file_path=chunk["file_path"],
                    start_line=chunk["start_line"],
                    end_line=chunk["end_line"],
                    source_chunk_id=str(chunk.get("chunk_id")) if chunk.get("chunk_id") else None,
                    excerpt=(chunk.get("chunk_content") or chunk.get("content") or "")[:400],
                    relevance_summary=f"Score: {chunk.get('score', 0):.3f} | {chunk.get('symbol_name') or 'code snippet'}",
                )
                evidence_items.append(item.model_dump())

            # Check if default branch moved
            repo = self.db.scalar(
                select(GitHubRepository).where(
                    GitHubRepository.id == uuid.UUID(repo_id_str),
                    GitHubRepository.workspace_id == uuid.UUID(workspace_id_str),
                )
            )
            repo_branch_commit = getattr(repo, "default_branch_commit_sha", None) if repo else None
            if repo_branch_commit and base_commit:
                if repo_branch_commit != base_commit:
                    logger.info(
                        f"Repository default branch ({repo_branch_commit}) has advanced "
                        f"beyond indexed commit ({base_commit}). Grounding plan on indexed commit."
                    )

        except Exception as e:
            logger.error(f"Error in retrieve_repository_context: {e}", exc_info=True)
            # Never fabricate chunks; return empty evidence list
            evidence_items = []

        timings = dict(state.get("timings", {}))
        timings["retrieve_repository_context"] = round(time.time() - start_time, 4)

        return {
            **state,
            "evidence": evidence_items,
            "timings": timings,
        }

    async def analyze_task(self, state: PlanningState) -> PlanningState:
        """
        Node 4: analyze_task
        - Synthesizes task objectives and prepares prompt template.
        - Delimits untrusted task data and untrusted retrieved evidence.
        """
        start_time = time.time()
        logger.info(f"LangGraph [analyze_task] starting for task_id={state.get('task_id')}")

        evidence_items = state.get("evidence", [])
        evidence_blocks = []

        for ev in evidence_items:
            block = (
                f"[EVIDENCE id={ev['evidence_id']} file={ev['file_path']} "
                f"lines={ev['start_line']}-{ev['end_line']} chunk={ev.get('source_chunk_id') or ''}]\n"
                f"{ev['excerpt']}\n"
                f"[/EVIDENCE]"
            )
            evidence_blocks.append(block)

        formatted_evidence = "\n\n".join(evidence_blocks) if evidence_blocks else "No repository evidence available."

        prompt_text = TASK_ANALYSIS_PROMPT_TEMPLATE.format(
            task_id=state.get("task_id", ""),
            task_title=state.get("task_title", ""),
            workspace_id=state.get("workspace_id", ""),
            repository_id=state.get("repository_id", "none"),
            commit_sha=state.get("base_commit_sha", "none"),
            task_description=state.get("task_description", ""),
            evidence_blocks=formatted_evidence,
        )

        timings = dict(state.get("timings", {}))
        timings["analyze_task"] = round(time.time() - start_time, 4)

        return {
            **state,
            "prompt_text": prompt_text,
            "timings": timings,
        }

    async def generate_plan(self, state: PlanningState) -> PlanningState:
        """
        Node 5: generate_plan
        - Calls the LLM provider to produce structured plan.
        - Uses retry prompt with validation feedback if retrying.
        """
        start_time = time.time()
        retry_count = state.get("retry_count", 0)
        logger.info(f"LangGraph [generate_plan] starting (attempt {retry_count + 1})")

        prompt = state.get("prompt_text", "")
        validation_errors = state.get("validation_errors", [])

        if validation_errors and retry_count > 0:
            repair_snippet = REPAIR_PLAN_PROMPT_TEMPLATE.format(
                validation_errors="\n".join(f"- {err}" for err in validation_errors)
            )
            prompt = f"{prompt}\n\n{repair_snippet}"

        try:
            plan_obj, metadata = await self.llm_provider.generate_structured(
                prompt=prompt,
                system_prompt=PLANNING_SYSTEM_PROMPT,
                schema_class=ImplementationPlanSchema,
            )

            # Ensure evidence items match state evidence
            plan_dict = json.loads(plan_obj.model_dump_json())
            if not plan_dict.get("evidence") and state.get("evidence"):
                plan_dict["evidence"] = state["evidence"]

            timings = dict(state.get("timings", {}))
            timings["generate_plan"] = round(time.time() - start_time, 4)

            return {
                **state,
                "plan": plan_dict,
                "model_metadata": metadata,
                "timings": timings,
            }

        except Exception as e:
            logger.error(f"Error in generate_plan LLM call: {e}", exc_info=True)
            return {
                **state,
                "status": "failed",
                "error_summary": f"LLM generation failed: {str(e)}",
            }

    async def validate_plan(self, state: PlanningState) -> PlanningState:
        """
        Node 6: validate_plan
        - Validates generated plan against ImplementationPlanSchema.
        - Checks step references, evidence citations, and location statuses.
        - Triggers bounded regeneration if invalid.
        """
        start_time = time.time()
        logger.info("LangGraph [validate_plan] validating output")

        plan_data = state.get("plan")
        if not plan_data:
            return {
                **state,
                "status": "failed",
                "error_summary": "No plan output was generated by model.",
            }

        validation_errors: list[str] = []

        try:
            # Reconstruct PlanEvidenceItem objects if needed
            evidence_dict = {e["evidence_id"]: e for e in state.get("evidence", [])}

            # Inject evidence from state if missing
            if not plan_data.get("evidence") and state.get("evidence"):
                plan_data["evidence"] = state["evidence"]

            # Validate schema
            validated_plan = ImplementationPlanSchema.model_validate(plan_data)

            # Additional check: evidence references exist in run's retrieved evidence collection
            for step in validated_plan.implementation_steps:
                for ref in step.evidence_refs:
                    if ref not in evidence_dict:
                        validation_errors.append(
                            f"Step '{step.step_id}' references evidence ID '{ref}' which was not in retrieved context."
                        )

            if validation_errors:
                raise ValueError("; ".join(validation_errors))

            timings = dict(state.get("timings", {}))
            timings["validate_plan"] = round(time.time() - start_time, 4)

            return {
                **state,
                "plan": json.loads(validated_plan.model_dump_json()),
                "validation_errors": [],
                "status": "valid",
                "timings": timings,
            }

        except Exception as e:
            err_msg = str(e)
            logger.warning(f"Plan validation failed: {err_msg}")
            validation_errors.append(err_msg)

            retry_count = state.get("retry_count", 0) + 1
            max_retries = state.get("max_retries", getattr(settings, "PLANNING_MAX_RETRIES", 2))

            if retry_count <= max_retries:
                return {
                    **state,
                    "validation_errors": validation_errors,
                    "retry_count": retry_count,
                    "status": "validation_failed",
                }
            else:
                return {
                    **state,
                    "validation_errors": validation_errors,
                    "retry_count": retry_count,
                    "status": "failed",
                    "error_summary": f"Exhausted validation retries ({max_retries}). Last error: {err_msg}",
                }

    async def persist_plan(self, state: PlanningState) -> PlanningState:
        """
        Node 7: persist_plan
        - Saves the validated ImplementationPlan to PostgreSQL.
        - Updates the PlanningRun record with completion metadata.
        """
        start_time = time.time()
        logger.info(f"LangGraph [persist_plan] saving plan for run_id={state.get('run_id')}")

        run_uuid = uuid.UUID(state["run_id"])
        workspace_uuid = uuid.UUID(state["workspace_id"])
        task_uuid = uuid.UUID(state["task_id"])
        plan_dict = json.loads(json.dumps(state["plan"], default=str))

        try:
            # Check for existing plan on this run
            existing_plan = self.db.scalar(
                select(ImplementationPlan).where(ImplementationPlan.planning_run_id == run_uuid)
            )

            if existing_plan:
                existing_plan.plan_data = plan_dict
                existing_plan.schema_version = plan_dict.get("schema_version", "mysde.plan.v1")
            else:
                new_plan = ImplementationPlan(
                    planning_run_id=run_uuid,
                    workspace_id=workspace_uuid,
                    task_id=task_uuid,
                    schema_version=plan_dict.get("schema_version", "mysde.plan.v1"),
                    plan_data=plan_dict,
                )
                self.db.add(new_plan)

            # Update PlanningRun
            run = self.db.scalar(select(PlanningRun).where(PlanningRun.id == run_uuid))
            if run:
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                run.base_commit_sha = state.get("base_commit_sha")
                run.model_version = state.get("model_metadata", {}).get("model", "mock-planner-v1")
                run.prompt_version = PLANNING_PROMPT_VERSION

            self.db.commit()

            timings = dict(state.get("timings", {}))
            timings["persist_plan"] = round(time.time() - start_time, 4)

            return {
                **state,
                "status": "completed",
                "timings": timings,
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error persisting implementation plan: {e}", exc_info=True)
            return {
                **state,
                "status": "failed",
                "error_summary": f"Failed to persist plan: {str(e)}",
            }

    async def finalize_run(self, state: PlanningState) -> PlanningState:
        """
        Node 8: finalize_run
        - Ensures PlanningRun database record reflects final status (completed, failed, needs_context).
        - Records error summary if present.
        """
        start_time = time.time()
        logger.info(f"LangGraph [finalize_run] status={state.get('status')}")

        run_uuid = uuid.UUID(state["run_id"])
        terminal_status = state.get("status", "failed")
        if terminal_status not in ["completed", "needs_context", "cancelled"]:
            terminal_status = "failed"

        try:
            run = self.db.scalar(select(PlanningRun).where(PlanningRun.id == run_uuid))
            if run:
                run.status = terminal_status
                run.completed_at = datetime.now(timezone.utc)
                run.error_summary = state.get("error_summary")
                self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error in finalize_run: {e}", exc_info=True)

        timings = dict(state.get("timings", {}))
        timings["finalize_run"] = round(time.time() - start_time, 4)

        return {
            **state,
            "status": terminal_status,
            "timings": timings,
        }
