"""Transcript ingestion: validation, revisions, and duplicates."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.auth.access import SESSION_ROLE_COURSE_PROFESSOR, SessionAccess
from app.auth.tokens import AuthenticatedActor
from app.config import Settings
from app.contracts.models import IngestTranscriptRequest, TranscriptChunk
from app.core.errors import AppError, ErrorCode
from app.storage.in_memory import InMemoryStore
from app.transcript.repository import (
    TRANSCRIPT_INGESTED,
    TimelineReader,
    WindowReadResult,
)
from app.ws.publisher import EventPublisher


class TranscriptBatchResponse(BaseModel):
    """Response summarizing one accepted transcript batch."""

    session_id: str = Field(description="Session the batch was ingested into.")
    accepted_chunk_ids: list[str] = Field(description="Newly accepted chunk identifiers.")
    superseded_chunk_ids: list[str] = Field(
        description="Chunk ids corrected by a higher revision in this batch."
    )
    transcript_revision: int = Field(
        ge=0, description="Latest revision in the session timeline after ingest."
    )


class TranscriptWindowResponse(BaseModel):
    """Response for one timeline read."""

    session_id: str = Field(description="Session the window was read from.")
    start_ms: int = Field(ge=0, description="Requested interval start in ms.")
    end_ms: int = Field(gt=0, description="Requested interval end in ms.")
    transcript_revision: int = Field(ge=0, description="Timeline revision served.")
    chunks: list[TranscriptChunk] = Field(description="Final chunks in the window.")


class TranscriptService:
    """Batch ingestion and timeline reads for timestamped transcript chunks."""

    def __init__(
        self,
        store: InMemoryStore,
        settings: Settings,
        session_access: SessionAccess,
        timeline_reader: TimelineReader,
        event_publisher: EventPublisher,
    ) -> None:
        """Bind the service to shared storage, settings, and publishing.

        Args:
            store: Injected storage connections.
            settings: Application settings with ingestion limits.
            session_access: Shared membership resolver.
            timeline_reader: Frozen timeline interface for reads.
            event_publisher: Publisher for session-scoped typed events.
        """

        self._store = store
        self._settings = settings
        self._session_access = session_access
        self._timeline_reader = timeline_reader
        self._publisher = event_publisher

    def ingest_batch(
        self,
        actor: AuthenticatedActor,
        session_id: str,
        request: IngestTranscriptRequest,
    ) -> TranscriptBatchResponse:
        """Validate and store one batch of transcript chunks.

        Chunks with an existing id must carry a strictly higher revision;
        equal or lower revisions are rejected as duplicates or out-of-order
        submissions. A higher revision supersedes the prior chunk so
        corrections invalidate cached cards.

        Args:
            actor: Authenticated owner or participant submitting the batch.
            session_id: Session the chunks belong to.
            request: Validated batch payload.

        Returns:
            Response listing accepted and superseded chunk ids.

        Raises:
            AppError: ``forbidden``, ``validation_failed``,
                ``payload_too_large``, or ``duplicate`` for rejected batches.
        """

        membership = self._session_access.resolve_membership(actor, session_id)
        if membership.session_role == SESSION_ROLE_COURSE_PROFESSOR:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Professors cannot ingest transcripts for student sessions.",
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

        if len(request.chunks) > self._settings.max_batch_chunks:
            raise AppError(
                ErrorCode.PAYLOAD_TOO_LARGE,
                "Transcript batch exceeds the configured maximum.",
                details={"max_batch_chunks": self._settings.max_batch_chunks},
            )

        chunks = self._store.transcript_chunks.setdefault(session_id, [])
        by_chunk_id = {chunk.chunk_id: chunk for chunk in chunks}
        accepted: list[str] = []
        superseded: list[str] = []
        within_batch: set[str] = set()

        for chunk in request.chunks:
            if chunk.session_id != session_id:
                raise AppError(
                    ErrorCode.VALIDATION_FAILED,
                    "Every chunk's session_id must match the path session_id.",
                )
            if len(chunk.text) > self._settings.max_transcript_text_chars:
                raise AppError(
                    ErrorCode.PAYLOAD_TOO_LARGE,
                    "Transcript chunk text exceeds the configured maximum.",
                    details={
                        "chunk_id": chunk.chunk_id,
                        "max_transcript_text_chars": (
                            self._settings.max_transcript_text_chars
                        ),
                    },
                )
            if chunk.chunk_id in within_batch:
                raise AppError(
                    ErrorCode.DUPLICATE,
                    "Duplicate transcript chunk id within the batch.",
                    details={"duplicate_chunk_id": chunk.chunk_id},
                )

            prior = by_chunk_id.get(chunk.chunk_id)
            if prior is not None:
                if chunk.revision <= prior.revision:
                    raise AppError(
                        ErrorCode.DUPLICATE,
                        "Chunk revision must increase to supersede stored text.",
                        details={
                            "chunk_id": chunk.chunk_id,
                            "stored_revision": prior.revision,
                            "received_revision": chunk.revision,
                        },
                    )
                chunks.remove(prior)
                superseded.append(prior.chunk_id)

            within_batch.add(chunk.chunk_id)
            chunks.append(chunk)
            by_chunk_id[chunk.chunk_id] = chunk
            accepted.append(chunk.chunk_id)

        transcript_revision = max((chunk.revision for chunk in chunks), default=0)
        self._publisher.publish(
            self._publisher.build_envelope(
                session_id,
                TRANSCRIPT_INGESTED,
                {
                    "accepted_chunk_ids": accepted,
                    "superseded_chunk_ids": superseded,
                    "transcript_revision": transcript_revision,
                },
            )
        )
        return TranscriptBatchResponse(
            session_id=session_id,
            accepted_chunk_ids=accepted,
            superseded_chunk_ids=superseded,
            transcript_revision=transcript_revision,
        )

    def read_window(
        self, actor: AuthenticatedActor, session_id: str, start_ms: int, end_ms: int
    ) -> TranscriptWindowResponse:
        """Read final transcript chunks for an authorized member.

        Args:
            actor: Authenticated owner, participant, or course professor.
            session_id: Session whose timeline is read.
            start_ms: Half-open interval start in ms.
            end_ms: Half-open interval end in ms.

        Returns:
            The final chunks in the window with the served revision.
        """

        self._session_access.resolve_membership(actor, session_id)
        result: WindowReadResult = self._timeline_reader.read_window(
            session_id, start_ms, end_ms
        )
        return TranscriptWindowResponse(
            session_id=session_id,
            start_ms=start_ms,
            end_ms=end_ms,
            transcript_revision=result.transcript_revision,
            chunks=result.chunks,
        )
