import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.endpoints.integrations_github import github_service
from app.core.config import get_settings
from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.integrations.github.client import GitHubApiError, GitHubRateLimitError
from app.models.github import (
    GitHubInstallation,
    GitHubOAuthState,
    GitHubRepository,
)
from app.models.workspace import WorkspaceMembership


def get_error_message(res) -> str:
    data = res.json()
    if isinstance(data, dict):
        if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
            return data["error"]["message"].lower()
        if "detail" in data:
            return str(data["detail"]).lower()
    return str(data).lower()


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


def test_github_status_and_unauthenticated_and_cross_workspace(client: TestClient):
    # 1. Unauthenticated request rejected
    fake_ws = uuid.uuid4()
    res = client.get(f"/api/v1/integrations/github/status?workspace_id={fake_ws}")
    assert res.status_code == 401

    # 2. Authenticated User A
    user_a, cookies_a, _ = register_user(client, "gh_a@example.com", "User A")
    client.cookies.clear()
    client.cookies.update(cookies_a)
    ws_a_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # 3. Status for authorized workspace
    status_res = client.get(f"/api/v1/integrations/github/status?workspace_id={ws_a_id}")
    assert status_res.status_code == 200
    data = status_res.json()
    assert "is_configured" in data
    assert data["is_connected"] is False

    # 4. User B cannot view User A's workspace status (cross-workspace returns 404)
    _, cookies_b, _ = register_user(client, "gh_b@example.com", "User B")
    client.cookies.clear()
    client.cookies.update(cookies_b)

    cross_res = client.get(f"/api/v1/integrations/github/status?workspace_id={ws_a_id}")
    assert cross_res.status_code == 404


def test_initiate_install_unconfigured_and_role_restrictions(client: TestClient, db: Session):
    user_a, cookies_a, _ = register_user(client, "gh_admin@example.com", "Admin User")
    client.cookies.clear()
    client.cookies.update(cookies_a)
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # 1. When unconfigured, initiate_install raises 503
    settings = get_settings()
    with patch.object(settings, "GITHUB_APP_ID", None), patch.object(settings, "GITHUB_APP_CLIENT_ID", None):
        res = client.get(f"/api/v1/integrations/github/install?workspace_id={ws_id}")
        assert res.status_code == 503
        assert "not configured" in get_error_message(res)

    # 2. When configured, owner can initiate install
    with patch.object(settings, "GITHUB_APP_ID", "12345"), \
         patch.object(settings, "GITHUB_APP_CLIENT_ID", "Iv1.test"), \
         patch.object(settings, "GITHUB_APP_PRIVATE_KEY", "fake_key"):
        res = client.get(f"/api/v1/integrations/github/install?workspace_id={ws_id}")
        assert res.status_code == 200
        data = res.json()
        assert "install_url" in data
        assert "state" in data
        assert data["state"] in data["install_url"]

    # 3. Regular member cannot initiate install
    member_user, cookies_m, _ = register_user(client, "gh_member@example.com", "Member User")
    # Add member_user to ws_id with role="member"
    membership = WorkspaceMembership(
        workspace_id=uuid.UUID(ws_id),
        user_id=uuid.UUID(member_user["id"]),
        role="member",
    )
    db.add(membership)
    db.commit()

    client.cookies.clear()
    client.cookies.update(cookies_m)

    with patch.object(settings, "GITHUB_APP_ID", "12345"), \
         patch.object(settings, "GITHUB_APP_CLIENT_ID", "Iv1.test"), \
         patch.object(settings, "GITHUB_APP_PRIVATE_KEY", "fake_key"):
        m_res = client.get(f"/api/v1/integrations/github/install?workspace_id={ws_id}")
        assert m_res.status_code == 403
        assert "owners and administrators" in get_error_message(m_res)


