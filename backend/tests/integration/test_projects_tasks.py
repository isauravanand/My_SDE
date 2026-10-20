import uuid

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


def test_project_crud_lifecycle_and_slugs(client: TestClient):
    # 1. Register User A
    user_a, cookies_a, headers_a = register_user(client, "proja@example.com", "Project Lead")
    client.cookies.clear()
    client.cookies.update(cookies_a)

    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # 2. Create Project
    create_res = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Core Service", "description": "Backend API service"},
        headers=headers_a,
    )
    assert create_res.status_code == 201
    proj = create_res.json()
    assert proj["name"] == "Core Service"
    assert proj["slug"] == "core-service"
    assert proj["status"] == "active"
    proj_id = proj["id"]

    # 3. Create second project with same name -> Slug deduplicated
    dup_res = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Core Service"},
        headers=headers_a,
    )
    assert dup_res.status_code == 201
    assert dup_res.json()["slug"] != proj["slug"]
    assert dup_res.json()["slug"].startswith("core-service")

    # 4. Same slug in a different workspace works without conflict
    _, cookies_b, headers_b = register_user(client, "projb@example.com", "User B")
    client.cookies.clear()
    client.cookies.update(cookies_b)
    ws_b_id = client.get("/api/v1/workspaces").json()[0]["id"]

    b_res = client.post(
        f"/api/v1/projects?workspace_id={ws_b_id}",
        json={"name": "Core Service"},
        headers=headers_b,
    )
    assert b_res.status_code == 201
    assert b_res.json()["slug"] == "core-service"

    # Switch back to User A
    client.cookies.clear()
    client.cookies.update(cookies_a)

    # 5. List projects
    list_res = client.get(f"/api/v1/projects?workspace_id={ws_id}")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 2

    # 6. Get project detail
    get_res = client.get(f"/api/v1/projects/{proj_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Core Service"

    # 7. Update project
    update_res = client.patch(
        f"/api/v1/projects/{proj_id}",
        json={"name": "Core Microservice", "description": "Updated description"},
        headers=headers_a,
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Core Microservice"
    assert update_res.json()["description"] == "Updated description"

    # 8. Archive project
    archive_res = client.post(f"/api/v1/projects/{proj_id}/archive", headers=headers_a)
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "archived"
    assert archive_res.json()["archived_at"] is not None

    # Verify active list excludes archived project
    active_res = client.get(f"/api/v1/projects?workspace_id={ws_id}&status=active")
    assert len(active_res.json()) == 1

    # 9. Restore project
    restore_res = client.post(f"/api/v1/projects/{proj_id}/restore", headers=headers_a)
    assert restore_res.status_code == 200
    assert restore_res.json()["status"] == "active"
    assert restore_res.json()["archived_at"] is None


def test_task_crud_lifecycle_and_rules(client: TestClient, db: Session):
    user_a, cookies_a, headers_a = register_user(client, "tasklead@example.com", "Task Lead")
    client.cookies.clear()
    client.cookies.update(cookies_a)

    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]
    proj_res = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Platform App"},
        headers=headers_a,
    )
    proj_id = proj_res.json()["id"]

    # 1. Create Task
    task_res = client.post(
        f"/api/v1/projects/{proj_id}/tasks",
        json={
            "title": "Implement JWT rotation",
            "description": "Rotate signing keys regularly",
            "status": "todo",
            "priority": "high",
            "task_type": "feature",
        },
        headers=headers_a,
    )
    assert task_res.status_code == 201
    task = task_res.json()
    assert task["title"] == "Implement JWT rotation"
    assert task["status"] == "todo"
    assert task["priority"] == "high"
    assert task["completed_at"] is None
    task_id = task["id"]

    # 2. Invalid status and priority values fail validation (422)
    inv_res = client.post(
        f"/api/v1/projects/{proj_id}/tasks",
        json={"title": "Invalid task", "status": "unknown_status"},
        headers=headers_a,
    )
    assert inv_res.status_code == 422

    inv_prio = client.post(
        f"/api/v1/projects/{proj_id}/tasks",
        json={"title": "Invalid prio", "priority": "super_urgent"},
        headers=headers_a,
    )
    assert inv_prio.status_code == 422

    # 3. Unauthorized task assignment (user not in workspace rejected with 400)
    fake_assignee = uuid.uuid4()
    bad_assign = client.post(
        f"/api/v1/projects/{proj_id}/tasks",
        json={"title": "Bad Assignee", "assignee_id": str(fake_assignee)},
        headers=headers_a,
    )
    assert bad_assign.status_code == 400
    assert "Assignee must be a member of the workspace" in bad_assign.json()["error"]["message"]

    # 4. Status transition and completed_at timestamp
    done_res = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
        headers=headers_a,
    )
    assert done_res.status_code == 200
    assert done_res.json()["status"] == "done"
    assert done_res.json()["completed_at"] is not None

    # Reopening task clears completed_at
    reopen_res = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "in_progress"},
        headers=headers_a,
    )
    assert reopen_res.status_code == 200
    assert reopen_res.json()["status"] == "in_progress"
    assert reopen_res.json()["completed_at"] is None

    # 5. Archive & restore task
    archive_task = client.post(f"/api/v1/tasks/{task_id}/archive", headers=headers_a)
    assert archive_task.status_code == 200
    assert archive_task.json()["archived_at"] is not None

    restore_task = client.post(f"/api/v1/tasks/{task_id}/restore", headers=headers_a)
    assert restore_task.status_code == 200
    assert restore_task.json()["archived_at"] is None


