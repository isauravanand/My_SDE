from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.execution import ExecutionRun, PatchArtifact, VerificationResult
from app.models.github import GitHubInstallation, GitHubRepository
from app.models.publishing import PublishingRun
from app.models.task import Task
from app.models.user import User
from app.models.workspace import Workspace
from app.services.publishing_service import GitPublishingService, slugify


@pytest.fixture
def mock_github_client():
    client = MagicMock()
    client.get_ref_commit.return_value = "0123456789abcdef0123456789abcdef01234567"
    client.get_ref.return_value = None
    client.create_branch.return_value = {"ref": "refs/heads/mysde/test-branch"}
    client.create_blob.return_value = "blob_sha_12345"
    client.create_tree.return_value = "tree_sha_12345"
    client.create_commit.return_value = "commit_sha_99999"
    client.update_ref.return_value = {"ref": "refs/heads/mysde/test-branch"}
    client.create_pull_request.return_value = {
        "number": 42,
        "html_url": "https://github.com/test-owner/test-repo/pull/42",
        "state": "open",
    }
    client.find_pull_request.return_value = None
    return client


@pytest.fixture
def publishing_service(mock_github_client):
    return GitPublishingService(github_client=mock_github_client)


@pytest.fixture
def publishing_test_data(db):
    user = User(
        email="publisher@example.com",
        full_name="Publisher User",
        hashed_password="argon2_hash",
        is_active=True,
    )
    workspace = Workspace(name="Publishing Workspace", slug="pub-ws", owner=user)
    db.add_all([user, workspace])
    db.commit()

    installation = GitHubInstallation(
        workspace_id=workspace.id,
        installation_id=123456,
        account_login="test-owner",
        account_type="User",
        status="active",
    )
    db.add(installation)
    db.commit()

    repo = GitHubRepository(
        workspace_id=workspace.id,
        installation_id=installation.id,
        github_repo_id=98765,
        name="test-repo",
        full_name="test-owner/test-repo",
        owner_login="test-owner",
        default_branch="main",
    )
    from app.models.project import Project
    project = Project(workspace_id=workspace.id, name="Test Project", slug="test-project")
    db.add_all([repo, project])
    db.commit()

    task = Task(
        workspace_id=workspace.id,
        project_id=project.id,
        repository_id=repo.id,
        title="Fix calculate_discount edge case",
        task_type="bug",
        priority="high",
        status="todo",
    )
    db.add(task)
    db.commit()

    from app.models.planning import ImplementationPlan, PlanningRun
    plan_run = PlanningRun(
        workspace_id=workspace.id,
        task_id=task.id,
        requested_by_user_id=user.id,
        status="completed",
        started_at=datetime.now(timezone.utc),
    )
    db.add(plan_run)
    db.commit()

    plan = ImplementationPlan(
        workspace_id=workspace.id,
        task_id=task.id,
        planning_run_id=plan_run.id,
        plan_data={"summary": "plan"},
    )
    db.add(plan)
    db.commit()

    base_sha = "0123456789abcdef0123456789abcdef01234567"
    exec_run = ExecutionRun(
        workspace_id=workspace.id,
        task_id=task.id,
        repository_id=repo.id,
        plan_id=plan.id,
        requested_by_user_id=user.id,
        base_commit_sha=base_sha,
        status="completed",
        started_at=datetime.now(timezone.utc),
    )
    db.add(exec_run)
    db.commit()

    raw_diff = """diff --git a/src/calculator.py b/src/calculator.py
index 1111111..2222222 100644
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -1,3 +1,3 @@
 def calculate_discount(price, discount):
-    return price - discount
+    return max(0, price - discount)
"""
    patch = PatchArtifact(
        execution_run_id=exec_run.id,
        patch_hash="patch_hash_aaa111",
        validation_status="valid",
        raw_diff=raw_diff,
        changed_files_count=1,
        additions_count=1,
        deletions_count=1,
        changed_files=[{"file_path": "src/calculator.py", "change_type": "modified", "additions": 1, "deletions": 1}],
    )
    verification = VerificationResult(
        execution_run_id=exec_run.id,
        verification_type="test",
        command_name="pytest",
        command_args=["pytest", "-v"],
        exit_code=0,
        status="passed",
        duration_seconds=1.2,
    )
    db.add_all([patch, verification])
    db.commit()

    return {
        "user": user,
        "workspace": workspace,
        "repo": repo,
        "task": task,
        "exec_run": exec_run,
        "patch": patch,
        "verification": verification,
    }


