"""REST routes for coarse signal events, participants, and corrections."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import (
    ConfirmEventRequest,
    IngestEventsRequest,
    RegisterParticipantRequest,
    SignalEvent,
)
from app.signals.service import EventBatchResponse, ParticipantResponse, SignalService

router = APIRouter(prefix="/api/v1/sessions/{session_id}", tags=["signals"])


def get_signal_service(request: Request) -> SignalService:
    """Resolve the signal service from application state."""

    return request.app.state.signal_service


@router.post(
    "/events/batch",
    response_model=EventBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a batch of signal events",
)
def ingest_events(
    session_id: str,
    request_body: IngestEventsRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[SignalService, Depends(get_signal_service)],
) -> EventBatchResponse:
    """Ingest coarse, timestamped missed-content signal events.

    Raw webcam frames, continuous raw audio, and screenshots are never
    accepted; unexpected fields are rejected by contract validation.
    """

    return service.ingest_batch(actor, session_id, request_body)


@router.post(
    "/participants",
    response_model=ParticipantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register as a session participant",
)
def register_participant(
    session_id: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[SignalService, Depends(get_signal_service)],
    request_body: RegisterParticipantRequest | None = None,
) -> ParticipantResponse:
    """Opt the authenticated user into anonymous, aggregated participation."""

    return service.register_participant(actor, session_id)


@router.post(
    "/events/{event_id}/confirmation",
    response_model=SignalEvent,
    summary="Correct a signal event",
)
def confirm_event(
    session_id: str,
    event_id: str,
    request_body: ConfirmEventRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[SignalService, Depends(get_signal_service)],
) -> SignalEvent:
    """Apply the student's confirmation or denial of missed content."""

    return service.confirm_event(actor, session_id, event_id, request_body)
