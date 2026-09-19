"""Ingestion, revisions, ownership, clock alignment and privacy regressions."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from .factories import BASE, authorization, chunk, signal


def test_signal_retry_conflict_and_private_timeline(client: TestClient) -> None:
    """Retries are no-ops, conflicting IDs fail, and other actors cannot see events."""
    payload = {"events": [signal()]}
    first = client.post(f"{BASE}/events/batch", headers=authorization(), json=payload)
    assert first.status_code == 200
    assert first.json() == {"accepted": 1, "duplicates": 0, "revision": 1}
    retry = client.post(f"{BASE}/signals", headers=authorization(), json=payload)
    assert retry.json() == {"accepted": 0, "duplicates": 1, "revision": 1}
    assert (
        client.post(
            f"{BASE}/signals",
            headers=authorization(),
            json={"events": [signal(confidence=0.9)]},
        ).status_code
        == 409
    )
    own = client.get(
        f"{BASE}/timeline?start_ms=0&end_ms=15000", headers=authorization()
    ).json()
    assert own["missed_windows"][0]["source_event_ids"] == ["event-1"]
    other = client.get(
        f"{BASE}/timeline?start_ms=0&end_ms=15000", headers=authorization("student-2")
    ).json()
    assert other["events"] == other["missed_windows"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"raw_audio": "PRIVATE-MARKER"},
        {"webcam_frame": "PRIVATE-MARKER"},
        {"participant_key": "student-2"},
        {"start_ms": -1},
        {"end_ms": 5000},
        {"start_ms": 5.5},
        {"confidence": 1.1},
        {"confidence": "NaN"},
        {"signals": ["inattentive"]},
        {"event_type": "attention_score"},
    ],
)
def test_invalid_signal_never_echoes_input(
    client: TestClient, changes: dict[str, Any]
) -> None:
    """Reject malformed or identity/media-bearing signals without leaking supplied values."""
    response = client.post(
        f"{BASE}/signals", headers=authorization(), json={"events": [signal(**changes)]}
    )
    assert response.status_code == 422
    assert "PRIVATE-MARKER" not in response.text
    assert response.json()["error"]["code"] == "invalid_request"


def test_batch_is_atomic_and_lecture_bound(client: TestClient) -> None:
    """A later conflicting event or wrong lecture must not partially persist a batch."""
    response = client.post(
        f"{BASE}/signals",
        headers=authorization(),
        json={"events": [signal(), signal(confidence=0.2)]},
    )
    assert response.status_code == 409
    assert (
        client.get(
            f"{BASE}/timeline?start_ms=0&end_ms=15000", headers=authorization()
        ).json()["events"]
        == []
    )
    assert (
        client.post(
            f"{BASE}/signals",
            headers=authorization(),
            json={"events": [signal(lecture_id="other")]},
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{BASE}/signals",
            headers=authorization(),
            json={"events": [signal(end_ms=60001)]},
        ).status_code
        == 400
    )


def test_confirmation_is_owner_only_and_survives_retries(client: TestClient) -> None:
    """Corrections remove candidate windows and original request retries cannot undo them."""
    client.post(f"{BASE}/signals", headers=authorization(), json={"events": [signal()]})
    assert (
        client.patch(
            f"{BASE}/events/event-1",
            headers=authorization("student-2"),
            json={"user_confirmed": False},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"{BASE}/events/event-1",
            headers=authorization(),
            json={"user_confirmed": False},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{BASE}/signals", headers=authorization(), json={"events": [signal()]}
        ).json()["duplicates"]
        == 1
    )
    result = client.get(
        f"{BASE}/timeline?start_ms=0&end_ms=15000", headers=authorization()
    ).json()
    assert result["missed_windows"] == []
    assert result["events"][0]["user_confirmed"] is False


def test_auth_consent_and_invalid_session(client: TestClient) -> None:
    """Require authentication, producer roles and session binding."""
    assert (
        client.post(f"{BASE}/signals", json={"events": [signal()]}).status_code == 401
    )
    assert (
        client.post(
            f"{BASE}/signals",
            headers=authorization("professor"),
            json={"events": [signal()]},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{BASE}/transcript-chunks/batch",
            headers=authorization(),
            json={"chunks": [chunk()]},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/sessions/other/timeline?start_ms=0&end_ms=100",
            headers=authorization(),
        ).status_code
        == 404
    )


def test_transcript_revisions_finality_and_atomicity(client: TestClient) -> None:
    """Out-of-order chunks sort correctly and only increasing revisions replace text."""
    path = f"{BASE}/transcript-chunks/batch"
    initial = {
        "chunks": [
            chunk(is_final=False),
            chunk("chunk-2", start_ms=15000, end_ms=30000),
        ]
    }
    assert (
        client.post(path, headers=authorization("transcriber"), json=initial).json()[
            "accepted"
        ]
        == 2
    )
    assert (
        client.get(
            f"{BASE}/transcript?start_ms=0&end_ms=15000", headers=authorization()
        ).status_code
        == 409
    )
    final = chunk(revision=2)
    assert (
        client.post(
            path, headers=authorization("transcriber"), json={"chunks": [final]}
        ).status_code
        == 200
    )
    assert (
        client.post(
            path, headers=authorization("transcriber"), json={"chunks": [final]}
        ).json()["duplicates"]
        == 1
    )
    invalid_batch = {
        "chunks": [chunk("chunk-3", start_ms=30000, end_ms=40000), chunk(revision=1)]
    }
    assert (
        client.post(
            path, headers=authorization("transcriber"), json=invalid_batch
        ).status_code
        == 409
    )
    assert (
        client.post(
            path,
            headers=authorization("transcriber"),
            json={"chunks": [chunk(revision=3, is_final=False)]},
        ).status_code
        == 409
    )
    context = client.get(
        f"{BASE}/transcript?start_ms=0&end_ms=30000", headers=authorization()
    ).json()
    assert [item["chunk_id"] for item in context["chunks"]] == ["chunk-1", "chunk-2"]
    assert context["transcript_revision"] == 2


def test_half_open_boundaries_and_padding(client: TestClient) -> None:
    """Adjacent chunks do not overlap; padding is clamped without changing source times."""
    client.post(
        f"{BASE}/transcript-chunks/batch",
        headers=authorization("transcriber"),
        json={"chunks": [chunk(), chunk("chunk-2", start_ms=15000, end_ms=30000)]},
    )
    context = client.get(
        f"{BASE}/transcript?start_ms=15000&end_ms=20000", headers=authorization()
    ).json()
    assert [item["chunk_id"] for item in context["chunks"]] == ["chunk-2"]
    padded = client.get(
        f"{BASE}/transcript?start_ms=0&end_ms=1000&padding_ms=5000",
        headers=authorization(),
    ).json()
    assert padded["effective_interval"] == {"start_ms": 0, "end_ms": 6000}
    assert padded["chunks"][0]["end_ms"] == 15000
    assert (
        client.get(
            f"{BASE}/timeline?start_ms=20&end_ms=10", headers=authorization()
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"audio": "PRIVATE-MARKER"},
        {"text": "data:audio/wav;base64,PRIVATE-MARKER"},
        {"text": "\u0000PRIVATE-MARKER"},
        {"text": "x" * 2001},
    ],
)
def test_transcript_media_and_size_rejected(
    client: TestClient, changes: dict[str, Any]
) -> None:
    """Typed text ingestion rejects media fields, data URLs and oversized text."""
    response = client.post(
        f"{BASE}/transcript-chunks/batch",
        headers=authorization("transcriber"),
        json={"chunks": [chunk(**changes)]},
    )
    assert response.status_code == 422
    assert "PRIVATE-MARKER" not in response.text


def test_http_body_limit_and_binary_rejection(client: TestClient) -> None:
    """Enforce request limits independently of payload schema validation."""
    assert (
        client.post(
            f"{BASE}/signals",
            headers={**authorization(), "content-type": "application/json"},
            content=b"x" * 256001,
        ).status_code
        == 413
    )
    assert (
        client.post(
            f"{BASE}/signals",
            headers={**authorization(), "content-type": "audio/wav"},
            content=b"RIFF",
        ).status_code
        == 415
    )


def test_simulated_zoom_uses_trusted_clock(client: TestClient) -> None:
    """Normalize synthetic epoch timestamps and reject packets before session origin."""
    origin = 1_720_000_000_000
    packet = {
        "chunk_id": "zoom-1",
        "start_epoch_ms": origin + 1000,
        "end_epoch_ms": origin + 7000,
        "text": "Synthetic Zoom transcript.",
        "is_final": True,
    }
    path = f"{BASE}/zoom/simulated-transcript-chunks"
    assert (
        client.post(
            path, headers=authorization("transcriber"), json={"chunks": [packet]}
        ).status_code
        == 200
    )
    result = client.get(
        f"{BASE}/transcript?start_ms=1000&end_ms=7000", headers=authorization()
    ).json()
    assert result["chunks"][0]["start_ms"] == 1000
    packet["start_epoch_ms"] = origin - 1
    assert (
        client.post(
            path, headers=authorization("transcriber"), json={"chunks": [packet]}
        ).status_code
        == 400
    )
