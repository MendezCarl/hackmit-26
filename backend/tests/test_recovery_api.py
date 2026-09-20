"""Recovery job, card grounding, cache, provider-failure, and cost tests."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.auth.tokens import AuthenticatedActor, issue_access_token  # noqa: E402
from app.config import Settings  # noqa: E402
from app.core.errors import AppError, ErrorCode  # noqa: E402
from app.main import create_app  # noqa: E402
from app.recovery.generator import (  # noqa: E402
    DeterministicRecoveryGenerator,
)

SETTINGS = Settings(app_env="test")
LECTURE_ID = "lecture-1"
COURSE_ID = "course-1"


class FailingRecoveryGenerator(DeterministicRecoveryGenerator):
    """Test double simulating one typed provider failure."""

    def __init__(self, error_code: ErrorCode) -> None:
        """Configure the failure the generator raises on every call.

        Args:
            error_code: Typed error code raised instead of generating.
        """

        self._error_code = error_code

    def generate(self, session, window):  # noqa: ANN001 - test double
        """Raise the configured typed provider failure."""

        raise AppError(self._error_code, "Synthetic provider failure for tests.")


class MalformedRecoveryGenerator(DeterministicRecoveryGenerator):
    """Test double simulating invalid provider output."""

    def generate(self, session, window):  # noqa: ANN001 - test double
        """Return output missing every required grounding field."""

        raise ValueError("Provider returned an ungrounded, malformed card.")


def token_for(user_id: str, role: str = "student", course_id: str | None = None) -> str:
    """Mint a synthetic token."""

    return issue_access_token(
        SETTINGS,
        AuthenticatedActor(user_id=user_id, role=role, course_id=course_id),
    )


def auth_headers(token: str) -> dict[str, str]:
    """Build an authorization header."""

    return {"Authorization": f"Bearer {token}"}


def build_test_client(generator=None) -> TestClient:
    """Create an isolated client, optionally with a failing generator."""

    return TestClient(create_app(SETTINGS, recovery_generator=generator))


def create_session(client: TestClient, lecture_id: str = LECTURE_ID) -> str:
    """Create a synthetic session and return its id."""

    return client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": lecture_id,
            "course_id": COURSE_ID,
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers=auth_headers(token_for("owner-1")),
    ).json()["session_id"]


def ingest_transcript(
    client: TestClient, session_id: str, revision: int = 1
) -> None:
    """Ingest synthetic transcript chunks around the missed interval."""

    chunks = [
        {
            "chunk_id": f"chunk-{index}-rev{revision}",
            "session_id": session_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
            "source": "local_transcription",
            "is_final": is_final,
            "revision": revision,
        }
        for index, (start_ms, end_ms, text, is_final) in enumerate(
            [
                (
                    900_000,
                    960_000,
                    "We compute attention scores with queries and keys.",
                    True,
                ),
                (
                    960_000,
                    1_020_000,
                    "Softmax turns the scores into weights that sum to one.",
                    True,
                ),
            ],
            start=1,
        )
    ]
    response = client.post(
        f"/api/v1/sessions/{session_id}/transcript/batch",
        json={"lecture_id": LECTURE_ID, "chunks": chunks},
        headers=auth_headers(token_for("owner-1")),
    )
    assert response.status_code == 202


def ingest_event(client: TestClient, session_id: str, event_id: str) -> None:
    """Ingest one missed-window event as the owner."""

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
        headers=auth_headers(token_for("owner-1")),
    )
    assert response.status_code == 202


def request_recovery(client: TestClient, session_id: str, token: str, body: dict):
    """Submit one recovery request."""

    return client.post(
        f"/api/v1/sessions/{session_id}/recovery/jobs",
        json=body,
        headers=auth_headers(token),
    )


def recovery_body(
    start_ms: int = 931_200, end_ms: int = 978_700, source_event_ids: list | None = None
) -> dict:
    """Build one valid recovery request body."""

    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "source_event_ids": source_event_ids or [],
    }


def test_recovery_returns_grounded_card_with_transcript_references() -> None:
    """A valid request must complete with a card grounded in chunk ids."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(client, session_id)
    ingest_event(client, session_id, "event-1")

    job = request_recovery(
        client,
        session_id,
        token_for("owner-1"),
        recovery_body(source_event_ids=["event-1"]),
    )
    assert job.status_code == 202
    job_body = job.json()
    assert job_body["status"] == "completed"
    assert job_body["cache_status"] == "miss"

    card = client.get(
        f"/api/v1/sessions/{session_id}/recovery/cards/{job_body['card_id']}",
        headers=auth_headers(token_for("owner-1")),
    )
    assert card.status_code == 200
    card_body = card.json()
    assert card_body["source_event_ids"] == ["event-1"]
    assert card_body["model_metadata"]["data_label"] == "synthetic"
    assert card_body["model_metadata"]["provider_mode"] == "mock"
    source_chunk_ids = {
        timestamp["chunk_id"] for timestamp in card_body["source_timestamps"]
    }
    assert source_chunk_ids == {"chunk-1-rev1", "chunk-2-rev1"}


