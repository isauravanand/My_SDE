import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.execution.patch.validator import (
    PROTECTED_PATH_PATTERNS,
    PatchValidationError,
    PatchValidator,
)
from app.integrations.github.client import GitHubApiClient, GitHubApiError
from app.models.execution import ExecutionRun, PatchArtifact, VerificationResult
from app.models.publishing import PublishingRun
from app.models.user import User
from app.schemas.publishing import PublishingPrecheckResponse
from app.services.activity import ActivityService

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Convert text to safe URL/branch slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


class GitPublishingService:
    """Orchestrates secure human-approved Git branch publishing and Pull Request creation."""

    def __init__(
        self,
        github_client: GitHubApiClient | None = None,
        settings: Settings | None = None,
    ):
        self.github_client = github_client or GitHubApiClient()
        self.settings = settings or get_settings()

    def precheck_publishing(
        self,
        db: Session,
        execution_run_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user: User,
    ) -> PublishingPrecheckResponse:
        """Evaluate all server-side prerequisites before permitting publishing."""
        execution_run = db.scalar(
            select(ExecutionRun).where(
                ExecutionRun.id == execution_run_id,
                ExecutionRun.workspace_id == workspace_id,
            )
        )
        if not execution_run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execution run not found in active workspace.",
            )

        blockers: list[str] = []

        # 1. Execution status check
        if execution_run.status not in ("completed", "repaired"):
            blockers.append(f"Execution run is '{execution_run.status}', but must be 'completed'.")

        # 2. Check active patch artifact
        patch_artifact = db.scalar(
            select(PatchArtifact)
            .where(PatchArtifact.execution_run_id == execution_run.id)
            .order_by(PatchArtifact.created_at.desc(), PatchArtifact.id.desc())
        )
        if not patch_artifact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No patch proposal found for this execution run.",
            )

        current_patch_hash = patch_artifact.patch_hash

        # 3. Verification checks evaluation
        verification_results = db.scalars(
            select(VerificationResult).where(
                VerificationResult.execution_run_id == execution_run.id
            )
        ).all()

        passed_checks = sum(1 for v in verification_results if v.status == "passed")
        failed_checks = sum(1 for v in verification_results if v.status != "passed")

        verification_passed = len(verification_results) > 0 and failed_checks == 0
        if len(verification_results) == 0:
            blockers.append("No verification checks have been run for this execution.")
        elif failed_checks > 0:
            blockers.append(f"{failed_checks} verification check(s) failed or were not successful.")

        # 4. Check publishing approval record
        publishing_run = db.scalar(
            select(PublishingRun)
            .where(PublishingRun.execution_run_id == execution_run.id)
            .order_by(PublishingRun.created_at.desc())
        )

        is_approved = False
        approved_patch_hash = None
        is_patch_stale = False

        if publishing_run and publishing_run.approved_at is not None:
            approved_patch_hash = publishing_run.approved_patch_hash
            if approved_patch_hash == current_patch_hash:
                is_approved = True
            else:
                is_patch_stale = True
                blockers.append("Approval was invalidated because the patch was modified or regenerated.")
        else:
            blockers.append("Explicit human approval is required before publishing.")

        # 5. Check connected repository & remote base branch
        repo = (
            execution_run.repository
            or (execution_run.task.repository if execution_run.task else None)
            or (execution_run.task.project.repository if execution_run.task and execution_run.task.project else None)
        )
        if repo and not execution_run.repository_id:
            execution_run.repository_id = repo.id
            if execution_run.task and not execution_run.task.repository_id:
                execution_run.task.repository_id = repo.id
            db.commit()
        remote_base_sha = None
        is_base_stale = False
        default_branch = repo.default_branch if repo else "main"

        if repo and repo.installation:
            try:
                remote_base_sha = self.github_client.get_ref_commit(
                    installation_id=repo.installation.installation_id,
                    owner=repo.owner_login,
                    repo=repo.name,
                    ref=default_branch,
                )
                if remote_base_sha != execution_run.base_commit_sha:
                    is_base_stale = True
                    blockers.append(
                        f"Base branch '{default_branch}' has moved on remote ({remote_base_sha[:8]} != {execution_run.base_commit_sha[:8]}). Stale base conflict detected."
                    )
            except Exception as e:
                logger.warning(f"Could not verify remote base branch commit: {e}")

        can_publish = (
            verification_passed
            and is_approved
            and not is_patch_stale
            and not is_base_stale
            and len(blockers) == 0
        )

        return PublishingPrecheckResponse(
            can_publish=can_publish,
            is_approved=is_approved,
            approved_patch_hash=approved_patch_hash,
            current_patch_hash=current_patch_hash,
            is_patch_stale=is_patch_stale,
            verification_passed=verification_passed,
            passed_checks_count=passed_checks,
            failed_checks_count=failed_checks,
            execution_base_sha=execution_run.base_commit_sha,
            remote_base_sha=remote_base_sha,
            is_base_stale=is_base_stale,
            blockers=blockers,
            repository_full_name=repo.full_name if repo else None,
            default_branch=default_branch,
        )

    def approve_publishing(
        self,
        db: Session,
        execution_run_id: uuid.UUID,
        patch_hash: str,
        workspace_id: uuid.UUID,
        user: User,
    ) -> PublishingRun:
        """Approve the exact patch hash for Git publishing."""
        execution_run = db.scalar(
            select(ExecutionRun).where(
                ExecutionRun.id == execution_run_id,
                ExecutionRun.workspace_id == workspace_id,
            )
        )
        if not execution_run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execution run not found in active workspace.",
            )

        patch_artifact = db.scalar(
            select(PatchArtifact)
            .where(PatchArtifact.execution_run_id == execution_run.id)
            .order_by(PatchArtifact.created_at.desc(), PatchArtifact.id.desc())
        )
        if not patch_artifact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No patch proposal found for this execution run.",
            )

        effective_patch_hash = patch_hash or patch_artifact.patch_hash
        if patch_hash and patch_artifact.patch_hash != patch_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provided patch hash does not match current active patch proposal.",
            )

        # File safety validation on patch before approval
        try:
            parsed_validation = PatchValidator.validate_patch(patch_artifact.raw_diff)
            for f in parsed_validation.changed_files:
                path_obj = Path(f.file_path)
                if path_obj.is_absolute() or ".." in path_obj.parts:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Security violation: path traversal or absolute path '{f.file_path}' rejected.",
                    )
                for pattern in PROTECTED_PATH_PATTERNS:
                    if pattern.search(f.file_path):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Security violation: protected file '{f.file_path}' cannot be published.",
                        )
        except PatchValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security violation: {e}",
            ) from e

        # Verification check rule: at least 1 check, 0 failures
        verification_results = db.scalars(
            select(VerificationResult).where(
                VerificationResult.execution_run_id == execution_run.id
            )
        ).all()
        if not verification_results or any(v.status != "passed" for v in verification_results):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot approve publishing: execution verification checks have not all passed.",
            )

        repo = (
            execution_run.repository
            or (execution_run.task.repository if execution_run.task else None)
            or (execution_run.task.project.repository if execution_run.task and execution_run.task.project else None)
        )
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot publish: execution run has no connected GitHub repository.",
            )
        if not execution_run.repository_id:
            execution_run.repository_id = repo.id
            if execution_run.task and not execution_run.task.repository_id:
                execution_run.task.repository_id = repo.id
            db.commit()

        task = execution_run.task
        task_slug = slugify(task.title)[:24]
        head_branch = f"mysde/task-{task.id.hex[:8]}-{task_slug}"
        base_branch = repo.default_branch or "main"

        # Unique idempotency key based on execution, patch, and branch
        idempotency_key = hashlib.sha256(
            f"{execution_run.id}:{effective_patch_hash}:{head_branch}".encode()
        ).hexdigest()

        publishing_run = db.scalar(
            select(PublishingRun).where(
                PublishingRun.execution_run_id == execution_run.id
            )
        )

        now = datetime.now(timezone.utc)
        if not publishing_run:
            publishing_run = PublishingRun(
                workspace_id=workspace_id,
                task_id=task.id,
                execution_run_id=execution_run.id,
                repository_id=repo.id,
                patch_artifact_id=patch_artifact.id,
                requested_by_user_id=user.id,
                approved_by_user_id=user.id,
                approved_patch_hash=effective_patch_hash,
                approved_at=now,
                status="approved",
                base_branch=base_branch,
                base_commit_sha=execution_run.base_commit_sha,
                head_branch=head_branch,
                idempotency_key=idempotency_key,
                changed_files=patch_artifact.changed_files,
            )
            db.add(publishing_run)
        else:
            publishing_run.approved_by_user_id = user.id
            publishing_run.approved_at = now
            publishing_run.approved_patch_hash = effective_patch_hash
            publishing_run.status = "approved"
            publishing_run.patch_artifact_id = patch_artifact.id
            publishing_run.changed_files = patch_artifact.changed_files
            publishing_run.safe_error_summary = None

        db.commit()
        db.refresh(publishing_run)

        ActivityService.log_activity(
            db=db,
            workspace_id=workspace_id,
            actor_id=user.id,
            event_type="publishing_approved",
            resource_type="publishing_run",
            resource_id=publishing_run.id,
            metadata={
                "task_id": str(task.id),
                "patch_hash": patch_hash,
                "head_branch": head_branch,
            },
        )

        return publishing_run

    def publish_to_github(
        self,
        db: Session,
        execution_run_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user: User,
        base_branch_override: str | None = None,
        custom_pr_title: str | None = None,
        custom_pr_body: str | None = None,
    ) -> PublishingRun:
        """
        Execute Git branch creation, commit creation, and Pull Request creation.
        Guarantees idempotency and prevents concurrent duplicates.
        """
        execution_run = db.scalar(
            select(ExecutionRun).where(
                ExecutionRun.id == execution_run_id,
                ExecutionRun.workspace_id == workspace_id,
            )
        )
        if not execution_run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execution run not found in active workspace.",
            )

        patch_artifact = db.scalar(
            select(PatchArtifact)
            .where(PatchArtifact.execution_run_id == execution_run.id)
            .order_by(PatchArtifact.created_at.desc(), PatchArtifact.id.desc())
        )
        if not patch_artifact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No patch proposal found for this execution run.",
            )

        publishing_run = db.scalar(
            select(PublishingRun).where(
                PublishingRun.execution_run_id == execution_run.id
            )
        )

        if not publishing_run or not publishing_run.approved_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Publishing must be explicitly approved before executing.",
            )

        if publishing_run.approved_patch_hash != patch_artifact.patch_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approval was invalidated because the patch was modified or regenerated.",
            )

        # Idempotency check: if already completed, return existing PR
        if publishing_run.status == "completed" and publishing_run.pr_url:
            return publishing_run

        # Concurrency check
        if publishing_run.status in ("preparing", "pushing_branch", "creating_pr"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Publishing is currently in progress for this execution run.",
            )

        repo = (
            execution_run.repository
            or (execution_run.task.repository if execution_run.task else None)
            or (execution_run.task.project.repository if execution_run.task and execution_run.task.project else None)
        )
        if not repo or not repo.installation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No connected GitHub repository or installation found.",
            )
        if not execution_run.repository_id:
            execution_run.repository_id = repo.id
            if execution_run.task and not execution_run.task.repository_id:
                execution_run.task.repository_id = repo.id
            db.commit()

        target_base = base_branch_override or publishing_run.base_branch or repo.default_branch or "main"

        # Stale-base branch check against remote
        try:
            remote_base_sha = self.github_client.get_ref_commit(
                installation_id=repo.installation.installation_id,
                owner=repo.owner_login,
                repo=repo.name,
                ref=target_base,
            )
            if remote_base_sha != execution_run.base_commit_sha:
                publishing_run.status = "stale_base_conflict"
                publishing_run.safe_error_summary = (
                    f"Remote base branch '{target_base}' has new commits ({remote_base_sha[:8]} != {execution_run.base_commit_sha[:8]}). "
                    "Re-run verification against the latest commit before publishing."
                )
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=publishing_run.safe_error_summary,
                )
        except HTTPException:
            raise
        except GitHubApiError as e:
            raise HTTPException(
                status_code=e.status_code,
                detail=f"GitHub API error checking base branch '{target_base}': {e.message}",
            ) from e

        # Mark in progress
        publishing_run.status = "preparing"
        publishing_run.retry_count += 1
        db.commit()

        # Controlled Server-Side Workspace & File Safety Validation
        try:
            # 1. Parse changed files from patch
            parsed_validation = PatchValidator.validate_patch(patch_artifact.raw_diff)
            for f in parsed_validation.changed_files:
                path_obj = Path(f.file_path)
                if path_obj.is_absolute() or ".." in path_obj.parts:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Security violation: path traversal or absolute path '{f.file_path}' rejected.",
                    )
                for pattern in PROTECTED_PATH_PATTERNS:
                    if pattern.search(f.file_path):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Security violation: protected file '{f.file_path}' cannot be published.",
                        )

            # 2. Extract reconstructed file content from patch
            file_changes = self._extract_files_from_patch(patch_artifact.raw_diff)

            # 3. Create Git objects via GitHub Data API (or resume if branch exists)
            publishing_run.status = "pushing_branch"
            db.commit()

            installation_id = repo.installation.installation_id
            owner = repo.owner_login
            repo_name = repo.name

            # Check if branch exists
            branch_ref = self.github_client.get_ref(
                installation_id, owner, repo_name, f"heads/{publishing_run.head_branch}"
            )
            if not branch_ref:
                # Create branch reference pointing to base_commit_sha
                branch_ref = self.github_client.create_branch(
                    installation_id=installation_id,
                    owner=owner,
                    repo=repo_name,
                    branch_name=publishing_run.head_branch,
                    commit_sha=execution_run.base_commit_sha,
                )

            # Create blobs and tree
            tree_items: list[dict[str, Any]] = []
            for file_path, file_content in file_changes.items():
                blob_sha = self.github_client.create_blob(
                    installation_id=installation_id,
                    owner=owner,
                    repo=repo_name,
                    content=file_content.encode("utf-8"),
                )
                tree_items.append({
                    "path": file_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                })

            # Create tree based on base_commit_sha
            new_tree_sha = self.github_client.create_tree(
                installation_id=installation_id,
                owner=owner,
                repo=repo_name,
                tree_items=tree_items,
                base_tree_sha=execution_run.base_commit_sha,
            )
            if isinstance(new_tree_sha, dict):
                new_tree_sha = new_tree_sha.get("sha")

            # Create commit
            task = execution_run.task
            commit_message = f"feat({task.task_type}): {task.title}\n\nTask ID: {task.id}\nExecution Run: {execution_run.id}"
            new_commit_sha = self.github_client.create_commit(
                installation_id=installation_id,
                owner=owner,
                repo=repo_name,
                message=commit_message,
                tree_sha=new_tree_sha,
                parent_shas=[execution_run.base_commit_sha],
            )
            if isinstance(new_commit_sha, dict):
                new_commit_sha = new_commit_sha.get("sha")
            publishing_run.head_commit_sha = new_commit_sha

            # Update branch ref
            self.github_client.update_ref(
                installation_id=installation_id,
                owner=owner,
                repo=repo_name,
                ref=f"heads/{publishing_run.head_branch}",
                commit_sha=new_commit_sha,
            )

            # 4. Create Pull Request
            publishing_run.status = "creating_pr"
            db.commit()

            pr_title = custom_pr_title or f"[{task.task_type.upper()}] {task.title}"
            pr_body = custom_pr_body or self._generate_pr_body(execution_run, patch_artifact)

            pr_data = self.github_client.create_pull_request(
                installation_id=installation_id,
                owner=owner,
                repo=repo_name,
                title=pr_title,
                body=pr_body,
                head=publishing_run.head_branch,
                base=target_base,
            )

            publishing_run.pr_number = pr_data.get("number")
            publishing_run.pr_url = pr_data.get("html_url")
            publishing_run.pr_title = pr_title
            publishing_run.pr_body = pr_body
            publishing_run.pr_state = pr_data.get("state", "open")
            publishing_run.status = "completed"
            publishing_run.published_at = datetime.now(timezone.utc)
            publishing_run.safe_error_summary = None

            # Update Task status to in_review
            task.status = "in_review"

            db.commit()
            db.refresh(publishing_run)

            ActivityService.log_activity(
                db=db,
                workspace_id=workspace_id,
                actor_id=user.id,
                event_type="github_pr_published",
                resource_type="publishing_run",
                resource_id=publishing_run.id,
                metadata={
                    "pr_number": publishing_run.pr_number,
                    "pr_url": publishing_run.pr_url,
                    "head_branch": publishing_run.head_branch,
                    "commit_sha": publishing_run.head_commit_sha,
                },
            )

            return publishing_run

        except PatchValidationError as e:
            publishing_run.status = "failed"
            publishing_run.safe_error_summary = f"Security violation: {e}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=publishing_run.safe_error_summary,
            ) from e
        except HTTPException:
            publishing_run.status = "failed"
            db.commit()
            raise
        except GitHubApiError as e:
            publishing_run.status = "failed"
            publishing_run.safe_error_summary = f"GitHub API error: {e.message}"
            db.commit()
            raise HTTPException(
                status_code=e.status_code,
                detail=publishing_run.safe_error_summary,
            ) from e
        except Exception as e:
            logger.exception("Unexpected error during Git publishing workflow")
            publishing_run.status = "failed"
            publishing_run.safe_error_summary = f"Publishing failed: {str(e)}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Publishing workflow encountered an internal error. You can safely retry.",
            ) from e

    def _extract_files_from_patch(self, raw_diff: str) -> dict[str, str]:
        """Extract modified file paths and their updated content from unified diff."""
        file_contents: dict[str, str] = {}
        current_file: str | None = None
        current_lines: list[str] = []

        for line in raw_diff.splitlines():
            if line.startswith("diff --git a/"):
                if current_file:
                    file_contents[current_file] = "\n".join(current_lines)
                parts = line.split(" b/")
                if len(parts) == 2:
                    current_file = parts[1].strip()
                    current_lines = []
                else:
                    current_file = None
            elif current_file and (line.startswith("+") and not line.startswith("+++")):
                current_lines.append(line[1:])
            elif current_file and (line.startswith(" ") or not (line.startswith("-") or line.startswith("@@"))):
                if line.startswith(" "):
                    current_lines.append(line[1:])
                elif not line.startswith("---") and not line.startswith("+++"):
                    current_lines.append(line)

        if current_file:
            file_contents[current_file] = "\n".join(current_lines)

        return file_contents

    def _generate_pr_body(self, execution_run: ExecutionRun, patch_artifact: PatchArtifact) -> str:
        """Generate a reviewable, audit-linked Markdown PR description."""
        task = execution_run.task
        verification_results = execution_run.verification_results

        checks_rows = []
        for v in verification_results:
            icon = "✅" if v.status == "passed" else "❌"
            checks_rows.append(f"| `{v.command_name}` | {icon} {v.status.upper()} | {v.duration_seconds:.2f}s |")

        checks_table = (
            "| Command | Status | Duration |\n|---|---|---|\n" + "\n".join(checks_rows)
            if checks_rows
            else "_No verification commands configured._"
        )

        files_list = "\n".join([f"- `{f.get('file_path')}` (+{f.get('additions', 0)} / -{f.get('deletions', 0)})" for f in patch_artifact.changed_files])

        return f"""## 🤖 MySDE Automated Pull Request

### Task Context
- **Task:** {task.title}
- **Type:** `{task.task_type}`
- **Priority:** `{task.priority}`
- **Task ID:** `{task.id}`

### Description
{task.description or '_No description provided._'}

### Changed Files
{files_list or '_None_'}

### Verification Evidence
{checks_table}

---
*Grounded by MySDE Agentic AI Engine. Human approval confirmed prior to branch publication.*
"""


publishing_service = GitPublishingService()
