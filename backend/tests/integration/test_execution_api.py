import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.execution.sandbox.mock import MockSandbox
from app.models.execution import ExecutionRun, PatchArtifact
from app.models.planning import ImplementationPlan, PlanningRun
from app.models.project import Project
from app.models.task import Task
from app.models.workspace import Workspace
from app.services.execution_service import ExecutionService


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


def create_task_with_plan(client: TestClient, db: Session, user_email: str = "exec@example.com"):
    user, cookies, headers = register_user(client, user_email, "Execution Engineer")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # Create project
    proj = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Execution Project"},
        headers=headers,
    ).json()

    # Create task
    task = client.post(
        f"/api/v1/projects/{proj['id']}/tasks?workspace_id={ws_id}",
        json={
            "title": "Add caching layer to user service",
            "description": "Implement Redis cache with TTL and serialization.",
            "task_type": "feature",
            "priority": "high",
        },
        headers=headers,
    ).json()

    # Create validated implementation plan in DB
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
        plan_data={
            "schema_version": "mysde.plan.v1",
            "task_id": task["id"],
            "base_commit_sha": "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4",
            "summary": "Plan to add caching layer to user service",
            "implementation_steps": [
                {
                    "step_id": "step-1",
                    "order": 1,
                    "title": "Create cache manager module",
                    "description": "Add CacheManager class with get/set",
                    "relevant_files": ["src/cache.py"],
                    "change_type": "create",
                    "dependencies": [],
                    "verification_instructions": "python -m py_compile src/cache.py",
                    "evidence_refs": [],
                    "confidence": "high",
                    "location_status": "proposed_new",
                    "rationale": "Modular caching interface",
                }
            ],
            "evidence": [],
        },
    )
    db.add(plan)
    db.commit()

    return user, headers, ws_id, task["id"], plan.id


def test_complete_execution_lifecycle_and_verification(client: TestClient, db: Session):
    """End-to-end test of Phase 7 execution run: prepare -> approve -> run checks -> evidence."""
    user, headers, ws_id, task_id, plan_id = create_task_with_plan(client, db)

    # 1. Start execution run
    start_res = client.post(
        f"/api/v1/tasks/{task_id}/execution",
        json={"plan_id": str(plan_id)},
        headers=headers,
    )
    assert start_res.status_code == 201
    run_data = start_res.json()
    run_id = run_data["id"]
    assert run_data["status"] == "awaiting_patch_approval"
    assert len(run_data["patches"]) == 1

    # 2. Inspect patch proposal
    patch_res = client.get(f"/api/v1/execution/runs/{run_id}/patch")
    assert patch_res.status_code == 200
    patch_data = patch_res.json()
    assert patch_data["validation_status"] == "valid"
    assert "diff --git" in patch_data["raw_diff"]
    assert patch_data["is_approved"] is False

    # 3. Approve patch and trigger execution checks
    approve_res = client.post(
        f"/api/v1/execution/runs/{run_id}/approve",
        json={"run_checks": True, "verification_commands": ["syntax_check"]},
        headers=headers,
    )
    assert approve_res.status_code == 200
    completed_run = approve_res.json()
    assert completed_run["status"] == "completed"
    assert completed_run["cleanup_status"] == "cleaned"
    assert completed_run["completed_at"] is not None

    # Verify check results
    assert len(completed_run["verification_results"]) == 1
    check = completed_run["verification_results"][0]
    assert check["command_name"] == "syntax_check"
    assert check["status"] == "passed"
    assert check["exit_code"] == 0

    # 4. List task executions
    list_res = client.get(f"/api/v1/tasks/{task_id}/executions")
    assert list_res.status_code == 200
    runs = list_res.json()
    assert len(runs) >= 1
    assert runs[0]["id"] == run_id


def test_reject_patch_proposal(client: TestClient, db: Session):
    """Test rejecting a proposed patch terminates the run cleanly."""
    user, headers, ws_id, task_id, plan_id = create_task_with_plan(client, db, "rejector@example.com")

    # Start run
    start_res = client.post(
        f"/api/v1/tasks/{task_id}/execution",
        json={"plan_id": str(plan_id)},
        headers=headers,
    )
    run_id = start_res.json()["id"]

    # Reject patch
    reject_res = client.post(
        f"/api/v1/execution/runs/{run_id}/reject",
        json={"reason": "Incorrect files altered."},
        headers=headers,
    )
    assert reject_res.status_code == 200
    rejected_run = reject_res.json()
    assert rejected_run["status"] == "cancelled"
    assert "rejected" in rejected_run["safe_error_summary"].lower()


