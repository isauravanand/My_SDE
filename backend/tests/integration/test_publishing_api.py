import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.models.execution import ExecutionRun, PatchArtifact, VerificationResult
from app.models.github import GitHubInstallation, GitHubRepository
from app.models.planning import ImplementationPlan, PlanningRun


def register_user(client: TestClient, email: str, name: str = "Test User"):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    user = res.json()
    cookies = {
        SESSION_COOKIE_NAME: res.cookies[SESSION_COOKIE_NAME],
        CSRF_COOKIE_NAME: res.cookies[CSRF_COOKIE_NAME],
    }
    headers = {CSRF_HEADER_NAME: res.cookies[CSRF_COOKIE_NAME]}
    return user, cookies, headers


@pytest.fixture
def api_test_setup(client: TestClient, db: Session):
    user, cookies, headers = register_user(client, f"pubuser_{uuid.uuid4().hex[:8]}@example.com", "Publisher")
    ws_res = client.get("/api/v1/workspaces", cookies=cookies)
    workspace = ws_res.json()[0]
    workspace_id = workspace["id"]

    # Create project and task
    proj_res = client.post(
        f"/api/v1/projects?workspace_id={workspace_id}",
        json={"name": "Publishing Project", "description": "Project for publishing"},
        cookies=cookies,
        headers=headers,
    )
    project_id = proj_res.json()["id"]

    # Add GitHub installation and repository
    installation = GitHubInstallation(
        workspace_id=uuid.UUID(workspace_id),
        installation_id=555666,
        account_login="acme-corp",
        account_type="Organization",
        status="active",
    )
    db.add(installation)
    db.commit()

    repo = GitHubRepository(
        workspace_id=uuid.UUID(workspace_id),
        installation_id=installation.id,
        github_repo_id=1234567,
        name="api-service",
        full_name="acme-corp/api-service",
        owner_login="acme-corp",
        default_branch="main",
    )
    db.add(repo)
    db.commit()

    task_res = client.post(
        f"/api/v1/projects/{project_id}/tasks?workspace_id={workspace_id}",
        json={
            "title": "Fix calculate_tax roundoff bug",
            "description": "Ensure floating point precision matches accounting rules.",
            "task_type": "bug",
            "priority": "high",
            "repository_id": str(repo.id),
        },
        cookies=cookies,
        headers=headers,
    )
    task_id = task_res.json()["id"]

    # Create plan run and plan
    plan_run = PlanningRun(
        workspace_id=uuid.UUID(workspace_id),
        task_id=uuid.UUID(task_id),
        requested_by_user_id=uuid.UUID(user["id"]),
        status="completed",
        started_at=datetime.now(timezone.utc),
    )
    db.add(plan_run)
    db.commit()

    plan = ImplementationPlan(
        workspace_id=uuid.UUID(workspace_id),
        task_id=uuid.UUID(task_id),
        planning_run_id=plan_run.id,
        plan_data={"summary": "Fix accounting roundoff"},
    )
    db.add(plan)
    db.commit()

    base_sha = "1111222233334444555566667777888899990000"
    exec_run = ExecutionRun(
        workspace_id=uuid.UUID(workspace_id),
        task_id=uuid.UUID(task_id),
        repository_id=repo.id,
        plan_id=plan.id,
        requested_by_user_id=uuid.UUID(user["id"]),
        base_commit_sha=base_sha,
        status="completed",
        started_at=datetime.now(timezone.utc),
    )
    db.add(exec_run)
    db.commit()

    raw_diff = """diff --git a/src/tax.py b/src/tax.py
index 1000000..2000000 100644
--- a/src/tax.py
+++ b/src/tax.py
@@ -1,3 +1,3 @@
 def calculate_tax(amount):
-    return round(amount * 0.2, 2)
+    return round(amount * 0.20, 2)
"""
    patch_artifact = PatchArtifact(
        execution_run_id=exec_run.id,
        patch_hash="patch_hash_tax_123",
        validation_status="valid",
        raw_diff=raw_diff,
        changed_files_count=1,
        additions_count=1,
        deletions_count=1,
        changed_files=[{"file_path": "src/tax.py"}],
    )
    verification = VerificationResult(
        execution_run_id=exec_run.id,
        verification_type="test",
        command_name="pytest",
        command_args=["pytest", "tests/test_tax.py"],
        exit_code=0,
        status="passed",
        duration_seconds=0.8,
        stdout_excerpt="1 test passed",
        stderr_excerpt="",
    )
    db.add_all([patch_artifact, verification])
    db.commit()

    return {
        "user": user,
        "cookies": cookies,
        "headers": headers,
        "workspace_id": workspace_id,
        "repo": repo,
        "exec_run": exec_run,
        "patch": patch_artifact,
        "verification": verification,
        "base_sha": base_sha,
    }


