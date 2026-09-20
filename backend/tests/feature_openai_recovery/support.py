"""Synthetic host fixtures for isolated feature services; no external dependencies."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.auth.access import StoreSessionAccess
from app.auth.tokens import AuthenticatedActor
from app.config import Settings
from app.contracts.models import (
    LectureSession,
    SessionMode,
    SessionStatus,
    TranscriptChunk,
    TranscriptSource,
)
from app.learning.state import LearningState
from app.storage.in_memory import InMemoryStore, ParticipantRecord


def fixture():
    """Build a trusted synthetic lecture host with five consenting participants."""
    store = InMemoryStore()
    session = LectureSession(
        session_id="s",
        lecture_id="l",
        owner_id="student1",
        course_id="c",
        title="Synthetic stacks",
        mode=SessionMode.IN_PERSON,
        status=SessionStatus.ACTIVE,
        started_at="2026-09-19T00:00:00Z",
        session_clock_origin="2026-09-19T00:00:00Z",
    )
    store.sessions["s"] = session
    store.participants["s"] = {
        f"student{i}": ParticipantRecord(user_id=f"student{i}") for i in range(1, 6)
    }
    store.transcript_chunks["s"] = [
        TranscriptChunk(
            chunk_id="chunk",
            session_id="s",
            start_ms=0,
            end_ms=30_000,
            text="A stack follows last-in, first-out ordering.",
            source=TranscriptSource.LOCAL_TRANSCRIPTION,
        )
    ]
    return store, LearningState(), StoreSessionAccess(store), Settings(app_env="test")


def actor(user="student1", role="student"):
    """Return a synthetic verified identity for the test's trusted host boundary."""
    return AuthenticatedActor(user_id=user, role=role, course_id="c")