def test_callback_state_validation_and_connection(client: TestClient, db: Session):
    user, cookies, _ = register_user(client, "callback_test@example.com", "Installer")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]
    settings = get_settings()

    mock_install_details = {
        "id": 998877,
        "account": {
            "login": "acme-corp",
            "type": "Organization",
            "avatar_url": "https://avatars.githubusercontent.com/u/1234",
        },
        "permissions": {"metadata": "read", "contents": "write", "pull_requests": "write"},
    }
    mock_repos = [
        {
            "id": 101,
            "name": "core-api",
            "full_name": "acme-corp/core-api",
            "owner": {"login": "acme-corp"},
            "default_branch": "main",
            "private": True,
            "archived": False,
        },
        {
            "id": 102,
            "name": "web-frontend",
            "full_name": "acme-corp/web-frontend",
            "owner": {"login": "acme-corp"},
            "default_branch": "master",
            "private": False,
            "archived": False,
        },
    ]

    with patch.object(settings, "GITHUB_APP_ID", "12345"), \
         patch.object(settings, "GITHUB_APP_CLIENT_ID", "Iv1.test"), \
         patch.object(settings, "GITHUB_APP_PRIVATE_KEY", "fake_key"), \
         patch.object(github_service.client, "get_installation_details", return_value=mock_install_details), \
         patch.object(github_service.client, "list_installation_repositories", return_value=mock_repos):

        # 1. Invalid / unknown state token
        res_invalid = client.get(
            "/api/v1/integrations/github/callback?state=invalid_token_123&installation_id=998877",
            follow_redirects=False,
        )
        assert res_invalid.status_code == 400

        # 2. Create an expired state in DB
        expired_state = GitHubOAuthState(
            workspace_id=uuid.UUID(ws_id),
            user_id=uuid.UUID(user["id"]),
            state_token="expired_token_abc",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.add(expired_state)
        db.commit()

        res_expired = client.get(
            "/api/v1/integrations/github/callback?state=expired_token_abc&installation_id=998877",
            follow_redirects=False,
        )
        assert res_expired.status_code == 400
        assert "expired" in get_error_message(res_expired)

        # 3. Create a valid state
        valid_state = GitHubOAuthState(
            workspace_id=uuid.UUID(ws_id),
            user_id=uuid.UUID(user["id"]),
            state_token="valid_token_xyz",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db.add(valid_state)
        db.commit()

        # 4. Valid callback execution -> Redirects to frontend and binds installation
        res_valid = client.get(
            "/api/v1/integrations/github/callback?state=valid_token_xyz&installation_id=998877",
            follow_redirects=False,
        )
        assert res_valid.status_code == 302
        assert "/repositories?installed=true" in res_valid.headers["location"]

        # 5. Replay attack: using the consumed state again fails
        res_replay = client.get(
            "/api/v1/integrations/github/callback?state=valid_token_xyz&installation_id=998877",
            follow_redirects=False,
        )
        assert res_replay.status_code == 400
        assert "already been consumed" in get_error_message(res_replay)

        # 6. Verify integration status is now connected and repos exist
        status_res = client.get(f"/api/v1/integrations/github/status?workspace_id={ws_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["is_connected"] is True
        assert status_data["account_login"] == "acme-corp"
        assert status_data["total_repositories"] == 2

        # 7. Attempting to bind the same installation_id to a different workspace is rejected (HTTP 409)
        _, cookies_other, _ = register_user(client, "other_ws@example.com", "Other User")
        client.cookies.clear()
        client.cookies.update(cookies_other)
        other_ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

        other_state = GitHubOAuthState(
            workspace_id=uuid.UUID(other_ws_id),
            user_id=uuid.UUID(client.get("/api/v1/auth/me").json()["id"]),
            state_token="other_ws_state_123",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db.add(other_state)
        db.commit()

        res_conflict = client.get(
            "/api/v1/integrations/github/callback?state=other_ws_state_123&installation_id=998877",
            follow_redirects=False,
        )
        assert res_conflict.status_code == 409
        assert "already connected to another workspace" in get_error_message(res_conflict)


def test_repository_listing_filtering_and_selection(client: TestClient, db: Session):
    user, cookies, headers = register_user(client, "repo_select_user@example.com", "Repo Manager")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # Directly create installation & repos in DB
    inst = GitHubInstallation(
        workspace_id=uuid.UUID(ws_id),
        installation_id=554433,
        account_login="org-dev",
        account_type="Organization",
        status="active",
    )
    db.add(inst)
    db.flush()

    repo1 = GitHubRepository(
        workspace_id=uuid.UUID(ws_id),
        installation_id=inst.id,
        github_repo_id=201,
        owner_login="org-dev",
        name="frontend-app",
        full_name="org-dev/frontend-app",
        is_private=False,
        is_selected=False,
    )
    repo2 = GitHubRepository(
        workspace_id=uuid.UUID(ws_id),
        installation_id=inst.id,
        github_repo_id=202,
        owner_login="org-dev",
        name="backend-service",
        full_name="org-dev/backend-service",
        is_private=True,
        is_selected=True,
    )
    db.add_all([repo1, repo2])
    db.commit()

    # 1. List repositories
    list_res = client.get(f"/api/v1/integrations/github/repositories?workspace_id={ws_id}")
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # 2. Search filter
    search_res = client.get(f"/api/v1/integrations/github/repositories?workspace_id={ws_id}&search=frontend")
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 1
    assert search_res.json()["items"][0]["name"] == "frontend-app"

    # 3. is_selected filter
    selected_res = client.get(f"/api/v1/integrations/github/repositories?workspace_id={ws_id}&is_selected=true")
    assert selected_res.status_code == 200
    assert selected_res.json()["total"] == 1
    assert selected_res.json()["items"][0]["name"] == "backend-service"

    # 4. Toggle selection on repo1 -> is_selected = True
    patch_res = client.patch(
        f"/api/v1/integrations/github/repositories/{repo1.id}",
        json={"is_selected": True},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_selected"] is True

    # 5. Member cannot toggle repository selection
    member_user, cookies_m, headers_m = register_user(client, "repo_member@example.com", "Member")
    membership = WorkspaceMembership(
        workspace_id=uuid.UUID(ws_id),
        user_id=uuid.UUID(member_user["id"]),
        role="member",
    )
    db.add(membership)
    db.commit()

    client.cookies.clear()
    client.cookies.update(cookies_m)

    m_patch = client.patch(
        f"/api/v1/integrations/github/repositories/{repo1.id}",
        json={"is_selected": False},
        headers=headers_m,
    )
    assert m_patch.status_code == 403


def test_sync_repositories_and_github_api_errors(client: TestClient, db: Session):
    user, cookies, headers = register_user(client, "sync_test@example.com", "Sync User")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    inst = GitHubInstallation(
        workspace_id=uuid.UUID(ws_id),
        installation_id=777888,
        account_login="sync-org",
        account_type="Organization",
        status="active",
    )
    db.add(inst)
    db.commit()

    # 1. Success sync
    mock_repos = [
        {
            "id": 901,
            "name": "synced-repo",
            "full_name": "sync-org/synced-repo",
            "owner": {"login": "sync-org"},
            "default_branch": "main",
            "private": True,
            "archived": False,
        }
    ]
    with patch.object(github_service.client, "list_installation_repositories", return_value=mock_repos):
        sync_res = client.post(
            f"/api/v1/integrations/github/repositories/sync?workspace_id={ws_id}",
            headers=headers,
        )
        assert sync_res.status_code == 200
        assert sync_res.json()["synced_count"] == 1

    # 2. Rate limit error from GitHub API returns 429
    with patch.object(
        github_service.client,
        "list_installation_repositories",
        side_effect=GitHubRateLimitError("Rate limit exceeded", reset_at=1700000000),
    ):
        rate_res = client.post(
            f"/api/v1/integrations/github/repositories/sync?workspace_id={ws_id}",
            headers=headers,
        )
        assert rate_res.status_code == 429

    # 3. Timeout from GitHub API returns 504
    with patch.object(
        github_service.client,
        "list_installation_repositories",
        side_effect=GitHubApiError("Connection timed out", status_code=504),
    ):
        timeout_res = client.post(
            f"/api/v1/integrations/github/repositories/sync?workspace_id={ws_id}",
            headers=headers,
        )
        assert timeout_res.status_code == 504


def test_disconnect_integration(client: TestClient, db: Session):
    user, cookies, headers = register_user(client, "disconn_user@example.com", "Disconnect Admin")
    client.cookies.clear()
    client.cookies.update(cookies)
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    inst = GitHubInstallation(
        workspace_id=uuid.UUID(ws_id),
        installation_id=665544,
        account_login="disconn-org",
        status="active",
    )
    db.add(inst)
    db.commit()

    # Disconnect
    dis_res = client.post(
        f"/api/v1/integrations/github/disconnect?workspace_id={ws_id}",
        headers=headers,
    )
    assert dis_res.status_code == 200

    # Verify status is now uninstalled
    status_res = client.get(f"/api/v1/integrations/github/status?workspace_id={ws_id}")
    assert status_res.status_code == 200
    assert status_res.json()["is_connected"] is False


def test_webhook_signature_verification_and_events(client: TestClient, db: Session):
    settings = get_settings()
    test_secret = "test_webhook_secret_key_123"

    user, _, _ = register_user(client, "webhook_owner@example.com", "Webhook Owner")
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]

    # Pre-populate installation
    inst = GitHubInstallation(
        workspace_id=uuid.UUID(ws_id),
        installation_id=443322,
        account_login="webhook-org",
        status="active",
    )
    db.add(inst)
    db.commit()

    payload = {
        "action": "deleted",
        "installation": {
            "id": 443322,
            "account": {"login": "webhook-org"},
        },
    }
    raw_payload = json.dumps(payload).encode("utf-8")

    # 1. Missing signature -> 401
    with patch.object(settings, "GITHUB_WEBHOOK_SECRET", test_secret):
        res_no_sig = client.post(
            "/api/v1/integrations/github/webhook",
            content=raw_payload,
            headers={"Content-Type": "application/json", "X-GitHub-Event": "installation", "X-GitHub-Delivery": "del-001"},
        )
        assert res_no_sig.status_code == 401

        # 2. Invalid signature -> 401
        res_bad_sig = client.post(
            "/api/v1/integrations/github/webhook",
            content=raw_payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=badsignature000000000000000000000000000000000000000000000000000",
                "X-GitHub-Event": "installation",
                "X-GitHub-Delivery": "del-002",
            },
        )
        assert res_bad_sig.status_code == 401

        # 3. Valid HMAC signature -> 200
        computed = hmac.new(test_secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        valid_sig = f"sha256={computed}"

        res_valid = client.post(
            "/api/v1/integrations/github/webhook",
            content=raw_payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": valid_sig,
                "X-GitHub-Event": "installation",
                "X-GitHub-Delivery": "del-003",
            },
        )
        assert res_valid.status_code == 200
        assert res_valid.json()["status"] == "success"

        # Verify DB installation is now marked uninstalled
        db.refresh(inst)
        assert inst.status == "uninstalled"
        assert inst.uninstalled_at is not None

        # 4. Duplicate delivery ID -> Ignored idempotently
        res_dup = client.post(
            "/api/v1/integrations/github/webhook",
            content=raw_payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": valid_sig,
                "X-GitHub-Event": "installation",
                "X-GitHub-Delivery": "del-003",
            },
        )
        assert res_dup.status_code == 200
        assert res_dup.json()["status"] == "ignored"
        assert res_dup.json()["reason"] == "duplicate_delivery"
