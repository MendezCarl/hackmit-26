"""Typed service interfaces shared across independently developed features."""

from typing import Protocol

from app.dropbox.models import (
    ExportReceipt,
    ExportRequest,
    FilePage,
    FolderReceipt,
    FolderSelection,
    Material,
    MaterialRequest,
)
from app.professor.models import AggregationPolicy, ProfessorSummary
from app.signals.models import SignalBatch, SignalEvent, SignalFeedback
from app.timeline.contracts import Interval, Receipt, SessionGrant
from app.timeline.models import ContextWindow, TimelinePage
from app.transcript.models import TranscriptBatch


class SignalPort(Protocol):
    """Authorized coarse-signal operations supplied by feature 2."""

    async def ingest(self, grant: SessionGrant, batch: SignalBatch) -> Receipt:
        """Ingest an atomic batch or raise a typed feature error."""
        ...

    async def correct(
        self, grant: SessionGrant, event_id: str, feedback: SignalFeedback
    ) -> SignalEvent:
        """Return the owner's corrected signal."""
        ...


class TranscriptPort(Protocol):
    """Authorized derived-text writes supplied by feature 2."""

    async def ingest(self, grant: SessionGrant, batch: TranscriptBatch) -> Receipt:
        """Ingest a revisioned batch or raise a typed feature error."""
        ...


class TimelinePort(Protocol):
    """Bounded timeline queries supplied by feature 2."""

    async def read(self, grant: SessionGrant, interval: Interval) -> TimelinePage:
        """Return final text and the caller's private events."""
        ...

    async def context(
        self, grant: SessionGrant, interval: Interval, padding_ms: int = 5000
    ) -> ContextWindow:
        """Return revisioned context or a missing-transcript error."""
        ...


class ProfessorPort(Protocol):
    """Threshold-safe summaries supplied by feature 4."""

    policy: AggregationPolicy | None

    async def summarize(self, grant: SessionGrant) -> ProfessorSummary:
        """Return the authorized post-lecture summary."""
        ...


class DropboxPort(Protocol):
    """Selected derived-content operations supplied by feature 6."""

    async def link(self, grant: SessionGrant, selection: FolderSelection) -> FolderReceipt:
        """Link a verified user-selected folder."""
        ...

    async def list_files(self, grant: SessionGrant, cursor: str | None = None) -> FilePage:
        """List bounded metadata inside the linked folder."""
        ...

    async def read(self, grant: SessionGrant, request: MaterialRequest) -> Material:
        """Read selected supporting text."""
        ...

    async def export(self, grant: SessionGrant, request: ExportRequest) -> ExportReceipt:
        """Export an authorized derived artifact."""
        ...
