import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.models.execution import ExecutionRun
from app.models.planning import ImplementationPlan, PlanningRun
from app.models.task import Task


def register_user_payload(client: TestClient, email: str, name: str = "Test User"):
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


def get_default_workspace_id(client: TestClient) -> str:
    res = client.get("/api/v1/workspaces")
    assert res.status_code == 200
    workspaces = res.json()
    return workspaces[0]["id"]


def test_request_id_creation_and_propagation(client: TestClient):
    """Ensure X-Request-ID is generated if missing and preserved if supplied."""
    # 1. Custom request ID provided
    res1 = client.get("/health", headers={"X-Request-ID": "test-custom-trace-999"})
    assert res1.status_code == 200
    assert res1.headers.get("X-Request-ID") == "test-custom-trace-999"

    # 2. No request ID provided -> generated automatically
    res2 = client.get("/health")
    assert res2.status_code == 200
    generated_id = res2.headers.get("X-Request-ID")
    assert generated_id is not None
    # Validate UUID4 format
    parsed = uuid.UUID(generated_id, version=4)
    assert parsed is not None


def test_unauthenticated_observability_endpoints(client: TestClient):
    """Ensure observability endpoints require authenticated session."""
    client.cookies.clear()
    dummy_id = str(uuid.uuid4())

    r1 = client.get(f"/api/v1/observability/metrics?workspace_id={dummy_id}")
    assert r1.status_code == 401

    r2 = client.get(f"/api/v1/observability/runs?workspace_id={dummy_id}")
    assert r2.status_code == 401

    r3 = client.get(f"/api/v1/observability/runs/{dummy_id}/trace?workspace_id={dummy_id}")
    assert r3.status_code == 401

    r4 = client.post(f"/api/v1/observability/recover-stale?workspace_id={dummy_id}")
    assert r4.status_code in (401, 403)


def test_workspace_metrics_endpoint(client: TestClient):
    """Validate calculation and return of aggregate workspace observability metrics."""
    _, cookies, _ = register_user_payload(client, f"obs_metrics_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    ws_id = get_default_workspace_id(client)

    res = client.get(f"/api/v1/observability/metrics?workspace_id={ws_id}&time_window_days=30")
    assert res.status_code == 200
    data = res.json()
    assert data["workspace_id"] == ws_id
    assert data["time_window_days"] == 30
    assert "total_runs" in data
    assert "successful_runs" in data
    assert "failed_runs" in data
    assert "average_durations_seconds" in data


def test_tenant_isolation_on_observability(client: TestClient):
    """Ensure users cannot inspect metrics, runs, or recover runs from another tenant's workspace."""
    # User A
    _, cookies_a, _ = register_user_payload(client, f"tenant_a_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies_a)
    ws_a_id = get_default_workspace_id(client)

    # User B
    _, cookies_b, headers_b = register_user_payload(client, f"tenant_b_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies_b)

    # User B tries to access User A's workspace observability (returns 403 or 404 anti-enumeration)
    res1 = client.get(f"/api/v1/observability/metrics?workspace_id={ws_a_id}")
    assert res1.status_code in (403, 404)

    res2 = client.get(f"/api/v1/observability/runs?workspace_id={ws_a_id}")
    assert res2.status_code in (403, 404)

    res3 = client.post(
        f"/api/v1/observability/recover-stale?workspace_id={ws_a_id}",
        headers=headers_b,
    )
    assert res3.status_code in (403, 404)


def test_recover_stale_runs_api(client: TestClient, db: Session):
    """Validate recovery endpoint transitions stale in-flight runs to timed_out state."""
    user, cookies, headers = register_user_payload(client, f"recover_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = get_default_workspace_id(client)

    # Create Project first
    proj_res = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Observability Test Project"},
        headers=headers,
    )
    assert proj_res.status_code == 201
    project_id = uuid.UUID(proj_res.json()["id"])

    # Create Task
    task = Task(
        workspace_id=uuid.UUID(ws_id),
        project_id=project_id,
        title="Stale Task",
        description="Task to test timeout recovery",
        created_by=uuid.UUID(user["id"]),
        status="in_progress",
    )
    db.add(task)
    db.flush()

    # Create PlanningRun and Plan
    plan_run = PlanningRun(
        workspace_id=uuid.UUID(ws_id),
        task_id=task.id,
        requested_by_user_id=uuid.UUID(user["id"]),
        status="completed",
        base_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(plan_run)
    db.flush()

    plan = ImplementationPlan(
        planning_run_id=plan_run.id,
        workspace_id=uuid.UUID(ws_id),
        task_id=task.id,
        schema_version="mysde.plan.v1",
        plan_data={"summary": "Recovery test plan"},
    )
    db.add(plan)
    db.flush()

    # Create stale ExecutionRun started 45 minutes ago
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=45)
    stale_run = ExecutionRun(
        workspace_id=uuid.UUID(ws_id),
        task_id=task.id,
        plan_id=plan.id,
        requested_by_user_id=uuid.UUID(user["id"]),
        base_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        status="preparing",
        started_at=stale_time,
    )
    db.add(stale_run)
    db.commit()

    # Call recovery endpoint
    res = client.post(
        f"/api/v1/observability/recover-stale?workspace_id={ws_id}&timeout_minutes=15",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["recovered_executions"] >= 1

    # Verify DB state
    db.refresh(stale_run)
    assert stale_run.status == "timed_out"
    assert stale_run.completed_at is not None
    assert "timed out or was interrupted" in stale_run.safe_error_summary

    # Verify run trace endpoint inspection
    trace_res = client.get(
        f"/api/v1/observability/runs/{stale_run.id}/trace?workspace_id={ws_id}"
    )
    assert trace_res.status_code == 200
    trace_data = trace_res.json()
    assert trace_data["execution_run_id"] == str(stale_run.id)
    assert trace_data["status"] == "timed_out"
    assert "timed out or was interrupted" in trace_data["safe_error_summary"]
    assert len(trace_data["timeline"]) >= 1


def test_rate_limiting_verify_email(client: TestClient):
    """Ensure sensitive endpoint rate limiting stops abuse."""
    client.cookies.clear()
    # The verify-email endpoint is rate limited to 10 requests per minute
    statuses = []
    for _ in range(12):
        r = client.post("/api/v1/auth/verify-email", json={"token": "invalid_test_token"})
        statuses.append(r.status_code)

    assert 429 in statuses
