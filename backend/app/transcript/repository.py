"""Timeline reads over final transcript chunks.

``TimelineReader`` is the frozen shared interface the recovery workstream
consumes. It returns overlapping final chunks, source ids, and the transcript
revision for an interval, using half-open ``[start_ms, end_ms)`` semantics.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.contracts.models import TranscriptChunk
from app.storage.in_memory import InMemoryStore

TRANSCRIPT_INGESTED = "transcript.ingested"


class WindowReadResult(BaseModel):
    """Result of one timeline read over an interval."""

    chunks: list[TranscriptChunk] = Field(
        description="Final chunks overlapping the interval, ordered by start time."
    )
    transcript_revision: int = Field(
        ge=0, description="Latest revision seen in the session's timeline."
    )
    source_ids: list[str] = Field(description="Distinct source chunk identifiers.")


class TimelineReader(Protocol):
    """Frozen interface for retrieving final transcript chunks."""

    def read_window(self, session_id: str, start_ms: int, end_ms: int) -> WindowReadResult:
        """Retrieve final chunks overlapping the interval.

        Args:
            session_id: Session whose timeline is read.
            start_ms: Half-open interval start in ms.
            end_ms: Half-open interval end in ms.

        Returns:
            Overlapping final chunks, the transcript revision, and source ids.
        """
        ...


class InMemoryTimelineReader:
    """TimelineReader implementation over the injected in-memory store."""

    def __init__(self, store: InMemoryStore) -> None:
        """Bind the reader to shared storage.

        Args:
            store: Injected storage connections.
        """

        self._store = store

    def read_window(self, session_id: str, start_ms: int, end_ms: int) -> WindowReadResult:
        """Return final chunks overlapping ``[start_ms, end_ms)``.

        Provisional chunks are stored but excluded from timeline reads.
        The revision covers every stored chunk, provisional or final, so a
        correction invalidates cached cards.

        Args:
            session_id: Session whose timeline is read.
            start_ms: Half-open interval start in ms.
            end_ms: Half-open interval end in ms.

        Returns:
            Overlapping final chunks, the transcript revision, and source ids.
        """

        chunks = [
            chunk
            for chunk in self._store.transcript_chunks.get(session_id, [])
            if chunk.is_final and chunk.start_ms < end_ms and start_ms < chunk.end_ms
        ]
        chunks.sort(key=lambda chunk: (chunk.start_ms, chunk.end_ms))
        all_chunks = self._store.transcript_chunks.get(session_id, [])
        transcript_revision = max((chunk.revision for chunk in all_chunks), default=0)
        return WindowReadResult(
            chunks=chunks,
            transcript_revision=transcript_revision,
            source_ids=[chunk.chunk_id for chunk in chunks],
        )
