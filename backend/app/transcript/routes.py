"""Authorized transcript producer endpoint."""

from fastapi import APIRouter

from app.timeline.contracts import Receipt
from app.timeline.dependencies import AuthorizedSession, Services
from app.timeline.http import ERROR_RESPONSES, FeatureRoute
from app.transcript.models import TranscriptBatch

router = APIRouter(
    prefix="/api/v1/sessions/{session_id}",
    tags=["transcripts"],
    route_class=FeatureRoute,
    responses=ERROR_RESPONSES,
)


@router.post(
    "/transcript-chunks/batch",
    response_model=Receipt,
    summary="Ingest bounded transcript text",
    description="Bearer session membership and producer permission required. Text only; no audio or recordings. Batch commits atomically. Stale/conflicting revisions return 409; invalid fields return 422.",
)
async def ingest_transcript(
    batch: TranscriptBatch, grant: AuthorizedSession, services: Services
) -> Receipt:
    """Accept derived transcript chunks; return write counts and revision."""
    return await services.transcripts.ingest(grant, batch)
