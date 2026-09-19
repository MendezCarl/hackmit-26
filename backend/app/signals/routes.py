"""Signal endpoints expose no raw-media or client-selected identity fields."""

from fastapi import APIRouter

from app.signals.models import SignalBatch, SignalEvent, SignalFeedback
from app.timeline.contracts import Identifier, Receipt
from app.timeline.dependencies import AuthorizedSession, Services
from app.timeline.http import ERROR_RESPONSES, FeatureRoute

router = APIRouter(
    prefix="/api/v1/sessions/{session_id}",
    tags=["signals"],
    route_class=FeatureRoute,
    responses=ERROR_RESPONSES,
)


@router.post(
    "/events/batch",
    response_model=Receipt,
    summary="Ingest consented coarse signal events",
    description="Bearer membership and signal consent required. Atomic, retry-safe batch. Rejects raw media and caller identity; malformed payloads return 422, out-of-session ranges 400, conflicts 409. Optional local phone_visible observations support private recovery only with sustained corroboration; they never indicate attention or comprehension.",
)
@router.post(
    "/signals",
    response_model=Receipt,
    summary="Ingest coarse signals (feature alias)",
    description="Alias of events/batch with identical authorization, validation and privacy behavior.",
)
async def ingest_signals(
    batch: SignalBatch, grant: AuthorizedSession, services: Services
) -> Receipt:
    """Ingest this participant's validated event batch; return counts and revision."""
    return await services.signals.ingest(grant, batch)


@router.patch(
    "/events/{event_id}",
    response_model=SignalEvent,
    summary="Confirm or dismiss your signal",
    description="Bearer membership required. Only the originating participant may correct a signal. Returns 404 for another participant's event. Corrections affect timeline and later summaries.",
)
async def correct_signal(
    event_id: Identifier,
    feedback: SignalFeedback,
    grant: AuthorizedSession,
    services: Services,
) -> SignalEvent:
    """Persist the student's correction; return the updated coarse event."""
    return await services.signals.correct(grant, event_id, feedback)
