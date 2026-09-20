"""Lecture-session lifecycle tests, including lecture_id versus session_id."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.main import create_app

SETTINGS = Settings(app_env="test")


def token_for(user_id: str) -> str:
    """Mint a synthetic student token."""

    return issue_access_token(SETTINGS, AuthenticatedActor(user_id=user_id, role="student"))


def auth_headers(token: str) -> dict[str, str]:
    """Build an authorization header."""

    return {"Authorization": f"Bearer {token}"}


def build_test_client() -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(SETTINGS))


def test_create_session_returns_typed_contract() -> None:
    """Session creation must return the full LectureSession contract."""

    client = build_test_client()
    response = client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": "lecture-1",
            "course_id": "course-1",
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers=auth_headers(token_for("owner-1")),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["lecture_id"] == "lecture-1"
    assert body["session_id"].startswith("session_")
    assert body["session_id"] != body["lecture_id"]
    assert len(body["join_code"]) == 6
    assert set(body["join_code"]) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
    assert body["status"] == "active"
    assert body["session_clock_origin"].endswith("Z")
    assert body["owner_id"] == "owner-1"


def test_create_session_rejects_unexpected_fields() -> None:
    """Unexpected request fields must be rejected by strict validation."""

    client = build_test_client()
    response = client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": "lecture-1",
            "course_id": "course-1",
            "title": "Synthetic Lecture",
            "mode": "in_person",
            "owner_id": "attacker-1",
        },
        headers=auth_headers(token_for("owner-1")),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_owner_can_read_session_and_participant_can_join() -> None:
    """Registered participants must be able to read the session."""

    client = build_test_client()
    owner_token = token_for("owner-1")
    session_id = client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": "lecture-1",
            "course_id": "course-1",
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers=auth_headers(owner_token),
    ).json()["session_id"]

    participant_token = token_for("participant-1")
    join = client.post(
        f"/api/v1/sessions/{session_id}/participants",
        headers=auth_headers(participant_token),
    )
    assert join.status_code == 201
    assert join.json()["participant_count"] == 1

    read = client.get(
        f"/api/v1/sessions/{session_id}", headers=auth_headers(participant_token)
    )
    assert read.status_code == 200
    assert read.json()["session_id"] == session_id
    assert "no-store" in read.headers["cache-control"]


def test_authenticated_user_can_resolve_and_end_join_code() -> None:
    """Join-code resolution accepts normalized input and expires on ending."""
    client = build_test_client()
    owner_token = token_for("owner-1")
    created = client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": "lecture-1",
            "course_id": "course-1",
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers=auth_headers(owner_token),
    )
    session = created.json()
    join_code = session["join_code"]

    resolved = client.get(
        f"/api/v1/sessions/by-join-code/  {join_code.lower()}  ",
        headers=auth_headers(token_for("student-1")),
    )
    assert resolved.status_code == 200
    assert resolved.json()["session_id"] == session["session_id"]

    missing = client.get(
        "/api/v1/sessions/by-join-code/UNKNOWN",
        headers=auth_headers(token_for("student-2")),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["details"]["join_code"] == "UNKNOWN"

    ended = client.post(
        f"/api/v1/sessions/{session['session_id']}/end",
        headers=auth_headers(owner_token),
    )
    assert ended.status_code == 200
    assert client.app.state.store.session_join_codes.get(join_code) is None

    expired = client.get(
        f"/api/v1/sessions/by-join-code/{join_code}",
        headers=auth_headers(token_for("student-3")),
    )
    assert expired.status_code == 404
