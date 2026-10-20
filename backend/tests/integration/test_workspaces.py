import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.models.workspace import WorkspaceMembership


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


def test_default_workspace_created_on_registration(client: TestClient, db: Session):
    user, cookies, _ = register_user_payload(client, "owner@example.com", "John Doe")
    client.cookies.clear()
    client.cookies.update(cookies)

    # List workspaces
    res = client.get("/api/v1/workspaces")
    assert res.status_code == 200
    workspaces = res.json()
    assert len(workspaces) == 1
    assert "John Doe's Workspace" in workspaces[0]["name"]
    assert workspaces[0]["role"] == "owner"

    # Verify DB membership
    membership = db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == uuid.UUID(user["id"])
        )
    )
    assert membership is not None
    assert membership.role == "owner"


def test_unauthenticated_workspace_access(client: TestClient):
    client.cookies.clear()
    res = client.get("/api/v1/workspaces")
    assert res.status_code == 401


def test_create_workspace(client: TestClient):
    _, cookies, headers = register_user_payload(client, "creator@example.com")
    client.cookies.clear()
    client.cookies.update(cookies)

    # Create new workspace
    create_res = client.post(
        "/api/v1/workspaces",
        json={"name": "Engineering Team"},
        headers=headers,
    )
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["name"] == "Engineering Team"
    assert data["role"] == "owner"

    # Verify list contains 2 workspaces now
    list_res = client.get("/api/v1/workspaces")
    assert len(list_res.json()) == 2


def test_cross_workspace_access_denied(client: TestClient):
    # User A
    _, cookies_a, _ = register_user_payload(client, "user_a@example.com")
    client.cookies.clear()
    client.cookies.update(cookies_a)
    ws_a_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # User B
    _, cookies_b, _ = register_user_payload(client, "user_b@example.com")
    client.cookies.clear()
    client.cookies.update(cookies_b)

    # User B attempts to access User A's workspace -> Returns 404 (prevent enumeration)
    cross_res = client.get(f"/api/v1/workspaces/{ws_a_id}")
    assert cross_res.status_code == 404
    assert "Workspace not found" in cross_res.json()["error"]["message"]


def test_workspace_members_and_owner_protection(client: TestClient, db: Session):
    # Owner
    owner_user, owner_cookies, owner_headers = register_user_payload(
        client, "lead@example.com"
    )
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # Colleague
    colleague_user, _, _ = register_user_payload(client, "peer@example.com")

    # Add colleague to workspace manually in DB
    membership_peer = WorkspaceMembership(
        workspace_id=uuid.UUID(ws_id),
        user_id=uuid.UUID(colleague_user["id"]),
        role="member",
    )
    db.add(membership_peer)
    db.commit()

    # Switch back to owner session on client
    client.cookies.clear()
    client.cookies.update(owner_cookies)

    # List members
    members_res = client.get(f"/api/v1/workspaces/{ws_id}/members")
    assert members_res.status_code == 200
    members = members_res.json()
    assert len(members) == 2

    # Find owner membership and peer membership
    owner_membership = [m for m in members if m["user_id"] == owner_user["id"]][0]
    peer_membership = [m for m in members if m["user_id"] == colleague_user["id"]][0]

    # Owner attempts to downgrade themselves -> Rejected (400)
    downgrade_owner = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{owner_membership['id']}",
        json={"role": "member"},
        headers=owner_headers,
    )
    assert downgrade_owner.status_code == 400
    assert "owner's role cannot be modified" in downgrade_owner.json()["error"]["message"]

    # Owner upgrades peer to admin -> 200
    upgrade_peer = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{peer_membership['id']}",
        json={"role": "admin"},
        headers=owner_headers,
    )
    assert upgrade_peer.status_code == 200
    assert upgrade_peer.json()["role"] == "admin"
