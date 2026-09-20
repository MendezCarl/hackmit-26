"""Registration, login, profile, and consent tests."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

SETTINGS = Settings(app_env="test")


def build_test_client() -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(SETTINGS))


def auth_headers(token: str) -> dict[str, str]:
    """Build an authorization header."""

    return {"Authorization": f"Bearer {token}"}


def register_account(client: TestClient, email: str, role: str = "student") -> dict:
    """Register one account and return the auth-session payload."""

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "display_name": email.split("@")[0],
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_returns_profile_and_token() -> None:
    """Registration must return a profile and a usable JWT."""

    client = build_test_client()
    body = register_account(client, "student@example.com")
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "student@example.com"
    assert body["user"]["role"] == "student"
    assert "password" not in str(body).lower() or "password_hash" not in str(body)

    profile = client.get("/api/v1/users/me", headers=auth_headers(body["access_token"]))
    assert profile.status_code == 200
    assert profile.json()["user_id"] == body["user"]["user_id"]


def test_register_rejects_duplicate_email() -> None:
    """Re-registering an existing email must fail with 409."""

    client = build_test_client()
    register_account(client, "student@example.com")
    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "email": "student@example.com",
            "password": "another-horse-battery",
            "display_name": "Copy",
            "role": "student",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate"


def test_register_rejects_short_password_and_bad_email() -> None:
    """Weak passwords and malformed emails must fail validation."""

    client = build_test_client()
    weak = client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "short",
            "display_name": "Weak",
            "role": "student",
        },
    )
    assert weak.status_code == 422
    malformed = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "correct-horse-battery",
            "display_name": "Malformed",
            "role": "student",
        },
    )
    assert malformed.status_code == 422


def test_login_issues_working_token_and_rejects_wrong_password() -> None:
    """Login must verify credentials and reject incorrect passwords."""

    client = build_test_client()
    register_account(client, "student@example.com")

    success = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "correct-horse-battery"},
    )
    assert success.status_code == 200
    token = success.json()["access_token"]
    profile = client.get("/api/v1/users/me", headers=auth_headers(token))
    assert profile.status_code == 200

    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "wrong-password-123"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "unauthorized"

    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "correct-horse-battery"},
    )
    assert unknown.status_code == 401


def test_login_is_case_insensitive_for_email() -> None:
    """Email lookup must normalize case."""

    client = build_test_client()
    register_account(client, "student@example.com")
    success = client.post(
        "/api/v1/auth/login",
        json={
            "email": "Student@Example.COM",
            "password": "correct-horse-battery",
        },
    )
    assert success.status_code == 200


def test_consent_defaults_off_and_updates() -> None:
    """Consent must default to opted out and store explicit updates."""

    client = build_test_client()
    token = register_account(client, "student@example.com")["access_token"]

    initial = client.get("/api/v1/users/me/consent", headers=auth_headers(token))
    assert initial.status_code == 200
    assert initial.json()["analytics_opt_in"] is False

    updated = client.put(
        "/api/v1/users/me/consent",
        json={"analytics_opt_in": True},
        headers=auth_headers(token),
    )
    assert updated.status_code == 200
    assert updated.json()["analytics_opt_in"] is True
    assert updated.json()["updated_at"] is not None


def test_profile_requires_authentication() -> None:
    """Unauthenticated profile access must be rejected."""

    client = build_test_client()
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