def test_slugify():
    assert slugify("Fix calculate_discount edge case!") == "fix-calculate-discount-edge-case"
    assert slugify("Feature: Add OAuth 2.0 Auth") == "feature-add-oauth-20-auth"


def test_precheck_requires_approval_and_passed_checks(db, publishing_service, publishing_test_data):
    data = publishing_test_data
    precheck = publishing_service.precheck_publishing(
        db=db,
        execution_run_id=data["exec_run"].id,
        workspace_id=data["workspace"].id,
        user=data["user"],
    )
    assert not precheck.can_publish
    assert not precheck.is_approved
    assert precheck.verification_passed
    assert any("approval is required" in b for b in precheck.blockers)


def test_approval_and_successful_precheck(db, publishing_service, publishing_test_data):
    data = publishing_test_data
    pub_run = publishing_service.approve_publishing(
        db=db,
        execution_run_id=data["exec_run"].id,
        patch_hash=data["patch"].patch_hash,
        workspace_id=data["workspace"].id,
        user=data["user"],
    )
    assert pub_run.status == "approved"
    assert pub_run.approved_patch_hash == data["patch"].patch_hash
    assert pub_run.approved_at is not None

    precheck = publishing_service.precheck_publishing(
        db=db,
        execution_run_id=data["exec_run"].id,
        workspace_id=data["workspace"].id,
        user=data["user"],
    )
    assert precheck.can_publish
    assert precheck.is_approved
    assert not precheck.is_patch_stale
    assert not precheck.is_base_stale
    assert len(precheck.blockers) == 0


def test_approval_invalidated_when_patch_hash_changes(db, publishing_service, publishing_test_data):
    data = publishing_test_data
    # 1. Approve initial patch
    publishing_service.approve_publishing(
        db=db,
        execution_run_id=data["exec_run"].id,
        patch_hash=data["patch"].patch_hash,
        workspace_id=data["workspace"].id,
        user=data["user"],
    )
    # 2. Add newer patch with different hash
    from datetime import timedelta
    newer_patch = PatchArtifact(
        execution_run_id=data["exec_run"].id,
        patch_hash="patch_hash_bbb222_modified",
        validation_status="valid",
        raw_diff="diff --git a/src/other.py b/src/other.py\n+new content\n",
        changed_files_count=1,
        additions_count=1,
        deletions_count=0,
        changed_files=[{"file_path": "src/other.py"}],
        created_at=datetime.now(timezone.utc) + timedelta(seconds=10),
    )
    db.add(newer_patch)
    db.commit()

    precheck = publishing_service.precheck_publishing(
        db=db,
        execution_run_id=data["exec_run"].id,
        workspace_id=data["workspace"].id,
        user=data["user"],
    )
    assert not precheck.can_publish
    assert not precheck.is_approved
    assert precheck.is_patch_stale
    assert any("Approval was invalidated" in b for b in precheck.blockers)


def test_failed_verification_blocks_approval(db, publishing_service, publishing_test_data):
    data = publishing_test_data
    # Mark verification check as failed
    data["verification"].status = "failed"
    data["verification"].exit_code = 1
    db.commit()

    with pytest.raises(HTTPException) as exc:
        publishing_service.approve_publishing(
            db=db,
            execution_run_id=data["exec_run"].id,
            patch_hash=data["patch"].patch_hash,
            workspace_id=data["workspace"].id,
            user=data["user"],
        )
    assert exc.value.status_code == 400
    assert "verification checks have not all passed" in exc.value.detail


