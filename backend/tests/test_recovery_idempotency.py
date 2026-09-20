"""Recovery job idempotency tests using the ``Idempotency-Key`` header."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.auth.tokens import AuthenticatedActor, issue_access_token  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

SETTINGS = Settings(app_env="test")
LECTURE_ID = "lecture-1"


def token_for(user_id: str) -> str:
    """Mint a synthetic student token."""

    return issue_access_token(SETTINGS, AuthenticatedActor(user_id=user_id, role="student"))


def auth_headers(token: str) -> dict[str, str]:
    """Build an authorization header."""

    return {"Authorization": f"Bearer {token}"}


def build_test_client() -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(SETTINGS))


def prepare_session_with_transcript(client: TestClient) -> str:
    """Create a session with final transcript chunks around the interval."""

    session_id = client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": LECTURE_ID,
            "course_id": "course-1",
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers=auth_headers(token_for("owner-1")),
    ).json()["session_id"]
    response = client.post(
        f"/api/v1/sessions/{session_id}/transcript/batch",
        json={
            "lecture_id": LECTURE_ID,
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "session_id": session_id,
                    "start_ms": 900_000,
                    "end_ms": 960_000,
                    "text": "Queries measure similarity against keys.",
                    "source": "local_transcription",
                    "is_final": True,
                    "revision": 1,
                }
            ],
        },
        headers=auth_headers(token_for("owner-1")),
    )
    assert response.status_code == 202
    return session_id


def test_same_idempotency_key_returns_original_job() -> None:
    """Retrying with the same key must return the original job."""

    client = build_test_client()
    session_id = prepare_session_with_transcript(client)
    headers = {"Idempotency-Key": "retry-001", **auth_headers(token_for("owner-1"))}

    first = client.post(
        f"/api/v1/sessions/{session_id}/recovery/jobs",
        json={"start_ms": 931_200, "end_ms": 978_700},
        headers=headers,
    )
    assert first.status_code == 202
    second = client.post(
        f"/api/v1/sessions/{session_id}/recovery/jobs",
        json={"start_ms": 931_200, "end_ms": 978_700},
        headers=headers,
    )
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]


def test_different_idempotency_keys_create_distinct_jobs() -> None:
    """Different keys must create separate jobs even for the same interval."""

    client = build_test_client()
    session_id = prepare_session_with_transcript(client)
    token = token_for("owner-1")

    first = client.post(
        f"/api/v1/sessions/{session_id}/recovery/jobs",
        json={"start_ms": 931_200, "end_ms": 978_700},
        headers={"Idempotency-Key": "retry-a", **auth_headers(token)},
    )
    second = client.post(
        f"/api/v1/sessions/{session_id}/recovery/jobs",
        json={"start_ms": 931_200, "end_ms": 978_700},
        headers={"Idempotency-Key": "retry-b", **auth_headers(token)},
    )
    assert first.json()["job_id"] != second.json()["job_id"]


def test_idempotency_keys_are_scoped_per_user() -> None:
    """The same key for a different user must create a fresh job."""

    client = build_test_client()
    session_id = prepare_session_with_transcript(client)
    participant_token = token_for("participant-1")
    client.post(
        f"/api/v1/sessions/{session_id}/participants",
        headers=auth_headers(participant_token),
    )

    owner_job = client.post(
        f"/api/v1/sessions/{session_id}/recovery/jobs",
        json={"start_ms": 931_200, "end_ms": 978_700},
        headers={"Idempotency-Key": "shared-key", **auth_headers(token_for("owner-1"))},
    )
    participant_job = client.post(
        f"/api/v1/sessions/{session_id}/recovery/jobs",
        json={"start_ms": 931_200, "end_ms": 978_700},
        headers={"Idempotency-Key": "shared-key", **auth_headers(participant_token)},
    )
    assert owner_job.json()["job_id"] != participant_job.json()["job_id"]


def test_overlapping_source_events_expand_the_context_interval() -> None:
    """Merging must let a source event outside the request pull in its transcript."""

    client = build_test_client()
    session_id = prepare_session_with_transcript(client)
    # Add an event that starts before the requested interval and overlaps it.
    client.post(
        f"/api/v1/sessions/{session_id}/events/batch",
        json={
            "lecture_id": LECTURE_ID,
            "events": [
                {
                    "event_id": "event-early",
                    "session_id": session_id,
                    "event_type": "possible_missed_window",
                    "start_ms": 910_000,
                    "end_ms": 940_000,
                    "signals": ["head_away"],
                    "confidence": 0.6,
                }
            ],
        },
        headers=auth_headers(token_for("owner-1")),
    )
    job = client.post(
        f"/api/v1/sessions/{session_id}/recovery/jobs",
        json={
            "start_ms": 935_000,
            "end_ms": 950_000,
            "source_event_ids": ["event-early"],
        },
        headers=auth_headers(token_for("owner-1")),
    )
    assert job.status_code == 202
    assert job.json()["status"] == "completed"
