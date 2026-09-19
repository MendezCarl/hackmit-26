"""Explicitly demo-only simulated Zoom transcript ingestion."""

from fastapi import APIRouter

from app.integrations.zoom.transcript import SimulatedZoomBatch, ingest_simulated_zoom
from app.timeline.contracts import Receipt
from app.timeline.dependencies import AuthorizedSession, Services
from app.timeline.http import ERROR_RESPONSES, FeatureRoute

router = APIRouter(
    prefix="/api/v1/sessions/{session_id}/zoom",
    tags=["zoom-demo"],
    route_class=FeatureRoute,
    responses=ERROR_RESPONSES,
)


@router.post(
    "/simulated-transcript-chunks",
    response_model=Receipt,
    summary="Ingest synthetic Zoom transcript packets",
    description="Demo-only route, absent from the production feature registration. Requires an authorized transcript producer. Accepts synthetic text and epoch-millisecond timestamps; does not expose RTMS media or claim live Zoom connectivity.",
)
async def simulate_zoom(
    batch: SimulatedZoomBatch, grant: AuthorizedSession, services: Services
) -> Receipt:
    """Normalize synthetic packet timestamps and use the shared ingestion service."""
    return await ingest_simulated_zoom(grant, batch, services.transcripts)