def test_repeated_request_reuses_cached_card() -> None:
    """A repeat request within the same scope must record a cache hit."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(client, session_id)

    first = request_recovery(
        client, session_id, token_for("owner-1"), recovery_body()
    ).json()
    second = request_recovery(
        client, session_id, token_for("owner-1"), recovery_body()
    ).json()

    assert first["cache_status"] == "miss"
    assert second["cache_status"] == "hit"
    assert second["card_id"] == first["card_id"]


def test_cache_is_isolated_per_user_scope() -> None:
    """Another user's request must not reuse or expose the first card."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(client, session_id)

    participant_token = token_for("participant-1")
    client.post(
        f"/api/v1/sessions/{session_id}/participants",
        headers=auth_headers(participant_token),
    )

    owner_card_id = request_recovery(
        client, session_id, token_for("owner-1"), recovery_body()
    ).json()["card_id"]
    participant_job = request_recovery(
        client, session_id, participant_token, recovery_body()
    ).json()

    assert participant_job["cache_status"] == "miss"
    assert participant_job["card_id"] != owner_card_id

    forbidden = client.get(
        f"/api/v1/sessions/{session_id}/recovery/cards/{owner_card_id}",
        headers=auth_headers(participant_token),
    )
    assert forbidden.status_code == 403


def test_transcript_correction_invalidates_cached_card() -> None:
    """A new transcript revision must force a fresh generation."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(client, session_id)

    first = request_recovery(
        client, session_id, token_for("owner-1"), recovery_body()
    ).json()
    ingest_transcript(client, session_id, revision=2)
    after_correction = request_recovery(
        client, session_id, token_for("owner-1"), recovery_body()
    ).json()

    assert after_correction["cache_status"] == "miss"
    assert after_correction["card_id"] != first["card_id"]


def test_missing_transcript_context_is_a_typed_failure() -> None:
    """Requests with no final transcript must fail with a typed reason."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_event(client, session_id, "event-1")

    job = request_recovery(client, session_id, token_for("owner-1"), recovery_body())
    assert job.status_code == 202
    job_body = job.json()
    assert job_body["status"] == "failed"
    assert job_body["failure"]["reason"] == "missing_transcript_context"
    assert job_body["card_id"] is None


def test_invalid_recovery_range_is_rejected() -> None:
    """Empty and reversed intervals must fail request validation."""

    client = build_test_client()
    session_id = create_session(client)
    response = request_recovery(
        client,
        session_id,
        token_for("owner-1"),
        recovery_body(start_ms=500_000, end_ms=500_000),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_unknown_source_event_is_rejected() -> None:
    """Source events must exist in the same session."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(client, session_id)
    response = request_recovery(
        client,
        session_id,
        token_for("owner-1"),
        recovery_body(source_event_ids=["event-not-in-session"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_professor_cannot_request_personal_recovery() -> None:
    """Professors must not generate personal recovery cards."""

    client = build_test_client()
    session_id = create_session(client)
    professor_token = token_for("prof-1", role="professor", course_id=COURSE_ID)
    response = request_recovery(client, session_id, professor_token, recovery_body())
    assert response.status_code == 403


def test_provider_timeout_is_a_typed_failure() -> None:
    """Provider timeouts must produce a typed, recoverable failure."""

    client = build_test_client(FailingRecoveryGenerator(ErrorCode.PROVIDER_TIMEOUT))
    session_id = create_session(client)
    ingest_transcript(client, session_id)
    job = request_recovery(client, session_id, token_for("owner-1"), recovery_body()).json()
    assert job["status"] == "failed"
    assert job["failure"]["reason"] == "provider_timeout"


def test_provider_refusal_is_a_typed_failure() -> None:
    """Provider refusals must produce a typed, recoverable failure."""

    client = build_test_client(FailingRecoveryGenerator(ErrorCode.PROVIDER_REFUSED))
    session_id = create_session(client)
    ingest_transcript(client, session_id)
    job = request_recovery(client, session_id, token_for("owner-1"), recovery_body()).json()
    assert job["status"] == "failed"
    assert job["failure"]["reason"] == "provider_refused"


def test_malformed_provider_output_is_a_typed_failure() -> None:
    """Unparseable provider output must produce a typed failure."""

    client = build_test_client(MalformedRecoveryGenerator())
    session_id = create_session(client)
    ingest_transcript(client, session_id)
    job = request_recovery(client, session_id, token_for("owner-1"), recovery_body()).json()
    assert job["status"] == "failed"
    assert job["failure"]["reason"] == "provider_malformed_output"


def test_cost_metrics_are_labeled_synthetic_and_owner_only() -> None:
    """Usage must be recorded and readable only by the session owner."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(client, session_id)
    request_recovery(client, session_id, token_for("owner-1"), recovery_body())
    request_recovery(client, session_id, token_for("owner-1"), recovery_body())

    metrics = client.get(
        f"/api/v1/sessions/{session_id}/cost/metrics",
        headers=auth_headers(token_for("owner-1")),
    )
    assert metrics.status_code == 200
    entries = metrics.json()
    assert len(entries) == 2
    assert {entry["cache_status"] for entry in entries} == {"miss", "hit"}
    assert all(entry["data_label"] == "synthetic" for entry in entries)

    stranger = client.get(
        f"/api/v1/sessions/{session_id}/cost/metrics",
        headers=auth_headers(token_for("stranger-1")),
    )
    assert stranger.status_code == 403