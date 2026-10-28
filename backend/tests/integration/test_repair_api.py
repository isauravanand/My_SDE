import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.models.execution import ExecutionRun, PatchArtifact, VerificationResult
from app.models.planning import ImplementationPlan, PlanningRun
from app.models.repair import RepairRun


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


def create_failed_execution(client: TestClient, db: Session, user_email: str = "repair_user@example.com"):
    user, cookies, headers = register_user(client, user_email, "Repair Engineer")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # Create project and task
    proj = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Repair Project"},
        headers=headers,
    ).json()

    task = client.post(
        f"/api/v1/projects/{proj['id']}/tasks?workspace_id={ws_id}",
        json={
            "title": "Fix cache invalidation bug",
            "description": "Fix bug where cache returns stale data.",
            "task_type": "bug",
            "priority": "high",
        },
        headers=headers,
    ).json()

    # Create plan
    plan_run = PlanningRun(
        workspace_id=uuid.UUID(ws_id),
        task_id=uuid.UUID(task["id"]),
        requested_by_user_id=uuid.UUID(user["id"]),
        status="completed",
        base_commit_sha="a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(plan_run)
    db.flush()

    plan = ImplementationPlan(
        planning_run_id=plan_run.id,
        workspace_id=uuid.UUID(ws_id),
        task_id=uuid.UUID(task["id"]),
        schema_version="mysde.plan.v1",
        plan_data={"summary": "Fix cache logic", "task_id": task["id"]},
    )
    db.add(plan)
    db.flush()

    # Create ExecutionRun in failed status
    exec_run = ExecutionRun(
        workspace_id=uuid.UUID(ws_id),
        task_id=uuid.UUID(task["id"]),
        plan_id=plan.id,
        requested_by_user_id=uuid.UUID(user["id"]),
        base_commit_sha="a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4",
        status="failed",
        safe_error_summary="Verification checks failed.",
        cleanup_status="cleaned",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(exec_run)
    db.flush()

    # Create PatchArtifact
    patch = PatchArtifact(
        execution_run_id=exec_run.id,
        patch_hash="abc1234567890123456789012345678901234567890123456789012345678901",
        validation_status="applied",
        raw_diff="diff --git a/src/main.py b/src/main.py\n--- a/src/main.py\n+++ b/src/main.py\n@@ -1,3 +1,3 @@\n-def run():\n+def run():\n     return False\n",
        changed_files_count=1,
        is_approved=True,
    )
    db.add(patch)

    # Add failing verification result
    v_res = VerificationResult(
        execution_run_id=exec_run.id,
        verification_type="test",
        command_name="pytest",
        command_args=["pytest"],
        exit_code=1,
        status="failed",
        duration_seconds=2.1,
        stdout_excerpt="FAILED tests/test_main.py::test_run - AssertionError: expected True but got False",
        stderr_excerpt="AssertionError: expected True but got False",
    )
    db.add(v_res)
    db.commit()

    return user, cookies, headers, ws_id, exec_run


def test_unauthorized_repair_request(client: TestClient):
    client.cookies.clear()
    res = client.post(f"/api/v1/executions/{uuid.uuid4()}/repair")
    assert res.status_code in {401, 403}


def test_cross_workspace_repair_access_denied(client: TestClient, db: Session):
    # User 1 creates execution run
    _, _, _, _, exec_run = create_failed_execution(client, db, "user1_repair@example.com")

    # User 2 logs in
    _, user2_cookies, user2_headers = register_user(client, "user2_repair@example.com", "Attacker User")
    client.cookies.clear()
    client.cookies.update(user2_cookies)

    # User 2 attempts to trigger repair on User 1's execution run
    res = client.post(
        f"/api/v1/executions/{exec_run.id}/repair",
        headers=user2_headers,
    )
    assert res.status_code == 403
    assert "Access denied" in res.json().get("error", {}).get("message", "")


def test_repair_on_succeeded_execution_rejected(client: TestClient, db: Session):
    _, cookies, headers, _, exec_run = create_failed_execution(client, db, "user_success@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    # Mark all checks and run as completed/passed
    exec_run.status = "completed"
    for v in exec_run.verification_results:
        v.status = "passed"
        v.exit_code = 0
    db.commit()

    res = client.post(
        f"/api/v1/executions/{exec_run.id}/repair",
        headers=headers,
    )
    assert res.status_code == 400
    assert "Repair is not required" in res.json().get("error", {}).get("message", "")


def test_successful_assertion_repair_workflow(client: TestClient, db: Session):
    _, cookies, headers, _, exec_run = create_failed_execution(client, db, "repair_pass@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    res = client.post(
        f"/api/v1/executions/{exec_run.id}/repair",
        json={"verification_commands": ["pytest"]},
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "completed"
    assert data["final_outcome"] == "passed"
    assert data["consumed_attempts"] >= 1
    assert len(data["attempts"]) >= 1

    attempt = data["attempts"][0]
    assert attempt["failure_classification"]["category"] == "test_assertion_failure"
    assert attempt["proposal_status"] == "applied"
    assert attempt["root_cause_hypothesis"] is not None

    # Verify repair run query
    run_res = client.get(f"/api/v1/repairs/{data['id']}")
    assert run_res.status_code == 200
    assert run_res.json()["id"] == data["id"]

    # Verify latest repair query for execution run
    latest_res = client.get(f"/api/v1/executions/{exec_run.id}/repair")
    assert latest_res.status_code == 200
    assert latest_res.json()["id"] == data["id"]


def test_non_repairable_failure_stops_without_looping(client: TestClient, db: Session):
    _, cookies, headers, _, exec_run = create_failed_execution(client, db, "timeout_user@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    # Change verification result to timeout
    for v in exec_run.verification_results:
        v.status = "timed_out"
        v.exit_code = 124
        v.stderr_excerpt = "Sandbox execution exceeded timeout of 60 seconds"
    db.commit()

    res = client.post(
        f"/api/v1/executions/{exec_run.id}/repair",
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "non_repairable"
    assert data["final_outcome"] == "non_repairable"
    assert "timed out" in data["safe_error_summary"].lower() or "timeout" in data["safe_error_summary"].lower()


def test_cancel_repair_run(client: TestClient, db: Session):
    _, cookies, headers, ws_id, exec_run = create_failed_execution(client, db, "cancel_user@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    # Create a RepairRun in analyzing status
    repair_run = RepairRun(
        workspace_id=uuid.UUID(ws_id),
        execution_run_id=exec_run.id,
        task_id=exec_run.task_id,
        requested_by_user_id=exec_run.requested_by_user_id,
        status="analyzing",
        max_attempts=3,
        consumed_attempts=1,
        max_model_calls=6,
        consumed_model_calls=1,
        started_at=datetime.now(timezone.utc),
        deadline_at=datetime.now(timezone.utc),
    )
    db.add(repair_run)
    db.commit()

    res = client.post(
        f"/api/v1/repairs/{repair_run.id}/cancel",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    assert res.json()["final_outcome"] == "cancelled"


def test_repair_summary_endpoint(client: TestClient, db: Session):
    _, cookies, headers, _, exec_run = create_failed_execution(client, db, "summary_user@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    res = client.post(
        f"/api/v1/executions/{exec_run.id}/repair",
        headers=headers,
    )
    repair_id = res.json()["id"]

    sum_res = client.get(f"/api/v1/repairs/{repair_id}/summary")
    assert sum_res.status_code == 200
    summary = sum_res.json()
    assert summary["repair_run_id"] == repair_id
    assert summary["final_outcome"] == "passed"
    assert summary["total_attempts"] >= 1
