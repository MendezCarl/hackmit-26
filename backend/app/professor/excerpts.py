"""Bounded lecture-transcript excerpts for released professor hotspots.

Excerpts contain lecture content only: no speaker labels, participant data or
student signals. Chunk identifiers are replaced by request-local aliases so the
provider request never carries stored identifiers; the service maps grounded
evidence back to real ``chunk_id`` values for the professor.
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.contracts.learning import MetricsBucket, ProfessorMetrics
from app.contracts.models import TranscriptChunk
from app.storage.in_memory import InMemoryStore

EXCERPT_CHARACTER_LIMIT = 2_000
MAX_EXCERPT_INTERVALS = 5


@dataclass(frozen=True)
class ExcerptChunk:
    """One transcript chunk selected for a hotspot, keyed by an opaque alias."""

    alias: str
    chunk_id: str
    text: str


@dataclass(frozen=True)
class HotspotExcerpt:
    """Lecture text overlapping one released hotspot interval."""

    start_ms: int
    end_ms: int
    chunks: list[ExcerptChunk] = field(default_factory=list)

    def chunk_by_alias(self) -> dict[str, ExcerptChunk]:
        """Return the excerpt's chunks indexed by their request-local alias."""
        return {chunk.alias: chunk for chunk in self.chunks}


class TranscriptExcerptReader(Protocol):
    """Read bounded lecture excerpts for hotspot buckets without exposing storage."""

    def excerpts(self, report: ProfessorMetrics) -> list[HotspotExcerpt]:
        """Return one excerpt per released hotspot in report order (may be empty)."""
        ...


def released_hotspots(report: ProfessorMetrics) -> list[MetricsBucket]:
    """Return the released hotspot buckets eligible for recommendations, in order."""
    return [
        bucket
        for bucket in report.buckets
        if bucket.status == "available" and bucket.is_hotspot
    ][:MAX_EXCERPT_INTERVALS]


def build_hotspot_excerpt(
    bucket: MetricsBucket,
    chunks: list[TranscriptChunk],
    character_limit: int = EXCERPT_CHARACTER_LIMIT,
) -> HotspotExcerpt:
    """Select final transcript chunks referenced by a hotspot within a character budget.

    Args:
        bucket: Released hotspot bucket whose ``transcript_chunk_ids`` are trusted.
        chunks: Final transcript chunks of the session.
        character_limit: Maximum total excerpt characters for this interval.

    Returns:
        Excerpt with chunks ordered by start time; chunks that would exceed the
        budget are omitted, and the last kept chunk may be truncated.
    """
    wanted = set(bucket.transcript_chunk_ids)
    selected = sorted(
        (chunk for chunk in chunks if chunk.is_final and chunk.chunk_id in wanted),
        key=lambda chunk: (chunk.start_ms, chunk.end_ms),
    )
    kept: list[ExcerptChunk] = []
    remaining = character_limit
    for index, chunk in enumerate(selected):
        text = " ".join(chunk.text.split())
        if not text or remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining]
        kept.append(
            ExcerptChunk(alias=f"source_{index}", chunk_id=chunk.chunk_id, text=text)
        )
        remaining -= len(text)
    return HotspotExcerpt(start_ms=bucket.start_ms, end_ms=bucket.end_ms, chunks=kept)


class StoreTranscriptExcerpts:
    """Excerpt reader backed by the host store's final transcript chunks."""

    def __init__(self, store: InMemoryStore) -> None:
        """Read from the shared host store; no copies of transcript text are kept."""
        self.store = store

    def excerpts(self, report: ProfessorMetrics) -> list[HotspotExcerpt]:
        """Build one bounded excerpt per released hotspot of the report."""
        chunks = list(self.store.transcript_chunks.get(report.session_id, []))
        return [
            build_hotspot_excerpt(bucket, chunks) for bucket in released_hotspots(report)
        ]
