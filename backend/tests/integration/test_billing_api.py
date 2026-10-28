import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.mock_provider import MockBillingProvider
from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.models.billing import Subscription, UsageLedgerEntry
from app.models.planning import ImplementationPlan, PlanningRun
from app.models.task import Task


def register_user_payload(client: TestClient, email: str, name: str = "Billing Tester"):
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


def test_list_plans_returns_seeded_tiers(client: TestClient):
    """Ensure public plans endpoint lists available subscription tiers."""
    res = client.get("/api/v1/billing/plans")
    assert res.status_code == 200
    plans = res.json()
    assert len(plans) >= 3
    plan_codes = [p["plan_code"] for p in plans]
    assert "free" in plan_codes
    assert "pro" in plan_codes
    assert "team" in plan_codes


def test_get_workspace_subscription(client: TestClient):
    """Ensure a new workspace defaults to the Free plan with appropriate quota meters."""
    _, cookies, _ = register_user_payload(client, f"sub_user_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = get_default_workspace_id(client)

    res = client.get(f"/api/v1/billing/subscription?workspace_id={ws_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["workspace_id"] == ws_id
    assert data["status"] == "active"
    assert data["plan"]["plan_code"] == "free"
    assert data["usage"]["agent_runs_limit"] == 15
    assert data["usage"]["repair_runs_limit"] == 5
    assert data["is_in_good_standing"] is True


def test_tenant_isolation_on_billing(client: TestClient):
    """Ensure users cannot inspect or mutate subscriptions of workspaces they do not belong to."""
    # User A
    _, cookies_a, _ = register_user_payload(client, f"tenant_a_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies_a)
    ws_a_id = get_default_workspace_id(client)

    # User B
    _, cookies_b, headers_b = register_user_payload(client, f"tenant_b_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies_b)

    # User B attempts to access User A's subscription
    res1 = client.get(f"/api/v1/billing/subscription?workspace_id={ws_a_id}")
    assert res1.status_code in (403, 404)

    # User B attempts to initiate checkout for User A's workspace
    res2 = client.post(
        f"/api/v1/billing/checkout?workspace_id={ws_a_id}",
        json={"plan_code": "pro", "currency": "INR"},
        headers=headers_b,
    )
    assert res2.status_code in (403, 404)


def test_create_checkout_session(client: TestClient):
    """Ensure authorized workspace members can create a checkout session."""
    _, cookies, headers = register_user_payload(client, f"checkout_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = get_default_workspace_id(client)

    res = client.post(
        f"/api/v1/billing/checkout?workspace_id={ws_id}",
        json={"plan_code": "pro", "currency": "INR"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["plan_code"] == "pro"
    assert data["amount_cents"] == 249900
    assert "session_id" in data
    assert "checkout_url" in data


def test_webhook_payment_captured_activates_plan(client: TestClient, db: Session):
    """Ensure verified payment webhooks activate plan upgrades on the server."""
    user, cookies, _ = register_user_payload(client, f"webhook_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = get_default_workspace_id(client)

    secret = MockBillingProvider.MOCK_WEBHOOK_SECRET
    payload = {
        "event": "order.paid",
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "notes": {
            "workspace_id": ws_id,
            "plan_code": "team",
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # Post to public webhook endpoint
    webhook_res = client.post(
        "/api/v1/billing/webhooks/mock",
        content=raw_body,
        headers={"x-mock-signature": sig, "Content-Type": "application/json"},
    )
    assert webhook_res.status_code == 200

    # Verify subscription in database is now team plan
    sub = db.scalar(select(Subscription).where(Subscription.workspace_id == uuid.UUID(ws_id)))
    assert sub is not None
    assert sub.plan.plan_code == "team"
    assert sub.status == "active"


def test_duplicate_webhook_is_idempotent(client: TestClient):
    """Ensure duplicate webhook events with the same event_id are processed idempotently."""
    secret = MockBillingProvider.MOCK_WEBHOOK_SECRET
    event_id = f"evt_dup_{uuid.uuid4().hex[:12]}"
    payload = {
        "event": "order.paid",
        "id": event_id,
        "notes": {
            "workspace_id": str(uuid.uuid4()),
            "plan_code": "pro",
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # First delivery
    res1 = client.post(
        "/api/v1/billing/webhooks/mock",
        content=raw_body,
        headers={"x-mock-signature": sig, "Content-Type": "application/json"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"

    # Second duplicate delivery
    res2 = client.post(
        "/api/v1/billing/webhooks/mock",
        content=raw_body,
        headers={"x-mock-signature": sig, "Content-Type": "application/json"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "already_processed"


def test_execution_run_blocked_when_quota_exhausted(client: TestClient, db: Session):
    """Ensure server-side quota enforcement blocks agent run dispatch when quota is exhausted."""
    user, cookies, headers = register_user_payload(client, f"quota_block_{uuid.uuid4()}@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = get_default_workspace_id(client)

    # Create project and task
    p_res = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Quota Test Project"},
        headers=headers,
    )
    assert p_res.status_code == 201
    project_id = uuid.UUID(p_res.json()["id"])

    task = Task(
        workspace_id=uuid.UUID(ws_id),
        project_id=project_id,
        title="Quota Exceeded Task",
        created_by=uuid.UUID(user["id"]),
        status="todo",
    )
    db.add(task)
    db.flush()

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
        plan_data={"summary": "Quota test plan"},
    )
    db.add(plan)
    db.commit()

    # Exhaust the Free plan quota (15 runs) by recording 15 runs in the ledger
    for i in range(15):
        entry = UsageLedgerEntry(
            workspace_id=uuid.UUID(ws_id),
            user_id=uuid.UUID(user["id"]),
            event_type="agent_run_started",
            quantity=1,
            operation_id=f"exhaust_{uuid.uuid4().hex[:12]}_{i}",
        )
        db.add(entry)
    db.commit()

    # Attempt to dispatch the 16th execution run -> Must be blocked with 402 Payment Required!
    exec_res = client.post(
        f"/api/v1/tasks/{task.id}/execution",
        json={"plan_id": str(plan.id)},
        headers=headers,
    )
    assert exec_res.status_code == 402
    data = exec_res.json()
    assert "QUOTA_EXCEEDED" in str(data)