def test_stale_base_branch_detection(db, publishing_service, publishing_test_data, mock_github_client):
    data = publishing_test_data
    # Approve first
    publishing_service.approve_publishing(
        db=db,
        execution_run_id=data["exec_run"].id,
        patch_hash=data["patch"].patch_hash,
        workspace_id=data["workspace"].id,
        user=data["user"],
    )
    # Simulate remote base branch advancing to a new commit SHA
    mock_github_client.get_ref_commit.return_value = "new_different_remote_sha_9999999999999"

    with pytest.raises(HTTPException) as exc:
        publishing_service.publish_to_github(
            db=db,
            execution_run_id=data["exec_run"].id,
            workspace_id=data["workspace"].id,
            user=data["user"],
        )
    assert exc.value.status_code == 409
    assert "new commits" in exc.value.detail


def test_successful_publishing_and_idempotent_retry(db, publishing_service, publishing_test_data, mock_github_client):
    data = publishing_test_data
    # 1. Approve
    publishing_service.approve_publishing(
        db=db,
        execution_run_id=data["exec_run"].id,
        patch_hash=data["patch"].patch_hash,
        workspace_id=data["workspace"].id,
        user=data["user"],
    )
    # 2. Publish
    result = publishing_service.publish_to_github(
        db=db,
        execution_run_id=data["exec_run"].id,
        workspace_id=data["workspace"].id,
        user=data["user"],
    )
    assert result.status == "completed"
    assert result.pr_number == 42
    assert result.pr_url == "https://github.com/test-owner/test-repo/pull/42"
    assert result.head_commit_sha == "commit_sha_99999"
    assert data["task"].status == "in_review"

    # Verify calls on mock
    mock_github_client.create_branch.assert_called_once()
    mock_github_client.create_blob.assert_called_once()
    mock_github_client.create_tree.assert_called_once()
    mock_github_client.create_commit.assert_called_once()
    mock_github_client.update_ref.assert_called_once()
    mock_github_client.create_pull_request.assert_called_once()

    # 3. Idempotent call returns existing completed result without calling GitHub again
    call_count = mock_github_client.create_pull_request.call_count
    retry_result = publishing_service.publish_to_github(
        db=db,
        execution_run_id=data["exec_run"].id,
        workspace_id=data["workspace"].id,
        user=data["user"],
    )
    assert retry_result.id == result.id
    assert retry_result.pr_number == 42
    assert mock_github_client.create_pull_request.call_count == call_count


def test_unsafe_protected_file_rejected_before_git_push(db, publishing_service, publishing_test_data):
    data = publishing_test_data
    # Create patch modifying .env file
    unsafe_diff = """diff --git a/.env b/.env
index 0000000..1111111 100644
--- a/.env
+++ b/.env
@@ -1 +1 @@
-OLD_SECRET=123
+NEW_SECRET=456
"""
    data["patch"].raw_diff = unsafe_diff
    data["patch"].changed_files = [{"file_path": ".env"}]
    data["patch"].patch_hash = "unsafe_patch_hash_999"
    db.commit()

    with pytest.raises(HTTPException) as exc1:
        publishing_service.approve_publishing(
            db=db,
            execution_run_id=data["exec_run"].id,
            patch_hash="unsafe_patch_hash_999",
            workspace_id=data["workspace"].id,
            user=data["user"],
        )
    assert exc1.value.status_code == 400
    assert "Security violation" in exc1.value.detail

    # Or if approved directly in DB, also rejected during publish:
    pub_run = PublishingRun(
        workspace_id=data["workspace"].id,
        task_id=data["task"].id,
        execution_run_id=data["exec_run"].id,
        repository_id=data["repo"].id,
        patch_artifact_id=data["patch"].id,
        requested_by_user_id=data["user"].id,
        approved_by_user_id=data["user"].id,
        approved_patch_hash="unsafe_patch_hash_999",
        approved_at=datetime.now(timezone.utc),
        status="approved",
        base_branch="main",
        base_commit_sha=data["exec_run"].base_commit_sha,
        head_branch="mysde/test-unsafe",
        idempotency_key="idemp_key_unsafe",
    )
    db.add(pub_run)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        publishing_service.publish_to_github(
            db=db,
            execution_run_id=data["exec_run"].id,
            workspace_id=data["workspace"].id,
            user=data["user"],
        )
    assert exc.value.status_code == 400
    assert "Security violation" in exc.value.detail
