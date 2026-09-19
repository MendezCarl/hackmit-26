"""Version-aware transcript ingestion shared by REST, WebSocket and Zoom simulation."""

from app.timeline.contracts import FeatureError, Receipt, SessionGrant, require_interval
from app.timeline.repository import (
    MAX_SESSION_CHUNKS,
    SessionRepository,
    SessionState,
    mutate_session,
)
from app.transcript.models import TranscriptBatch


class TranscriptService:
    """Ingest derived text with per-chunk revisions and session-level invalidation."""

    def __init__(self, repository: SessionRepository) -> None:
        """Inject atomic session storage."""
        self.repository = repository

    async def ingest(self, grant: SessionGrant, batch: TranscriptBatch) -> Receipt:
        """Commit a full valid batch or none; reject stale/conflicting revisions.

        Raises:
            FeatureError: For unauthorized producers, invalid clocks, conflicts,
                finalized sessions, or exceeded storage capacity.
        """
        if not grant.can_transcribe:
            raise FeatureError(
                "forbidden", "Transcript ingestion is not authorized.", 403
            )
        if grant.is_ended:
            raise FeatureError("session_ended", "Transcript ingestion has ended.", 409)
        for chunk in batch.chunks:
            require_interval(grant, chunk)
            if chunk.lecture_id != grant.lecture_id:
                raise FeatureError(
                    "lecture_mismatch", "Lecture does not match this session."
                )

        def change(state: SessionState) -> tuple[Receipt, bool]:
            chunks = {chunk.chunk_id: chunk for chunk in state.chunks}
            accepted = duplicates = 0
            for chunk in batch.chunks:
                previous = chunks.get(chunk.chunk_id)
                if previous is not None:
                    if previous == chunk:
                        duplicates += 1
                        continue
                    if chunk.revision <= previous.revision:
                        raise FeatureError(
                            "transcript_conflict",
                            "Transcript revision is stale or conflicting.",
                            409,
                        )
                    if previous.is_final and not chunk.is_final:
                        raise FeatureError(
                            "transcript_conflict",
                            "Final text cannot become provisional.",
                            409,
                        )
                    if previous.source != chunk.source:
                        raise FeatureError(
                            "transcript_conflict",
                            "Transcript source cannot change.",
                            409,
                        )
                chunks[chunk.chunk_id] = chunk
                accepted += 1
            if len(chunks) > MAX_SESSION_CHUNKS:
                raise FeatureError(
                    "session_capacity", "Transcript capacity reached.", 413
                )
            state.chunks = sorted(
                chunks.values(), key=lambda chunk: (chunk.start_ms, chunk.chunk_id)
            )
            if accepted:
                state.transcript_revision += 1
            return Receipt(
                accepted=accepted,
                duplicates=duplicates,
                revision=state.revision + bool(accepted),
            ), bool(accepted)

        return await mutate_session(self.repository, grant.session_id, change)
