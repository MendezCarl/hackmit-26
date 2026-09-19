"""Bounded, synchronized timeline/context reads for Person A's recovery pipeline."""

from app.signals.models import SignalRules
from app.signals.service import build_missed_windows
from app.timeline.contracts import (
    MAX_QUERY_MS,
    FeatureError,
    Interval,
    SessionGrant,
    overlaps,
    require_interval,
)
from app.timeline.models import ContextWindow, TimelinePage
from app.timeline.repository import SessionRepository


class TimelineService:
    """Read-only timeline adapter; callers supply a freshly authorized grant."""

    def __init__(self, repository: SessionRepository, rules: SignalRules) -> None:
        """Inject shared feature storage and signal-window heuristics."""
        self.repository = repository
        self.rules = rules

    async def read(self, grant: SessionGrant, interval: Interval) -> TimelinePage:
        """Return final chunks plus own events; reject oversized or invalid ranges."""
        require_interval(grant, interval)
        if interval.end_ms - interval.start_ms > MAX_QUERY_MS:
            raise FeatureError(
                "range_too_large", "Query at most ten minutes at a time."
            )
        state = await self.repository.load(grant.session_id)
        events = [
            stored.event
            for stored in state.signals
            if stored.participant_key == grant.participant_key
            and overlaps(stored.event, interval)
        ]
        return TimelinePage(
            session_id=grant.session_id,
            interval=interval,
            revision=state.revision,
            transcript_revision=state.transcript_revision,
            chunks=[
                chunk
                for chunk in state.chunks
                if chunk.is_final and overlaps(chunk, interval)
            ],
            events=events,
            missed_windows=build_missed_windows(events, self.rules),
        )

    async def context(
        self, grant: SessionGrant, interval: Interval, padding_ms: int = 5000
    ) -> ContextWindow:
        """Select final overlapping chunks with clamped padding; never invent missing text.

        Whole chunks are returned with their original timestamps; consumers must
        ground to chunk boundaries, since text is not aligned word-by-word.
        """
        require_interval(grant, interval)
        if not 0 <= padding_ms <= 30_000:
            raise FeatureError(
                "invalid_padding", "Padding must be between zero and thirty seconds."
            )
        effective = Interval(
            start_ms=max(0, interval.start_ms - padding_ms),
            end_ms=min(grant.duration_ms, interval.end_ms + padding_ms),
        )
        page = await self.read(grant, effective)
        if not page.chunks:
            raise FeatureError(
                "transcript_unavailable",
                "No final transcript is available for this interval.",
                409,
            )
        return ContextWindow(
            session_id=grant.session_id,
            requested_interval=interval,
            effective_interval=effective,
            transcript_revision=page.transcript_revision,
            chunks=page.chunks,
        )
