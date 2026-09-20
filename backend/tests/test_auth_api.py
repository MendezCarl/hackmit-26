"""JWT authentication and cross-user access tests."""

import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import jwt as pyjwt
from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

SETTINGS = Settings(app_env="test")


def token_for(user_id: str, role: str = "student", course_id: str | None = None) -> str:
    """Mint a synthetic access token for one actor."""

    return issue_access_token(
        SETTINGS, AuthenticatedActor(user_id=user_id, role=role, course_id=course_id)
    )


def auth_headers(token: str) -> dict[str, str]:
    """Build an authorization header for a token."""

    return {"Authorization": f"Bearer {token}"}


def build_test_client() -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(Settings(app_env="test")))


def create_session(client: TestClient, user_id: str, token: str) -> str:
    """Create a synthetic session and return its id."""

    response = client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": "lecture-1",
            "course_id": "course-1",
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 201
    return response.json()["session_id"]


def test_missing_bearer_token_is_unauthorized() -> None:
    """Requests without a bearer token must receive the standard 401."""

    client = build_test_client()
    response = client.get("/api/v1/sessions/session_missing")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_invalid_token_is_unauthorized() -> None:
    """A tampered token must receive the standard 401."""

    client = build_test_client()
    response = client.get(
        "/api/v1/sessions/session_x", headers=auth_headers("not-a-jwt")
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_expired_token_is_unauthorized() -> None:
    """An expired token must receive the standard 401."""

    claims = {
        "sub": "student-1",
        "role": "student",
        "iat": int(time.time()) - 100,
        "exp": int(time.time()) - 10,
    }
    expired = pyjwt.encode(claims, SETTINGS.app_secret, algorithm="HS256")
    client = build_test_client()
    response = client.get("/api/v1/sessions/session_x", headers=auth_headers(expired))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_token_with_unknown_role_is_unauthorized() -> None:
    """Tokens carrying an unknown role claim must be rejected."""

    claims = {"sub": "user-1", "role": "admin", "exp": int(time.time()) + 600}
    forged = pyjwt.encode(claims, SETTINGS.app_secret, algorithm="HS256")
    client = build_test_client()
    response = client.get("/api/v1/sessions/session_x", headers=auth_headers(forged))
    assert response.status_code == 401


def test_cross_user_access_is_forbidden() -> None:
    """A user with no membership in a session must receive 403."""

    client = build_test_client()
    owner_token = token_for("owner-1")
    session_id = create_session(client, "owner-1", owner_token)

    stranger_token = token_for("stranger-2")
    response = client.get(
        f"/api/v1/sessions/{session_id}", headers=auth_headers(stranger_token)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_unknown_session_is_not_found() -> None:
    """Unknown sessions must produce 404, not 403, for members lookup."""

    client = build_test_client()
    response = client.get(
        "/api/v1/sessions/session_does_not_exist",
        headers=auth_headers(token_for("user-1")),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