def test_archived_project_restrictions(client: TestClient):
    _, cookies, headers = register_user(client, "arch_user@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]
    proj = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Archived Repo"},
        headers=headers,
    ).json()

    # Archive project
    client.post(f"/api/v1/projects/{proj['id']}/archive", headers=headers)

    # Attempting to create task in archived project must fail (400)
    task_res = client.post(
        f"/api/v1/projects/{proj['id']}/tasks",
        json={"title": "Task in dead project"},
        headers=headers,
    )
    assert task_res.status_code == 400
    assert "Cannot create tasks in an archived project" in task_res.json()["error"]["message"]


def test_task_search_filter_pagination(client: TestClient):
    _, cookies, headers = register_user(client, "search_user@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]
    proj = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Search Project"},
        headers=headers,
    ).json()

    # Create 3 distinct tasks
    client.post(
        f"/api/v1/projects/{proj['id']}/tasks",
        json={"title": "Fix memory leak in parser", "status": "todo", "priority": "critical"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{proj['id']}/tasks",
        json={"title": "Add OAuth support", "status": "in_progress", "priority": "high"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{proj['id']}/tasks",
        json={"title": "Update documentation", "status": "done", "priority": "low"},
        headers=headers,
    )

    # Filter by status
    todo_res = client.get(f"/api/v1/tasks?workspace_id={ws_id}&status=todo")
    assert todo_res.json()["total"] == 1
    assert todo_res.json()["items"][0]["title"] == "Fix memory leak in parser"

    # Filter by priority
    high_res = client.get(f"/api/v1/tasks?workspace_id={ws_id}&priority=high")
    assert high_res.json()["total"] == 1
    assert high_res.json()["items"][0]["title"] == "Add OAuth support"

    # Search keyword
    search_res = client.get(f"/api/v1/tasks?workspace_id={ws_id}&search=memory")
    assert search_res.json()["total"] == 1
    assert "memory leak" in search_res.json()["items"][0]["title"]

    # Pagination: limit=1, offset=1
    page_res = client.get(f"/api/v1/tasks?workspace_id={ws_id}&limit=1&offset=1")
    assert page_res.json()["total"] == 3
    assert len(page_res.json()["items"]) == 1


def test_cross_workspace_project_and_task_isolation(client: TestClient):
    # Workspace A
    _, cookies_a, headers_a = register_user(client, "iso_a@example.com")
    client.cookies.clear()
    client.cookies.update(cookies_a)
    ws_a_id = client.get("/api/v1/workspaces").json()[0]["id"]

    proj_a = client.post(
        f"/api/v1/projects?workspace_id={ws_a_id}",
        json={"name": "Secret Project A"},
        headers=headers_a,
    ).json()
    task_a = client.post(
        f"/api/v1/projects/{proj_a['id']}/tasks",
        json={"title": "Secret Task A"},
        headers=headers_a,
    ).json()

    # Workspace B
    _, cookies_b, headers_b = register_user(client, "iso_b@example.com")
    client.cookies.clear()
    client.cookies.update(cookies_b)

    # User B tries to view Project A -> 404
    cross_proj = client.get(f"/api/v1/projects/{proj_a['id']}")
    assert cross_proj.status_code == 404

    # User B tries to view Task A -> 404
    cross_task = client.get(f"/api/v1/tasks/{task_a['id']}")
    assert cross_task.status_code == 404

    # User B tries to create task under Project A -> 404
    cross_create = client.post(
        f"/api/v1/projects/{proj_a['id']}/tasks",
        json={"title": "Malicious Task"},
        headers=headers_b,
    )
    assert cross_create.status_code == 404

    # User B tries to update Task A -> 404
    cross_update = client.patch(
        f"/api/v1/tasks/{task_a['id']}",
        json={"title": "Hacked Title"},
        headers=headers_b,
    )
    assert cross_update.status_code == 404


def test_dashboard_summary_and_recent_activity(client: TestClient):
    _, cookies, headers = register_user(client, "dash_user@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # Initially empty summary
    init_dash = client.get(f"/api/v1/dashboard/summary?workspace_id={ws_id}")
    assert init_dash.status_code == 200
    data = init_dash.json()
    assert data["total_projects"] == 0
    assert data["open_tasks"] == 0
    assert data["in_progress_tasks"] == 0
    assert data["completed_tasks"] == 0
    assert data["agent_runs"] == 0

    # Create project and tasks
    proj = client.post(
        f"/api/v1/projects?workspace_id={ws_id}",
        json={"name": "Dashboard Project"},
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/projects/{proj['id']}/tasks",
        json={"title": "Task 1", "status": "in_progress"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{proj['id']}/tasks",
        json={"title": "Task 2", "status": "todo"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{proj['id']}/tasks",
        json={"title": "Task 3", "status": "done"},
        headers=headers,
    )

    # Check updated summary
    dash_res = client.get(f"/api/v1/dashboard/summary?workspace_id={ws_id}")
    dash_data = dash_res.json()
    assert dash_data["total_projects"] == 1
    assert dash_data["open_tasks"] == 2  # in_progress + todo
    assert dash_data["in_progress_tasks"] == 1
    assert dash_data["completed_tasks"] == 1

    # Check recent activity feed
    act_res = client.get(f"/api/v1/dashboard/recent-activity?workspace_id={ws_id}")
    assert act_res.status_code == 200
    activities = act_res.json()
    assert len(activities) >= 4  # 1 project_created + 3 task_created
    # Order should be chronological descending
    assert activities[0]["created_at"] >= activities[-1]["created_at"]
