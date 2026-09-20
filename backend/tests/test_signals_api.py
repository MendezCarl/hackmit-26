"""Signal-event ingestion, correction, and raw-media rejection tests."""

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


def token_for(user_id: str) -> str:
    """Mint a synthetic student token."""

    return issue_access_token(SETTINGS, AuthenticatedActor(user_id=user_id, role="student"))


def auth_headers(token: str) -> dict[str, str]:
    """Build an authorization header."""

    return {"Authorization": f"Bearer {token}"}


def build_test_client() -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(SETTINGS))


def create_session(client: TestClient) -> str:
    """Create a synthetic session and return its id."""

    response = client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": LECTURE_ID,
            "course_id": COURSE_ID,
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers=auth_headers(token_for("owner-1")),
    )
    return response.json()["session_id"]


def ingest_events(client: TestClient, session_id: str, token: str, events: list[dict]):
    """Submit a batch of events to a session."""

    return client.post(
        f"/api/v1/sessions/{session_id}/events/batch",
        json={"lecture_id": LECTURE_ID, "events": events},
        headers=auth_headers(token),
    )


def sample_event(session_id: str, event_id: str = "event-1") -> dict:
    """Build one valid coarse signal event."""

    return {
        "event_id": event_id,
        "session_id": session_id,
        "event_type": "possible_missed_window",
        "start_ms": 931_200,
        "end_ms": 978_700,
        "signals": ["head_away"],
        "confidence": 0.76,
        "user_confirmed": None,
    }


def test_ingest_events_returns_accepted_and_eligible() -> None:
    """Valid batches list accepted ids and missed-window-eligible ids."""

    client = build_test_client()
    session_id = create_session(client)
    response = ingest_events(
        client, session_id, token_for("owner-1"), [sample_event(session_id)]
    )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted_event_ids"] == ["event-1"]
    # The 47.5-second sample interval exceeds the 30-second default rule.
    assert body["recovery_eligible_event_ids"] == ["event-1"]


def test_invalid_interval_is_rejected() -> None:
    """Reversed, empty, and negative intervals must fail validation."""

    client = build_test_client()
    session_id = create_session(client)
    invalid = sample_event(session_id)
    invalid["start_ms"] = 500
    invalid["end_ms"] = 500
    response = ingest_events(client, session_id, token_for("owner-1"), [invalid])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_out_of_range_confidence_is_rejected() -> None:
    """Confidence outside [0, 1] must fail validation."""

    client = build_test_client()
    session_id = create_session(client)
    invalid = sample_event(session_id)
    invalid["confidence"] = 1.5
    response = ingest_events(client, session_id, token_for("owner-1"), [invalid])
    assert response.status_code == 422


def test_duplicate_event_is_rejected() -> None:
    """Re-submitting an existing event_id must fail with 409."""

    client = build_test_client()
    session_id = create_session(client)
    first = ingest_events(
        client, session_id, token_for("owner-1"), [sample_event(session_id)]
    )
    assert first.status_code == 202
    duplicate = ingest_events(
        client, session_id, token_for("owner-1"), [sample_event(session_id)]
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate"


def test_lecture_mismatch_is_rejected() -> None:
    """Batches carrying the wrong lecture_id must fail validation."""

    client = build_test_client()
    session_id = create_session(client)
    response = client.post(
        f"/api/v1/sessions/{session_id}/events/batch",
        json={"lecture_id": "other-lecture", "events": [sample_event(session_id)]},
        headers=auth_headers(token_for("owner-1")),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_raw_media_fields_are_rejected() -> None:
    """Unexpected fields such as raw frames must be rejected by contract."""

    client = build_test_client()
    session_id = create_session(client)
    raw_media_event = sample_event(session_id)
    raw_media_event["audio_frames"] = ["base64-audio"]
    raw_media_event["webcam_frame"] = "base64-frame"
    response = ingest_events(client, session_id, token_for("owner-1"), [raw_media_event])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_oversized_batch_is_rejected() -> None:
    """Batches above the configured maximum must fail with 413."""

    client = build_test_client()
    session_id = create_session(client)
    events = [
        sample_event(session_id, event_id=f"event-{index}")
        for index in range(SETTINGS.max_batch_events + 1)
    ]
    response = ingest_events(client, session_id, token_for("owner-1"), events)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_non_member_cannot_ingest_events() -> None:
    """Users without membership must receive 403."""

    client = build_test_client()
    session_id = create_session(client)
    response = ingest_events(
        client, session_id, token_for("stranger-1"), [sample_event(session_id)]
    )
    assert response.status_code == 403


def test_student_correction_updates_user_confirmed() -> None:
    """A student may confirm or deny a previously ingested event."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_events(client, session_id, token_for("owner-1"), [sample_event(session_id)])

    confirmation = client.post(
        f"/api/v1/sessions/{session_id}/events/event-1/confirmation",
        json={"user_confirmed": True},
        headers=auth_headers(token_for("owner-1")),
    )
    assert confirmation.status_code == 200
    assert confirmation.json()["user_confirmed"] is True
