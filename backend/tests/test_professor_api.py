"""Professor summary: threshold suppression, dedup, and privacy tests."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.main import create_app

SETTINGS = Settings(app_env="test")
LECTURE_ID = "lecture-1"
COURSE_ID = "course-1"
MISSING_THRESHOLD = 5


def token_for(user_id: str, role: str = "student", course_id: str | None = None) -> str:
    """Mint a synthetic token."""

    return issue_access_token(
        SETTINGS,
        AuthenticatedActor(user_id=user_id, role=role, course_id=course_id),
    )


def auth_headers(token: str) -> dict[str, str]:
    """Build an authorization header."""

    return {"Authorization": f"Bearer {token}"}


def build_test_client() -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(SETTINGS))


def create_session(client: TestClient) -> str:
    """Create a synthetic session and return its id."""

    return client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": LECTURE_ID,
            "course_id": COURSE_ID,
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers=auth_headers(token_for("owner-1")),
    ).json()["session_id"]


def submit_event(client: TestClient, session_id: str, user_id: str, event_id: str) -> None:
    """Register one participant and submit one event as them."""

    client.post(
        f"/api/v1/sessions/{session_id}/participants",
        headers=auth_headers(token_for(user_id)),
    )
    response = client.post(
        f"/api/v1/sessions/{session_id}/events/batch",
        json={
            "lecture_id": LECTURE_ID,
            "events": [
                {
                    "event_id": event_id,
                    "session_id": session_id,
                    "event_type": "possible_missed_window",
                    "start_ms": 931_200,
                    "end_ms": 978_700,
                    "signals": ["head_away"],
                    "confidence": 0.76,
                }
            ],
        },
        headers=auth_headers(token_for(user_id)),
    )
    assert response.status_code == 202


def read_summary(client: TestClient, session_id: str, token: str):
    """Read the professor summary for a session."""

    return client.get(
        f"/api/v1/sessions/{session_id}/professor/summary",
        headers=auth_headers(token),
    )


def test_small_group_is_suppressed() -> None:
    """Fewer participants than the threshold must suppress aggregates."""

    client = build_test_client()
    session_id = create_session(client)
    for index in range(MISSING_THRESHOLD - 1):
        submit_event(client, session_id, f"student-{index}", f"event-{index}")

    response = read_summary(
        client, session_id, token_for("prof-1", role="professor", course_id=COURSE_ID)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_suppressed"] is True
    assert body["participant_count"] == MISSING_THRESHOLD - 1
    assert body["timeline_buckets"] is None
    assert body["highest_signal_intervals"] is None
    assert body["suggested_actions"] is None


def test_threshold_releases_anonymous_aggregates() -> None:
    """Meeting the threshold must release aggregate-only content."""

    client = build_test_client()
    session_id = create_session(client)
    for index in range(MISSING_THRESHOLD):
        submit_event(client, session_id, f"student-{index}", f"event-{index}")

    response = read_summary(
        client, session_id, token_for("prof-1", role="professor", course_id=COURSE_ID)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_suppressed"] is False
    assert body["participant_count"] == MISSING_THRESHOLD
    assert len(body["timeline_buckets"]) >= 1
    assert body["highest_signal_intervals"][0]["event_count"] == MISSING_THRESHOLD
    assert body["suggested_actions"]


def test_repeated_submissions_deduplicate_per_user() -> None:
    """One user submitting twice must still count as one participant."""

    client = build_test_client()
    session_id = create_session(client)
    for index in range(MISSING_THRESHOLD):
        submit_event(client, session_id, f"student-{index}", f"event-{index}")
    # The same user submits a second event; the participant count must not change.
    submit_event(client, session_id, "student-0", "event-extra")

    response = read_summary(
        client, session_id, token_for("prof-1", role="professor", course_id=COURSE_ID)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["participant_count"] == MISSING_THRESHOLD


def test_students_cannot_read_professor_summary() -> None:
    """Students must not read professor summaries."""

    client = build_test_client()
    session_id = create_session(client)
    response = read_summary(client, session_id, token_for("owner-1"))
    assert response.status_code == 403


def test_other_course_professor_is_forbidden() -> None:
    """Professors of a different course must receive 403."""

    client = build_test_client()
    session_id = create_session(client)
    response = read_summary(
        client, session_id, token_for("prof-2", role="professor", course_id="other")
    )
    assert response.status_code == 403


def test_summary_never_contains_student_identifiers() -> None:
    """The summary payload must not include any student user ids."""

    client = build_test_client()
    session_id = create_session(client)
    for index in range(MISSING_THRESHOLD):
        submit_event(client, session_id, f"student-{index}", f"event-{index}")

    response = read_summary(
        client, session_id, token_for("prof-1", role="professor", course_id=COURSE_ID)
    )
    assert response.status_code == 200
    raw = response.text
    for index in range(MISSING_THRESHOLD):
        assert f"student-{index}" not in raw
    assert "owner-1" not in raw
    assert "user_id" not in raw
    assert "confidence" not in raw
