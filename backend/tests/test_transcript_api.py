"""Transcript ingestion, revisions, finality, and timeline-read tests."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

SETTINGS = Settings(app_env="test")
LECTURE_ID = "lecture-1"


def token_for(user_id: str) -> str:
    """Mint a synthetic student token."""

    return issue_access_token(
        SETTINGS, AuthenticatedActor(user_id=user_id, role="student")
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
            "course_id": "course-1",
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers=auth_headers(token_for("owner-1")),
    ).json()["session_id"]


def ingest_transcript(client: TestClient, session_id: str, chunks: list[dict]):
    """Submit a transcript batch."""

    return client.post(
        f"/api/v1/sessions/{session_id}/transcript/batch",
        json={"lecture_id": LECTURE_ID, "chunks": chunks},
        headers=auth_headers(token_for("owner-1")),
    )


def sample_chunk(session_id: str, chunk_id: str = "chunk-1", **overrides) -> dict:
    """Build one valid final transcript chunk."""

    chunk = {
        "chunk_id": chunk_id,
        "session_id": session_id,
        "start_ms": 930_000,
        "end_ms": 960_000,
        "text": "Attention scores weigh how each token influences each output.",
        "speaker_label": "instructor",
        "source": "local_transcription",
        "is_final": True,
        "revision": 1,
    }
    chunk.update(overrides)
    return chunk


def test_ingest_transcript_returns_revision() -> None:
    """Valid batches list accepted chunk ids and the timeline revision."""

    client = build_test_client()
    session_id = create_session(client)
    response = ingest_transcript(client, session_id, [sample_chunk(session_id)])
    assert response.status_code == 202
    body = response.json()
    assert body["accepted_chunk_ids"] == ["chunk-1"]
    assert body["transcript_revision"] == 1


def test_higher_revision_supersedes_stored_chunk() -> None:
    """A higher revision must replace the stored chunk as a correction."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(client, session_id, [sample_chunk(session_id)])

    corrected = sample_chunk(
        session_id, revision=2, text="Corrected transcript text for the interval."
    )
    response = ingest_transcript(client, session_id, [corrected])
    assert response.status_code == 202
    body = response.json()
    assert body["superseded_chunk_ids"] == ["chunk-1"]
    assert body["transcript_revision"] == 2

    window = client.get(
        f"/api/v1/sessions/{session_id}/transcript",
        params={"start_ms": 0, "end_ms": 1_000_000},
        headers=auth_headers(token_for("owner-1")),
    )
    assert window.json()["chunks"][0]["text"].startswith("Corrected")


def test_equal_revision_is_rejected_as_duplicate() -> None:
    """Re-submitting the same revision must fail with 409."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(client, session_id, [sample_chunk(session_id)])
    response = ingest_transcript(
        client, session_id, [sample_chunk(session_id, text="Unchanged revision")]
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate"


def test_provisional_chunks_are_excluded_from_reads() -> None:
    """Provisional chunks must be stored but never served in windows."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(
        client,
        session_id,
        [sample_chunk(session_id, chunk_id="final-1", is_final=True)],
    )
    ingest_transcript(
        client,
        session_id,
        [sample_chunk(session_id, chunk_id="provisional-1", is_final=False)],
    )
    window = client.get(
        f"/api/v1/sessions/{session_id}/transcript",
        params={"start_ms": 0, "end_ms": 1_000_000},
        headers=auth_headers(token_for("owner-1")),
    )
    served_ids = [chunk["chunk_id"] for chunk in window.json()["chunks"]]
    assert served_ids == ["final-1"]


def test_oversized_chunk_text_is_rejected() -> None:
    """Chunk text above the configured maximum must fail with 413."""

    client = build_test_client()
    session_id = create_session(client)
    oversized = sample_chunk(
        session_id, text="x" * (SETTINGS.max_transcript_text_chars + 1)
    )
    response = ingest_transcript(client, session_id, [oversized])
    assert response.status_code == 413


def test_window_read_uses_half_open_overlap() -> None:
    """Only chunks overlapping the half-open interval are returned."""

    client = build_test_client()
    session_id = create_session(client)
    ingest_transcript(
        client,
        session_id,
        [
            sample_chunk(session_id, chunk_id="a", start_ms=0, end_ms=10_000),
            sample_chunk(session_id, chunk_id="b", start_ms=30_000, end_ms=60_000),
        ],
    )
    window = client.get(
        f"/api/v1/sessions/{session_id}/transcript",
        params={"start_ms": 10_000, "end_ms": 30_001},
        headers=auth_headers(token_for("owner-1")),
    )
    # Chunk a ends at exactly 10_000 ms, so [10k, 30_001) does not overlap it;
    # chunk b starts at 30_000 ms and overlaps the half-open interval.
    served_ids = [chunk["chunk_id"] for chunk in window.json()["chunks"]]
    assert served_ids == ["b"]


def test_non_member_cannot_ingest_transcript() -> None:
    """Users without membership must receive 403."""

    client = build_test_client()
    session_id = create_session(client)
    response = client.post(
        f"/api/v1/sessions/{session_id}/transcript/batch",
        json={"lecture_id": LECTURE_ID, "chunks": [sample_chunk(session_id)]},
        headers=auth_headers(token_for("stranger-1")),
    )
    assert response.status_code == 403
