"""Shared read-only timeline DTOs; no feature implementation is imported."""

from app.signals.models import MissedWindow, SignalEvent
from app.timeline.contracts import Interval, StrictModel
from app.transcript.models import TranscriptChunk


class TimelinePage(StrictModel):
    """Final transcript and the caller's private signals within a bounded interval."""

    session_id: str
    interval: Interval
    revision: int
    transcript_revision: int
    chunks: list[TranscriptChunk]
    events: list[SignalEvent]
    missed_windows: list[MissedWindow]


class ContextWindow(StrictModel):
    """Recovery context with explicit requested/effective intervals and source revision."""

    session_id: str
    requested_interval: Interval
    effective_interval: Interval
    transcript_revision: int
    chunks: list[TranscriptChunk]