def test_publishing_api_precheck_and_approval_flow(client: TestClient, db: Session, api_test_setup):
    setup = api_test_setup
    cookies = setup["cookies"]
    headers = setup["headers"]
    ws_id = setup["workspace_id"]
    exec_id = str(setup["exec_run"].id)

    with patch("app.services.publishing_service.publishing_service.github_client") as mock_gh:
        mock_gh.get_ref_commit.return_value = setup["base_sha"]

        # 1. Precheck before approval
        pre_res = client.get(
            f"/api/v1/executions/{exec_id}/publish/precheck?workspace_id={ws_id}",
            cookies=cookies,
        )
        assert pre_res.status_code == 200
        data = pre_res.json()
        assert not data["is_approved"]
        assert not data["can_publish"]
        assert any("approval is required" in b for b in data["blockers"])

        # 2. Approve publishing with wrong hash -> 400
        bad_app_res = client.post(
            f"/api/v1/executions/{exec_id}/publish/approve?workspace_id={ws_id}",
            json={"patch_hash": "wrong_hash"},
            cookies=cookies,
            headers=headers,
        )
        assert bad_app_res.status_code == 400
        assert "does not match current active patch" in bad_app_res.json()["error"]["message"]

        # 3. Approve publishing with correct hash -> 200
        app_res = client.post(
            f"/api/v1/executions/{exec_id}/publish/approve?workspace_id={ws_id}",
            json={"patch_hash": setup["patch"].patch_hash},
            cookies=cookies,
            headers=headers,
        )
        assert app_res.status_code == 200
        app_data = app_res.json()
        assert app_data["status"] == "approved"
        assert app_data["approved_patch_hash"] == setup["patch"].patch_hash
        assert app_data["head_branch"].startswith("mysde/task-")

        # 4. Precheck after approval -> can_publish == True
        pre_res2 = client.get(
            f"/api/v1/executions/{exec_id}/publish/precheck?workspace_id={ws_id}",
            cookies=cookies,
        )
        assert pre_res2.status_code == 200
        data2 = pre_res2.json()
        assert data2["is_approved"]
        assert data2["can_publish"]
        assert len(data2["blockers"]) == 0


def test_publishing_api_publish_success_and_cross_tenant_denial(client: TestClient, db: Session, api_test_setup):
    from app.main import app

    setup = api_test_setup
    cookies = setup["cookies"]
    headers = setup["headers"]
    ws_id = setup["workspace_id"]
    exec_id = str(setup["exec_run"].id)

    with patch("app.services.publishing_service.publishing_service.github_client") as mock_gh:
        mock_gh.get_ref_commit.return_value = setup["base_sha"]
        mock_gh.get_ref.return_value = None  # branch does not exist yet
        mock_gh.create_branch.return_value = {"ref": "refs/heads/mysde/task-branch"}
        mock_gh.create_blob.return_value = "blob_sha_123"
        mock_gh.create_tree.return_value = "tree_sha_123"
        mock_gh.create_commit.return_value = "commit_sha_9999"
        mock_gh.update_ref.return_value = {"ref": "refs/heads/mysde/task-branch"}
        mock_gh.create_pull_request.return_value = {
            "number": 88,
            "html_url": "https://github.com/acme-corp/api-service/pull/88",
            "state": "open",
        }

        # Approve first
        client.post(
            f"/api/v1/executions/{exec_id}/publish/approve?workspace_id={ws_id}",
            json={"patch_hash": setup["patch"].patch_hash},
            cookies=cookies,
            headers=headers,
        )

        # Cross-tenant access test: register another user with isolated client and attempt to publish
        other_client = TestClient(app)
        other_user, other_cookies, other_headers = register_user(
            other_client, f"other_{uuid.uuid4().hex[:8]}@example.com", "Attacker"
        )
        other_ws = other_client.get("/api/v1/workspaces", cookies=other_cookies).json()[0]["id"]

        denied_res = other_client.post(
            f"/api/v1/executions/{exec_id}/publish?workspace_id={other_ws}",
            json={},
            cookies=other_cookies,
            headers=other_headers,
        )
        assert denied_res.status_code == 404

        # Authorized user publishes to GitHub
        pub_res = client.post(
            f"/api/v1/executions/{exec_id}/publish?workspace_id={ws_id}",
            json={"custom_pr_title": "Fix calculate_tax accounting precision"},
            cookies=cookies,
            headers=headers,
        )
        assert pub_res.status_code == 201
        pub_data = pub_res.json()
        assert pub_data["status"] == "completed"
        assert pub_data["pr_number"] == 88
        assert pub_data["pr_url"] == "https://github.com/acme-corp/api-service/pull/88"
        assert pub_data["head_commit_sha"] == "commit_sha_9999"

        # Idempotent retry: calling again returns the same PR without error
        retry_res = client.post(
            f"/api/v1/executions/{exec_id}/publish?workspace_id={ws_id}",
            json={},
            cookies=cookies,
            headers=headers,
        )
        assert retry_res.status_code in (200, 201)
        assert retry_res.json()["pr_number"] == 88

        # Check GET publishing status endpoint
        get_res = client.get(
            f"/api/v1/executions/{exec_id}/publish?workspace_id={ws_id}",
            cookies=cookies,
        )
        assert get_res.status_code == 200
        assert get_res.json()["pr_number"] == 88
