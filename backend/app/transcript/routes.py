"""REST routes for transcript ingestion and timeline reads."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import IngestTranscriptRequest
from app.transcript.service import (
    TranscriptBatchResponse,
    TranscriptService,
    TranscriptWindowResponse,
)

router = APIRouter(prefix="/api/v1/sessions/{session_id}", tags=["transcript"])


def get_transcript_service(request: Request) -> TranscriptService:
    """Resolve the transcript service from application state."""

    return request.app.state.transcript_service


@router.post(
    "/transcript-chunks/batch",
    response_model=TranscriptBatchResponse,
    status_code=202,
    summary="Ingest transcript chunks using the unified contract path",
)
@router.post(
    "/transcript/batch",
    response_model=TranscriptBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a batch of transcript chunks",
)
def ingest_transcript(
    session_id: str,
    request_body: IngestTranscriptRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[TranscriptService, Depends(get_transcript_service)],
) -> TranscriptBatchResponse:
    """Ingest timestamped transcript chunks from Zoom RTMS or local worker."""

    return service.ingest_batch(actor, session_id, request_body)


@router.get(
    "/transcript",
    response_model=TranscriptWindowResponse,
    summary="Read transcript chunks for an interval",
)
def read_transcript_window(
    session_id: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[TranscriptService, Depends(get_transcript_service)],
    start_ms: Annotated[
        int, Query(ge=0, description="Half-open interval start in ms.")
    ],
    end_ms: Annotated[int, Query(gt=0, description="Half-open interval end in ms.")],
) -> TranscriptWindowResponse:
    """Read final transcript chunks overlapping ``[start_ms, end_ms)``."""

    return service.read_window(actor, session_id, start_ms, end_ms)
