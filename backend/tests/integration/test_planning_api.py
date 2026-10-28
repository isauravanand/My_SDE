from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME


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


def test_planning_api_complete_lifecycle(client: TestClient, db: Session):
    # 1. Register user and get workspace
    user, cookies, headers = register_user(client, "planner@example.com", "Planning Engineer")
    ws_res = client.get("/api/v1/workspaces", cookies=cookies)
    workspaces = ws_res.json()
    workspace = workspaces[0]
    workspace_id = workspace["id"]

    # 2. Create project
    proj_res = client.post(
        f"/api/v1/projects?workspace_id={workspace_id}",
        json={"name": "API Service", "description": "Backend API project"},
        cookies=cookies,
        headers=headers,
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # 3. Create task
    task_res = client.post(
        f"/api/v1/projects/{project_id}/tasks?workspace_id={workspace_id}",
        json={
            "title": "Implement JWT rotation and token refresh endpoint",
            "description": "Add refresh token verification, rotation logic, and blacklisting support.",
            "task_type": "feature",
            "priority": "high",
        },
        cookies=cookies,
        headers=headers,
    )
    assert task_res.status_code == 201
    task = task_res.json()
    task_id = task["id"]

    # 4. Initially, no plan exists for task
    get_plan_res = client.get(
        f"/api/v1/tasks/{task_id}/plan?workspace_id={workspace_id}",
        cookies=cookies,
    )
    assert get_plan_res.status_code == 200
    assert get_plan_res.json() is None

    # 5. Trigger planning run via POST /tasks/{task_id}/plan
    trigger_res = client.post(
        f"/api/v1/tasks/{task_id}/plan?workspace_id={workspace_id}",
        json={"force_new": True},
        cookies=cookies,
        headers=headers,
    )
    assert trigger_res.status_code == 202
    run_data = trigger_res.json()
    assert run_data["task_id"] == task_id
    assert run_data["status"] in ["queued", "running", "completed"]
    run_id = run_data["id"]

    # 6. Retrieve planning run status via GET /planning/runs/{run_id}
    run_status_res = client.get(
        f"/api/v1/planning/runs/{run_id}?workspace_id={workspace_id}",
        cookies=cookies,
    )
    assert run_status_res.status_code == 200
    detail = run_status_res.json()
    assert detail["id"] == run_id

    # 7. List plans for task via GET /tasks/{task_id}/plans
    list_plans_res = client.get(
        f"/api/v1/tasks/{task_id}/plans?workspace_id={workspace_id}&limit=10",
        cookies=cookies,
    )
    assert list_plans_res.status_code == 200
    plans_list = list_plans_res.json()
    assert isinstance(plans_list, list)


def test_cross_workspace_planning_isolation(client: TestClient, db: Session):
    # Register user 1 in workspace 1
    _, cookies1, headers1 = register_user(client, "user1@example.com", "User One")
    client.cookies.clear()
    client.cookies.update(cookies1)
    ws1 = client.get("/api/v1/workspaces").json()[0]["id"]

    # User 1 creates project & task
    p1 = client.post(
        f"/api/v1/projects?workspace_id={ws1}",
        json={"name": "P1"},
        headers=headers1,
    ).json()["id"]

    t1 = client.post(
        f"/api/v1/projects/{p1}/tasks?workspace_id={ws1}",
        json={"title": "Task One Confidential", "description": "Private"},
        headers=headers1,
    ).json()["id"]

    # Register user 2 in workspace 2
    _, cookies2, headers2 = register_user(client, "user2@example.com", "User Two")
    client.cookies.clear()
    client.cookies.update(cookies2)
    ws2 = client.get("/api/v1/workspaces").json()[0]["id"]

    # User 2 attempts to trigger planning for User 1's task
    foreign_trigger = client.post(
        f"/api/v1/tasks/{t1}/plan?workspace_id={ws2}",
        json={},
        headers=headers2,
    )
    assert foreign_trigger.status_code in [403, 404]

    # User 2 attempts to read plan for User 1's task
    foreign_read = client.get(
        f"/api/v1/tasks/{t1}/plan?workspace_id={ws2}",
    )
    assert foreign_read.status_code in [403, 404]


def test_cancel_planning_run(client: TestClient, db: Session):
    user, cookies, headers = register_user(client, "canceller@example.com", "Canceller")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws = client.get("/api/v1/workspaces").json()[0]["id"]

    proj = client.post(
        f"/api/v1/projects?workspace_id={ws}",
        json={"name": "Cancel Project"},
        headers=headers,
    ).json()["id"]

    task = client.post(
        f"/api/v1/projects/{proj}/tasks?workspace_id={ws}",
        json={"title": "Task to Cancel", "description": "Description"},
        cookies=cookies,
        headers=headers,
    ).json()["id"]

    trigger_res = client.post(
        f"/api/v1/tasks/{task}/plan?workspace_id={ws}",
        json={},
        cookies=cookies,
        headers=headers,
    )
    run_id = trigger_res.json()["id"]

    # Cancel the run
    cancel_res = client.post(
        f"/api/v1/planning/runs/{run_id}/cancel?workspace_id={ws}",
        cookies=cookies,
        headers=headers,
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] in ["cancelled", "completed"]
