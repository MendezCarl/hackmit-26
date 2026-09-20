"""In-memory storage used while Mongo/Redis integrations remain faked.

MongoDB and Redis are the target persistence layer. Until the real
integration gate is met, this module provides the injected connections the
feature repositories build on. Domain models stay independent of any
document format.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.contracts.models import (
    ConsentSettings,
    CostMetrics,
    Course,
    Lecture,
    LectureSession,
    RecoveryCard,
    RecoveryJob,
    SignalEvent,
    TranscriptChunk,
)


@dataclass
class UserRecord:
    """Server-side account record; password hashes are never exposed."""

    user_id: str
    email: str
    password_hash: str
    role: str
    display_name: str
    created_at: str
    consent: ConsentSettings


@dataclass
class ParticipantRecord:
    """Server-side consent record for one session participant."""

    user_id: str
    is_opted_in: bool = True
    joined_at: str = ""


@dataclass
class EventRecord:
    """An ingested signal event with server-side attribution."""

    event: SignalEvent
    submitted_by: str


@dataclass
class CardRecord:
    """A stored recovery card with the user it belongs to."""

    card: RecoveryCard
    owner_user_id: str


@dataclass
class InMemoryStore:
    """Process-local storage containers shared by feature repositories."""

    users: dict[str, UserRecord] = field(default_factory=dict)
    courses: dict[str, Course] = field(default_factory=dict)
    lectures: dict[str, Lecture] = field(default_factory=dict)
    sessions: dict[str, LectureSession] = field(default_factory=dict)
    participants: dict[str, dict[str, ParticipantRecord]] = field(default_factory=dict)
    events: dict[str, list[EventRecord]] = field(default_factory=dict)
    transcript_chunks: dict[str, list[TranscriptChunk]] = field(default_factory=dict)
    recovery_jobs: dict[str, RecoveryJob] = field(default_factory=dict)
    recovery_cards: dict[str, CardRecord] = field(default_factory=dict)
    # Authorization-scoped cache key -> card_id.
    recovery_cache: dict[str, str] = field(default_factory=dict)
    # Scoped idempotency key (user|session|key) -> job_id.
    recovery_idempotency: dict[str, str] = field(default_factory=dict)
    cost_ledger: list[CostMetrics] = field(default_factory=list)
