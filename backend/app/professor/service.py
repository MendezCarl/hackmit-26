"""Anonymous professor summaries with small-group suppression.

The denominator is explicit: unique participating, opted-in users per
released bucket — never events — and repeated submissions are
deduplicated per user. Aggregates are released only after the configured
minimum group-size threshold is met; otherwise the summary is suppressed.
The threshold default is a clearly labeled synthetic demo setting.
"""

from __future__ import annotations

from collections import Counter
from uuid import uuid4

from app.auth.access import (
    SESSION_ROLE_COURSE_PROFESSOR,
    SESSION_ROLE_OWNER,
    SessionAccess,
)
from app.auth.tokens import ROLE_PROFESSOR, AuthenticatedActor
from app.config import Settings
from app.contracts.models import (
    ProfessorSummary,
    SignalIntervalAggregate,
    TimelineBucket,
)
from app.core.clock import utc_now_iso
from app.core.errors import AppError, ErrorCode
from app.signals.service import SignalService
from app.storage.in_memory import EventRecord, InMemoryStore
from app.ws.publisher import EventPublisher

PROFESSOR_SUMMARY_READY = "professor_summary.ready"
TOP_INTERVAL_COUNT = 3
SUGGESTED_ACTIONS = (
    "Consider re-explaining the concepts in the densest signal interval.",
    "Share a short written recap or slides covering the requested moment.",
    (
        "Invite an anonymous clarification request so students can re-engage "
        "without being singled out."
    ),
)


class ProfessorService:
    """Aggregation of consenting participants into a threshold-safe report."""

    def __init__(
        self,
        store: InMemoryStore,
        settings: Settings,
        session_access: SessionAccess,
        signal_service: SignalService,
        event_publisher: EventPublisher,
    ) -> None:
        """Bind the service to shared dependencies.

        Args:
            store: Injected storage connections.
            settings: Application settings with the group-size threshold.
            session_access: Shared membership resolver.
            signal_service: Signals feature used for participant counts.
            event_publisher: Publisher for session-scoped typed events.
        """

        self._store = store
        self._settings = settings
        self._session_access = session_access
        self._signal_service = signal_service
        self._publisher = event_publisher

    def _count_participating_users(self, session_id: str) -> int:
        """Count unique opted-in participants who submitted at least one event.

        Args:
            session_id: Session to aggregate over.

        Returns:
            The deduplicated participating-user count.
        """

        participants = self._signal_service.get_participants(session_id)
        opted_in = {
            user_id for user_id, record in participants.items() if record.is_opted_in
        }
        submitters = {record.submitted_by for record in self._safe_records(session_id)}
        return len(opted_in & submitters)

    def _build_timeline_buckets(self, session_id: str) -> list[TimelineBucket]:
        """Aggregate events into fixed buckets of the configured width.

        Args:
            session_id: Session to aggregate over.

        Returns:
            Anonymous buckets covering the observed lecture span.
        """

        events = [record.event for record in self._safe_records(session_id)]
        if not events:
            return []
        window = self._settings.aggregation_window_ms
        latest_end = max(event.end_ms for event in events)
        bucket_count = max(1, -(-latest_end // window))
        buckets: list[TimelineBucket] = []
        for index in range(bucket_count):
            start = index * window
            end = start + window
            count = sum(
                1 for event in events if event.start_ms < end and start < event.end_ms
            )
            buckets.append(TimelineBucket(start_ms=start, end_ms=end, event_count=count))
        return buckets

    def _build_highest_signal_intervals(
        self, session_id: str
    ) -> list[SignalIntervalAggregate]:
        """Rank the densest observed intervals without exposing individuals.

        Args:
            session_id: Session to aggregate over.

        Returns:
            The top anonymous intervals by event count.
        """

        records = self._safe_records(session_id)
        intervals: Counter[tuple[int, int]] = Counter()
        event_types: dict[tuple[int, int], Counter[str]] = {}
        for record in records:
            key = (record.event.start_ms, record.event.end_ms)
            intervals[key] += 1
            event_types.setdefault(key, Counter())[record.event.event_type] += 1

        ranked = sorted(intervals.items(), key=lambda item: (-item[1], item[0]))[
            :TOP_INTERVAL_COUNT
        ]
        return [
            SignalIntervalAggregate(
                start_ms=key[0],
                end_ms=key[1],
                event_count=count,
                dominant_event_types=[
                    event_type for event_type, _ in event_types[key].most_common(2)
                ],
            )
            for key, count in ranked
        ]

    def build_summary(self, actor: AuthenticatedActor, session_id: str) -> ProfessorSummary:
        """Build one threshold-safe anonymous summary for a course professor.

        Args:
            actor: Authenticated professor for the session's course.
            session_id: Session to summarize.

        Returns:
            A released or suppressed summary. Suppressed summaries contain
            only the threshold, bucket width, and participant count.

        Raises:
            AppError: ``forbidden`` for students, other professors, or
                professors of a different course.
        """

        if not self._settings.is_demo_or_test():
            raise AppError(
                ErrorCode.FORBIDDEN, "Use the policy-gated professor-metrics endpoint."
            )
        membership = self._session_access.resolve_membership(actor, session_id)
        session = self._store.sessions[session_id]
        if actor.role != ROLE_PROFESSOR:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Professor summaries require an authorized professor.",
            )
        if membership.session_role not in (
            SESSION_ROLE_COURSE_PROFESSOR,
            SESSION_ROLE_OWNER,
        ):
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Only the professor for this course can read the summary.",
            )
        if actor.course_id != session.course_id:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "This professor is not authorized for the session's course.",
            )

        participant_count = self._count_participating_users(session_id)
        is_suppressed = participant_count < self._settings.minimum_group_size
        summary = ProfessorSummary(
            summary_id=f"summary_{uuid4().hex}",
            session_id=session_id,
            participant_count=participant_count,
            minimum_group_size=self._settings.minimum_group_size,
            aggregation_window_ms=self._settings.aggregation_window_ms,
            is_suppressed=is_suppressed,
            timeline_buckets=(
                None if is_suppressed else self._build_timeline_buckets(session_id)
            ),
            highest_signal_intervals=(
                None if is_suppressed else self._build_highest_signal_intervals(session_id)
            ),
            suggested_actions=None if is_suppressed else list(SUGGESTED_ACTIONS),
            generated_at=utc_now_iso(),
        )
        self._publisher.publish(
            self._publisher.build_envelope(
                session_id,
                PROFESSOR_SUMMARY_READY,
                {"summary_id": summary.summary_id, "is_suppressed": is_suppressed},
            )
        )
        return summary

    def _safe_records(self, session_id: str) -> list[EventRecord]:
        """Exclude dismissed, nonconsenting and phone-derived evidence in legacy demos."""
        participants = self._signal_service.get_participants(session_id)
        return [
            record
            for record in self._signal_service.list_session_events(session_id)
            if record.submitted_by in participants
            and participants[record.submitted_by].is_opted_in
            and record.event.user_confirmed is not False
            and record.event.event_type not in {"phone_visible", "student_returned"}
            and "phone_visible" not in record.event.signals
        ]
