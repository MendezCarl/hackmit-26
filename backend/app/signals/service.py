"""Signals feature: coarse missed-content signal ingestion and correction.

The server accepts only coarse, timestamped, derived events. Raw webcam
frames, continuous raw audio, screenshots, and recordings are never accepted
by this or any other endpoint. The missed-window rule threshold is explicitly
configurable and testable; no attention score is invented.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.auth.access import (
    SESSION_ROLE_COURSE_PROFESSOR,
    SessionAccess,
)
from app.auth.tokens import AuthenticatedActor
from app.config import Settings
from app.contracts.models import (
    ConfirmEventRequest,
    IngestEventsRequest,
    SignalEvent,
)
from app.core.clock import utc_now_iso
from app.core.errors import AppError, ErrorCode
from app.storage.in_memory import EventRecord, InMemoryStore, ParticipantRecord
from app.ws.publisher import EventPublisher

SIGNAL_EVENT_INGESTED = "signal_event.ingested"
SIGNAL_EVENT_CONFIRMED = "signal_event.confirmed"
PARTICIPANT_JOINED = "participant.joined"


class EventBatchResponse(BaseModel):
    """Response summarizing one accepted signal-event batch."""

    session_id: str = Field(description="Session the batch was ingested into.")
    accepted_event_ids: list[str] = Field(description="Newly accepted event identifiers.")
    recovery_eligible_event_ids: list[str] = Field(
        description="Event ids passing the configurable missed-window rule."
    )


class ParticipantResponse(BaseModel):
    """Response for one participant registration."""

    session_id: str = Field(description="Session joined.")
    user_id: str = Field(description="Authenticated user who joined.")
    participant_count: int = Field(ge=1, description="Registered participant count.")


class SignalService:
    """Ingestion, participant consent, correction, and the missed-window rule."""

    def __init__(
        self,
        store: InMemoryStore,
        settings: Settings,
        session_access: SessionAccess,
        event_publisher: EventPublisher,
    ) -> None:
        """Bind the service to shared storage, settings, and publishing.

        Args:
            store: Injected storage connections.
            settings: Application settings, including the missed-window rule.
            session_access: Shared membership resolver.
            event_publisher: Publisher for session-scoped typed events.
        """

        self._store = store
        self._settings = settings
        self._session_access = session_access
        self._publisher = event_publisher

    def is_recovery_eligible(self, event: SignalEvent) -> bool:
        """Apply the configurable temporal missed-window rule.

        Args:
            event: One coarse signal event.

        Returns:
            True when the event's duration meets the configured threshold.
        """

        return (event.end_ms - event.start_ms) >= self._settings.min_missed_window_ms


    def ingest_batch(
        self,
        actor: AuthenticatedActor,
        session_id: str,
        request: IngestEventsRequest,
    ) -> EventBatchResponse:
        """Validate and store one batch of coarse signal events.

        Args:
            actor: Authenticated owner or participant submitting the batch.
            session_id: Session the events belong to.
            request: Validated batch payload.

        Returns:
            Response listing accepted and recovery-eligible event ids.

        Raises:
            AppError: ``forbidden``, ``validation_failed``,
                ``payload_too_large``, or ``duplicate`` for rejected batches.
        """

        membership = self._session_access.resolve_membership(actor, session_id)
        if membership.session_role == SESSION_ROLE_COURSE_PROFESSOR:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Professors cannot submit student signal events.",
            )

        session = self._store.sessions[session_id]
        if request.lecture_id != session.lecture_id:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "lecture_id does not match the session's lecture.",
                details={
                    "session_lecture_id": session.lecture_id,
                    "request_lecture_id": request.lecture_id,
                },
            )

        if len(request.events) > self._settings.max_batch_events:
            raise AppError(
                ErrorCode.PAYLOAD_TOO_LARGE,
                "Event batch exceeds the configured maximum.",
                details={"max_batch_events": self._settings.max_batch_events},
            )

        records = self._store.events.setdefault(session_id, [])
        existing_ids = {record.event.event_id for record in records}
        within_batch: set[str] = set()
        accepted: list[str] = []
        for event in request.events:
            if event.session_id != session_id:
                raise AppError(
                    ErrorCode.VALIDATION_FAILED,
                    "Every event's session_id must match the path session_id.",
                )
            if event.event_id in existing_ids or event.event_id in within_batch:
                raise AppError(
                    ErrorCode.DUPLICATE,
                    "Duplicate signal event id was rejected.",
                    details={"duplicate_event_id": event.event_id},
                )
            within_batch.add(event.event_id)
            records.append(EventRecord(event=event, submitted_by=actor.user_id))
            accepted.append(event.event_id)

        self._publisher.publish(
            self._publisher.build_envelope(
                session_id,
                SIGNAL_EVENT_INGESTED,
                {"accepted_event_ids": accepted},
            )
        )

        eligible = [
            record.event.event_id
            for record in records
            if self.is_recovery_eligible(record.event)
        ]
        return EventBatchResponse(
            session_id=session_id,
            accepted_event_ids=accepted,
            recovery_eligible_event_ids=eligible,
        )

    def register_participant(
        self, actor: AuthenticatedActor, session_id: str
    ) -> ParticipantResponse:
        """Register the authenticated user as an opted-in participant.

        Registration is the act of joining: it requires only that the session
        exists, because membership resolution would otherwise be circular.
        Re-registering is idempotent and returns the current count.

        Args:
            actor: Authenticated user joining the session.
            session_id: Session to join.

        Returns:
            Response with the participant count for the session.

        Raises:
            AppError: ``not_found`` when the session does not exist.
        """

        if session_id not in self._store.sessions:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Lecture session was not found.",
                details={"session_id": session_id},
            )
        participants = self._store.participants.setdefault(session_id, {})
        if actor.user_id not in participants:
            participants[actor.user_id] = ParticipantRecord(
                user_id=actor.user_id,
                is_opted_in=True,
                joined_at=utc_now_iso(),
            )
            self._publisher.publish(
                self._publisher.build_envelope(
                    session_id,
                    PARTICIPANT_JOINED,
                    {"participant_count": len(participants)},
                )
            )
        return ParticipantResponse(
            session_id=session_id,
            user_id=actor.user_id,
            participant_count=len(participants),
        )

    def confirm_event(
        self,
        actor: AuthenticatedActor,
        session_id: str,
        event_id: str,
        request: ConfirmEventRequest,
    ) -> SignalEvent:
        """Apply a student correction to one previously ingested event.

        Args:
            actor: Authenticated owner or participant making the correction.
            session_id: Session the event belongs to.
            event_id: Event to correct.
            request: Confirmed or denied missed content.

        Returns:
            The updated signal event.

        Raises:
            AppError: ``forbidden`` for professors and ``not_found`` for
                unknown events.
        """

        membership = self._session_access.resolve_membership(actor, session_id)
        if membership.session_role == SESSION_ROLE_COURSE_PROFESSOR:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Professors cannot correct student signal events.",
            )

        for record in self._store.events.get(session_id, []):
            if record.event.event_id == event_id:
                record.event.user_confirmed = request.user_confirmed
                self._publisher.publish(
                    self._publisher.build_envelope(
                        session_id,
                        SIGNAL_EVENT_CONFIRMED,
                        {"event_id": event_id, "user_confirmed": request.user_confirmed},
                    )
                )
                return record.event

        raise AppError(
            ErrorCode.NOT_FOUND,
            "Signal event was not found in this session.",
            details={"event_id": event_id},
        )

    def list_session_event_ids(self, session_id: str) -> list[str]:
        """Return every event id ingested for the session.

        Args:
            session_id: Session whose event ids are needed.

        Returns:
            All known event ids for the session.
        """

        return [
            record.event.event_id
            for record in self._store.events.get(session_id, [])
        ]

    def list_session_events(self, session_id: str) -> list[EventRecord]:
        """Return stored event records; attribution stays server-side.

        Args:
            session_id: Session whose records are needed.

        Returns:
            Event records with server-side attribution (never exposed via API).
        """

        return list(self._store.events.get(session_id, []))

    def get_participants(self, session_id: str) -> dict[str, ParticipantRecord]:
        """Return consent records for the session's participants.

        Args:
            session_id: Session to inspect.

        Returns:
            Mapping of user id to participant record.
        """

        return self._store.participants.get(session_id, {})
