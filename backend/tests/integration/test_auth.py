import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    hash_password,
    verify_password,
)
from app.models.session import Session as UserSession
from app.models.user import User
from app.services.email import get_email_service


def test_password_hashing_and_verification():
    raw = "MySecurePassword123!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert hashed.startswith("$argon2id$")
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_registration_success(client: TestClient, db: Session):
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "SuperSecretPassword123!",
            "full_name": "Alice Developer",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["full_name"] == "Alice Developer"
    assert data["is_verified"] is False
    assert data["is_active"] is True
    assert "password" not in data

    # Verify cookies
    assert SESSION_COOKIE_NAME in response.cookies
    assert CSRF_COOKIE_NAME in response.cookies

    # Verify session token in DB is hashed, not raw
    raw_token = response.cookies[SESSION_COOKIE_NAME]
    db_session = db.scalar(select(UserSession).where(UserSession.user_id == uuid.UUID(data["id"])))
    assert db_session is not None
    assert db_session.token_hash != raw_token


def test_registration_duplicate_email(client: TestClient):
    client.cookies.clear()
    client.post(
        "/api/v1/auth/register",
        json={"email": "duplicate@example.com", "password": "Password123!"},
    )
    dup_res = client.post(
        "/api/v1/auth/register",
        json={"email": "duplicate@example.com", "password": "Password123!"},
    )
    assert dup_res.status_code == 409
    assert "already exists" in dup_res.json()["error"]["message"]


def test_registration_invalid_input(client: TestClient):
    client.cookies.clear()
    # Invalid email
    res1 = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "Password123!"},
    )
    assert res1.status_code == 422

    # Password too short (< 8 chars)
    res2 = client.post(
        "/api/v1/auth/register",
        json={"email": "valid@example.com", "password": "short"},
    )
    assert res2.status_code == 422


def test_login_success_and_cookie_flags(client: TestClient):
    client.cookies.clear()
    # Register first
    client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "SecretPassword123!"},
    )
    client.cookies.clear()

    # Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "SecretPassword123!"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["email"] == "bob@example.com"
    assert SESSION_COOKIE_NAME in login_res.cookies


def test_login_invalid_credentials(client: TestClient):
    client.cookies.clear()
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "WrongPassword123!"},
    )
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["error"]["message"]


def test_current_user_unauthenticated(client: TestClient):
    client.cookies.clear()
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


def test_current_user_authenticated(client: TestClient):
    client.cookies.clear()
    client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "SecretPassword123!"},
    )

    me_res = client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "carol@example.com"


def test_csrf_rejection_for_state_changing_requests(client: TestClient):
    client.cookies.clear()
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "SecretPassword123!"},
    )
    csrf_cookie = reg_res.cookies[CSRF_COOKIE_NAME]

    # POST logout with session cookie but MISSING X-CSRF-Token header -> 403
    res_no_header = client.post("/api/v1/auth/logout")
    assert res_no_header.status_code == 403

    # POST logout with mismatched X-CSRF-Token header -> 403
    res_mismatch = client.post(
        "/api/v1/auth/logout",
        headers={CSRF_HEADER_NAME: "wrong-csrf-token"},
    )
    assert res_mismatch.status_code == 403

    # POST logout with VALID X-CSRF-Token header -> 200
    res_valid = client.post(
        "/api/v1/auth/logout",
        headers={CSRF_HEADER_NAME: csrf_cookie},
    )
    assert res_valid.status_code == 200
    assert "Logged out successfully" in res_valid.json()["message"]


def test_session_revocation_on_logout(client: TestClient, db: Session):
    client.cookies.clear()
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": "eve@example.com", "password": "SecretPassword123!"},
    )
    csrf_cookie = reg_res.cookies[CSRF_COOKIE_NAME]

    # Logout
    client.post(
        "/api/v1/auth/logout",
        headers={CSRF_HEADER_NAME: csrf_cookie},
    )

    # Submitting request to /auth/me must now return 401
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


def test_expired_session(client: TestClient, db: Session):
    client.cookies.clear()
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": "frank@example.com", "password": "SecretPassword123!"},
    )
    user_id = reg_res.json()["id"]

    # Manually expire session in DB
    user_session = db.scalar(select(UserSession).where(UserSession.user_id == uuid.UUID(user_id)))
    user_session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


def test_email_verification_workflow_and_single_use(client: TestClient, db: Session):
    client.cookies.clear()
    email = "grace@example.com"
    email_service = get_email_service()

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecretPassword123!"},
    )

    # Retrieve generated token from dev email adapter
    raw_token = email_service.get_last_token(email, "email_verification")
    assert raw_token is not None

    # Verify email
    ver_res = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert ver_res.status_code == 200

    # User in DB should now have is_verified == True
    user = db.scalar(select(User).where(User.email == email))
    assert user.is_verified is True
    assert user.verified_at is not None

    # Single-use enforcement: Attempting to verify with same token again must fail (400)
    second_res = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert second_res.status_code == 400


def test_password_reset_privacy_and_workflow(client: TestClient, db: Session):
    client.cookies.clear()
    email = "heidi@example.com"
    email_service = get_email_service()

    # Request reset for non-existent email -> Returns 200 (prevents enumeration)
    anon_res = client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert anon_res.status_code == 200

    # Register user
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "OldPassword123!"},
    )
    client.cookies.clear()

    # Request reset for registered user
    reset_req = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert reset_req.status_code == 200

    # Retrieve reset token from dev email adapter
    raw_reset_token = email_service.get_last_token(email, "password_reset")
    assert raw_reset_token is not None

    # Perform password reset
    reset_action = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_reset_token, "new_password": "NewSecretPassword123!"},
    )
    assert reset_action.status_code == 200

    # Token cannot be reused (single-use)
    reused = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_reset_token, "new_password": "AnotherPassword123!"},
    )
    assert reused.status_code == 400

    # Login with old password must fail
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "OldPassword123!"},
    )
    assert old_login.status_code == 401

    # Login with new password succeeds
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "NewSecretPassword123!"},
    )
    assert new_login.status_code == 200
