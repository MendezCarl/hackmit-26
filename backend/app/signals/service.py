"""Consent-aware signal ingestion and deterministic missed-window rules."""

from app.signals.models import (
    MissedWindow,
    SignalBatch,
    SignalEvent,
    SignalFeedback,
    SignalRules,
    StoredSignal,
)
from app.signals.rules import build_phone_windows, observation_labels
from app.timeline.contracts import (
    FeatureError,
    Interval,
    Receipt,
    SessionGrant,
    overlaps,
    require_interval,
)
from app.timeline.repository import (
    MAX_SESSION_SIGNALS,
    SessionRepository,
    SessionState,
    mutate_session,
)


def build_missed_windows(
    events: list[SignalEvent], rules: SignalRules
) -> list[MissedWindow]:
    """Merge private recovery candidates without treating phone presence as attention.

    Args:
        events: Authorized, same-participant/session observations.
        rules: Configurable demo thresholds; not validated attention thresholds.
    Returns:
        Uncertain intervals. Phone evidence requires sustained corroboration;
        looking down alone and return markers create no automatic windows.
        Explicit self-reports and confirmation of non-phone events remain supported.
    """
    candidates = build_phone_windows(events, rules)
    for event in events:
        labels = observation_labels(event)
        if (
            event.user_confirmed is False
            or "phone_visible" in labels
            or event.event_type == "student_returned"
            or labels == {"student_returned"}
        ):
            continue
        is_explicit = (
            event.user_confirmed is True or event.event_type == "user_marked_confused"
        )
        is_independent = bool(
            labels
            & {"face_absent", "head_away", "window_unfocused", "student_left_frame"}
        )
        if is_explicit or (
            is_independent
            and event.end_ms - event.start_ms >= rules.minimum_duration_ms
            and event.confidence >= rules.minimum_confidence
        ):
            candidates.append(
                MissedWindow(
                    start_ms=event.start_ms,
                    end_ms=event.end_ms,
                    source_event_ids=[event.event_id],
                    signals=sorted(labels),
                    confidence=event.confidence,
                )
            )
    eligible = sorted(
        candidates,
        key=lambda window: (window.start_ms, window.end_ms, window.source_event_ids),
    )
    windows: list[MissedWindow] = []
    for candidate in eligible:
        if windows and candidate.start_ms <= windows[-1].end_ms + rules.merge_gap_ms:
            previous = windows[-1]
            previous.end_ms = max(previous.end_ms, candidate.end_ms)
            previous.source_event_ids = sorted(
                set(previous.source_event_ids + candidate.source_event_ids)
            )
            previous.signals = sorted(set(previous.signals + candidate.signals))
            previous.confidence = max(previous.confidence, candidate.confidence)
        else:
            windows.append(
                MissedWindow(
                    start_ms=candidate.start_ms,
                    end_ms=candidate.end_ms,
                    source_event_ids=candidate.source_event_ids,
                    signals=sorted(set(candidate.signals)),
                    confidence=candidate.confidence,
                )
            )
    return windows


class SignalService:
    """Own private event storage; expose only the authorized student's signals."""

    def __init__(self, repository: SessionRepository, rules: SignalRules) -> None:
        """Inject session storage and configurable local-signal interpretation rules."""
        self.repository = repository
        self.rules = rules

    async def ingest(self, grant: SessionGrant, batch: SignalBatch) -> Receipt:
        """Validate and atomically ingest coarse events; reject conflicts or absent consent."""
        if not grant.can_signal or not grant.has_signal_consent:
            raise FeatureError(
                "consent_required", "Signal collection is not authorized.", 403
            )
        if grant.is_ended:
            raise FeatureError("session_ended", "Signal ingestion has ended.", 409)
        for event in batch.events:
            require_interval(grant, event)
            if event.lecture_id != grant.lecture_id:
                raise FeatureError(
                    "lecture_mismatch", "Lecture does not match this session."
                )

        def change(state: SessionState) -> tuple[Receipt, bool]:
            accepted = duplicates = 0
            existing = {
                (item.participant_key, item.event.event_id): item
                for item in state.signals
            }
            for event in batch.events:
                key = (grant.participant_key, event.event_id)
                if key in existing:
                    if existing[key].original != event:
                        raise FeatureError(
                            "event_conflict",
                            "Event identifier already has different content.",
                            409,
                        )
                    duplicates += 1
                    continue
                record = StoredSignal(
                    participant_key=grant.participant_key, original=event, event=event
                )
                existing[key] = record
                state.signals.append(record)
                accepted += 1
            if len(state.signals) > MAX_SESSION_SIGNALS:
                raise FeatureError("session_capacity", "Signal capacity reached.", 413)
            return Receipt(
                accepted=accepted,
                duplicates=duplicates,
                revision=state.revision + bool(accepted),
            ), bool(accepted)

        return await mutate_session(self.repository, grant.session_id, change)

    async def correct(
        self, grant: SessionGrant, event_id: str, feedback: SignalFeedback
    ) -> SignalEvent:
        """Record the owner's confirmation/dismissal, including after the lecture ends."""
        if not grant.can_signal:
            raise FeatureError(
                "forbidden", "Only the signal owner may correct it.", 403
            )

        def change(state: SessionState) -> tuple[SignalEvent, bool]:
            for stored in state.signals:
                if (
                    stored.participant_key == grant.participant_key
                    and stored.event.event_id == event_id
                ):
                    has_changed = stored.event.user_confirmed != feedback.user_confirmed
                    stored.event = stored.event.model_copy(
                        update={"user_confirmed": feedback.user_confirmed}
                    )
                    return stored.event, has_changed
            raise FeatureError("event_not_found", "Signal event was not found.", 404)

        return await mutate_session(self.repository, grant.session_id, change)

    async def read(self, grant: SessionGrant, interval: Interval) -> list[SignalEvent]:
        """Return only this participant's overlapping events, never another student's."""
        require_interval(grant, interval)
        state = await self.repository.load(grant.session_id)
        return [
            item.event
            for item in state.signals
            if item.participant_key == grant.participant_key
            and overlaps(item.event, interval)
        ]
