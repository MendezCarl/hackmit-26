"""Small synthetic payload builders; no media, real identities, or private transcripts."""

from typing import Any

BASE = "/api/v1/sessions/demo-session"


def authorization(actor: str = "student-1") -> dict[str, str]:
    """Return a public demo-only credential header."""
    return {"Authorization": f"Bearer demo-{actor}"}


def signal(event_id: str = "event-1", **changes: Any) -> dict[str, Any]:
    """Build a valid synthetic event, optionally replacing fields for negative tests."""
    return {
        "event_id": event_id,
        "lecture_id": "demo-lecture",
        "event_type": "possible_missed_window",
        "start_ms": 5000,
        "end_ms": 12_000,
        "signals": ["face_absent"],
        "confidence": 0.8,
        "user_confirmed": None,
        **changes,
    }


def chunk(chunk_id: str = "chunk-1", **changes: Any) -> dict[str, Any]:
    """Build a timestamped, explicitly synthetic teaching passage."""
    return {
        "chunk_id": chunk_id,
        "lecture_id": "demo-lecture",
        "start_ms": 0,
        "end_ms": 15_000,
        "text": "Synthetic lecture: a stack follows last-in, first-out ordering.",
        "source": "local_transcription",
        "is_final": True,
        "revision": 1,
        **changes,
    }
