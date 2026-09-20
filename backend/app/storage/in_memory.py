"""In-memory storage used while Mongo/Redis integrations remain faked.

MongoDB and Redis are the target persistence layer. Until the real
integration gate is met, this module provides the injected connections the
feature repositories build on. Domain models stay independent of any
document format.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass, field

from app.contracts.models import (
    ConsentSettings,
    CostMetrics,
    Course,
    CourseEnrollment,
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

    users: MutableMapping[str, UserRecord] = field(default_factory=dict)
    courses: MutableMapping[str, Course] = field(default_factory=dict)
    lectures: MutableMapping[str, Lecture] = field(default_factory=dict)
    # enrollment_id -> student course membership.
    enrollments: MutableMapping[str, CourseEnrollment] = field(default_factory=dict)
    sessions: MutableMapping[str, LectureSession] = field(default_factory=dict)
    session_join_codes: MutableMapping[str, str] = field(default_factory=dict)
    participants: MutableMapping[str, dict[str, ParticipantRecord]] = field(
        default_factory=dict
    )
    events: MutableMapping[str, list[EventRecord]] = field(default_factory=dict)
    transcript_chunks: MutableMapping[str, list[TranscriptChunk]] = field(
        default_factory=dict
    )
    recovery_jobs: MutableMapping[str, RecoveryJob] = field(default_factory=dict)
    recovery_cards: MutableMapping[str, CardRecord] = field(default_factory=dict)
    # Authorization-scoped cache key -> card_id.
    recovery_cache: MutableMapping[str, str] = field(default_factory=dict)
    # Scoped idempotency key (user|session|key) -> job_id.
    recovery_idempotency: MutableMapping[str, str] = field(default_factory=dict)
    cost_ledger: list[CostMetrics] = field(default_factory=list)