def test_cancel_execution_run(client: TestClient, db: Session):
    """Test manual cancellation of an execution run."""
    user, headers, ws_id, task_id, plan_id = create_task_with_plan(client, db, "canceller2@example.com")

    start_res = client.post(
        f"/api/v1/tasks/{task_id}/execution",
        json={},
        headers=headers,
    )
    run_id = start_res.json()["id"]

    cancel_res = client.post(
        f"/api/v1/execution/runs/{run_id}/cancel",
        headers=headers,
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"


def test_duplicate_run_concurrency_control(client: TestClient, db: Session):
    """Verifies that an active run blocks starting duplicate runs for the same task."""
    user, headers, ws_id, task_id, plan_id = create_task_with_plan(client, db, "concur@example.com")

    # Start run 1 (remains in awaiting_patch_approval)
    res1 = client.post(f"/api/v1/tasks/{task_id}/execution", json={}, headers=headers)
    assert res1.status_code == 201

    # Attempt to start run 2 for same task -> 400 Bad Request
    res2 = client.post(f"/api/v1/tasks/{task_id}/execution", json={}, headers=headers)
    assert res2.status_code == 400
    err_body = res2.json()
    err_msg = err_body.get("error", {}).get("message") or err_body.get("detail", "")
    assert "already in progress" in err_msg


def test_execution_without_plan_fails(client: TestClient, db: Session):
    """Attempting execution on a task with no implementation plan returns 400."""
    _, cookies, headers = register_user(client, "noplan@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    proj = client.post(f"/api/v1/projects?workspace_id={ws_id}", json={"name": "NoPlanProj"}, headers=headers).json()
    task = client.post(
        f"/api/v1/projects/{proj['id']}/tasks?workspace_id={ws_id}",
        json={"title": "Task without plan"},
        headers=headers,
    ).json()

    res = client.post(f"/api/v1/tasks/{task['id']}/execution", json={}, headers=headers)
    assert res.status_code == 400
    err_body = res.json()
    err_msg = err_body.get("error", {}).get("message") or err_body.get("detail", "")
    assert "No implementation plan found" in err_msg


def test_cross_workspace_execution_isolation(client: TestClient, db: Session):
    """Verify Workspace B user cannot access or approve Workspace A's execution runs."""
    # User A in Workspace A
    _, headers_a, ws_a, task_a, plan_a = create_task_with_plan(client, db, "user_a@example.com")
    run_a = client.post(f"/api/v1/tasks/{task_a}/execution", json={}, headers=headers_a).json()

    # User B in Workspace B
    _, cookies_b, headers_b = register_user(client, "user_b@example.com")
    client.cookies.clear()
    client.cookies.update(cookies_b)

    # User B tries to view User A's run -> 403
    res_get = client.get(f"/api/v1/execution/runs/{run_a['id']}")
    assert res_get.status_code in [403, 404]

    # User B tries to view patch -> 403
    res_patch = client.get(f"/api/v1/execution/runs/{run_a['id']}/patch")
    assert res_patch.status_code in [403, 404]

    # User B tries to approve run -> 403
    res_approve = client.post(f"/api/v1/execution/runs/{run_a['id']}/approve", json={}, headers=headers_b)
    assert res_approve.status_code in [403, 404]


def test_unauthenticated_request_rejected(client: TestClient):
    """Unauthenticated requests are rejected with 401 Unauthorized."""
    client.cookies.clear()
    fake_id = uuid.uuid4()
    res = client.get(f"/api/v1/execution/runs/{fake_id}")
    assert res.status_code == 401


def test_verification_exit_code_and_failure_recording(db: Session):
    """Test service records failed verification checks with honest exit codes."""
    # Create workspace, project, task, and plan
    user_id = uuid.uuid4()
    ws = Workspace(name="Test Workspace", slug=f"ws-{uuid.uuid4().hex[:8]}", owner_id=user_id)
    db.add(ws)
    db.flush()

    proj = Project(workspace_id=ws.id, name="Test Project", slug=f"proj-{uuid.uuid4().hex[:8]}", created_by=user_id)
    db.add(proj)
    db.flush()

    task = Task(
        workspace_id=ws.id,
        project_id=proj.id,
        title="Check failure recording",
        task_type="feature",
        created_by=user_id,
    )
    db.add(task)
    db.flush()

    plan = ImplementationPlan(
        planning_run_id=uuid.uuid4(),
        workspace_id=ws.id,
        task_id=task.id,
        schema_version="mysde.plan.v1",
        plan_data={"summary": "Plan", "implementation_steps": []},
    )
    db.add(plan)
    db.commit()

    service = ExecutionService(db)
    # Mock workspace check
    service._verify_workspace_access = lambda w, u: None

    run = service.start_execution_run(task.id, user_id, plan.id)

    # Inject mock sandbox simulating check failure on 'syntax_check'
    failing_sandbox = MockSandbox(simulate_failure_command="syntax_check")
    result_run = service.approve_and_execute(
        run_id=run.id,
        user_id=user_id,
        run_checks=True,
        verification_commands=["syntax_check"],
        sandbox_override=failing_sandbox,
    )

    assert result_run.status == "failed"
    assert len(result_run.verification_results) == 1
    v = result_run.verification_results[0]
    assert v.status == "failed"
    assert v.exit_code == 1
    assert "Test run failed" in v.stdout_excerpt


def test_database_foreign_key_cascade(client: TestClient, db: Session):
    """Deleting a task cascades and removes all associated execution runs, patches, and results."""
    user, headers, ws_id, task_id, plan_id = create_task_with_plan(client, db, "cascade@example.com")
    run_res = client.post(f"/api/v1/tasks/{task_id}/execution", json={}, headers=headers)
    run_id = run_res.json()["id"]

    # Delete task
    db_task = db.execute(select(Task).where(Task.id == uuid.UUID(task_id))).scalar_one()
    _ = db_task.execution_runs  # Load relationship so ORM cascade deletes child records
    db.delete(db_task)
    db.commit()

    # Verify execution run, patch, and results are deleted
    run_db = db.execute(select(ExecutionRun).where(ExecutionRun.id == uuid.UUID(run_id))).scalar_one_or_none()
    assert run_db is None

    patch_db = db.execute(select(PatchArtifact).where(PatchArtifact.execution_run_id == uuid.UUID(run_id))).scalar_one_or_none()
    assert patch_db is None
