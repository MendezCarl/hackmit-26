"""Normalize synthetic Zoom-style epoch timestamps into one trusted lecture clock.

This model is deliberately a demo fixture format, not a claim to implement Zoom's
RTMS wire protocol. A future verified RTMS transport must translate into this port.
"""

from typing import Annotated

from pydantic import Field

from app.timeline.contracts import (
    FeatureError,
    Identifier,
    Receipt,
    SessionGrant,
    StrictModel,
)
from app.timeline.ports import TranscriptPort
from app.transcript.models import MAX_CHUNK_CHARACTERS, TranscriptBatch, TranscriptChunk


class SimulatedZoomChunk(StrictModel):
    """Synthetic derived-text packet; epoch timestamps are integer milliseconds."""

    chunk_id: Identifier
    start_epoch_ms: Annotated[int, Field(strict=True, ge=0)]
    end_epoch_ms: Annotated[int, Field(strict=True, ge=0)]
    text: Annotated[str, Field(min_length=1, max_length=MAX_CHUNK_CHARACTERS)]
    is_final: Annotated[bool, Field(strict=True)] = True
    revision: Annotated[int, Field(strict=True, ge=1)] = 1


class SimulatedZoomBatch(StrictModel):
    """At most 100 synthetic packets; raw media fields are forbidden."""

    chunks: Annotated[list[SimulatedZoomChunk], Field(min_length=1, max_length=100)]


def map_zoom_chunk(grant: SessionGrant, packet: SimulatedZoomChunk) -> TranscriptChunk:
    """Map a synthetic epoch interval; reject pre-session or invalid timestamps."""
    start_ms = packet.start_epoch_ms - grant.clock_origin_epoch_ms
    end_ms = packet.end_epoch_ms - grant.clock_origin_epoch_ms
    if not 0 <= start_ms < end_ms <= grant.duration_ms:
        raise FeatureError(
            "invalid_time_range", "Provider timestamps are outside this session."
        )
    return TranscriptChunk(
        chunk_id=packet.chunk_id,
        lecture_id=grant.lecture_id,
        start_ms=start_ms,
        end_ms=end_ms,
        text=packet.text,
        source="zoom_rtms",
        is_final=packet.is_final,
        revision=packet.revision,
    )


async def ingest_simulated_zoom(
    grant: SessionGrant, batch: SimulatedZoomBatch, service: TranscriptPort
) -> Receipt:
    """Validate a synthetic batch and reuse the ordinary transcript ingestion path."""
    return await service.ingest(
        grant,
        TranscriptBatch(
            chunks=[map_zoom_chunk(grant, packet) for packet in batch.chunks]
        ),
    )
