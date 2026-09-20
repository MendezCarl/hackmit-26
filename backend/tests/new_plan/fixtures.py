"""Synthetic fixtures with explicit lecture-relative time; no external services."""

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

SETTINGS = Settings(app_env="test", context_padding_ms=0)


def actor(user="owner", role="student"):
    """Return a synthetic actor in course c."""
    return AuthenticatedActor(user_id=user, role=role, course_id="c")


def headers(user="owner", role="student"):
    """Sign synthetic credentials with test-only settings."""
    return {
        "Authorization": "Bearer " + issue_access_token(SETTINGS, actor(user, role))
    }


def setup(generator=None):
    """Create a session, final transcript and five consenting test participants."""
    client = TestClient(create_app(SETTINGS, recovery_generator=generator))
    response = client.post(
        "/api/v1/sessions",
        headers=headers(),
        json={
            "lecture_id": "l",
            "course_id": "c",
            "title": "Synthetic stacks",
            "mode": "in_person",
        },
    )
    assert response.status_code == 201, response.text
    session = response.json()["session_id"]
    base = f"/api/v1/sessions/{session}"
    chunk = {
        "chunk_id": "chunk1",
        "session_id": session,
        "start_ms": 0,
        "end_ms": 60_000,
        "text": "A stack uses last-in, first-out ordering.",
        "source": "local_transcription",
        "is_final": True,
        "revision": 1,
    }
    response = client.post(
        base + "/transcript-chunks/batch",
        headers=headers(),
        json={"lecture_id": "l", "chunks": [chunk]},
    )
    assert response.status_code < 300, response.text
    for user in ["owner", "s2", "s3", "s4", "s5"]:
        assert (
            client.post(base + "/participants", headers=headers(user)).status_code < 300
        )
    return client, session, base


def coverage(
    client,
    base,
    user="owner",
    available=True,
    coverage_id="coverage1",
    start=0,
    end=60_000,
):
    """Submit one bounded observation availability record."""
    return client.post(
        base + "/coverage/batch",
        headers=headers(user),
        json={
            "records": [
                {
                    "coverage_id": coverage_id,
                    "start_ms": start,
                    "end_ms": end,
                    "is_available": available,
                }
            ]
        },
    )


def cover_all(client, base):
    """Provide actual synthetic coverage, separate from event presence."""
    for user in ["owner", "s2", "s3", "s4", "s5"]:
        assert coverage(client, base, user).status_code == 200


def signal(
    client,
    session,
    base,
    user="owner",
    kind="possible_missed_window",
    event_id="e1",
    signals=None,
):
    """Submit a coarse synthetic signal under the authenticated user."""
    return client.post(
        base + "/events/batch",
        headers=headers(user),
        json={
            "lecture_id": "l",
            "events": [
                {
                    "event_id": event_id,
                    "session_id": session,
                    "event_type": kind,
                    "start_ms": 0,
                    "end_ms": 30_000,
                    "signals": signals or [kind],
                    "confidence": 0.8,
                }
            ],
        },
    )


def end(client, base):
    """End session using the existing lifecycle endpoint."""
    response = client.post(base + "/end", headers=headers())
    assert response.status_code < 300, response.text


def report(client, base):
    """Read as the authorized course professor."""
    return client.get(base + "/professor-metrics", headers=headers("prof", "professor"))
