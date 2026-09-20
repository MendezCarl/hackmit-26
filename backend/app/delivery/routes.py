"""Typed feature routes; authentication and contract rules follow ADR 0002."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import (
    BatchReceipt,
    DeliveryBatch,
)
from app.contracts.models import ErrorResponse

Actor = Annotated[AuthenticatedActor, Depends(get_current_actor)]
router = APIRouter(
    prefix="/api/v1/sessions/{session_id}",
    tags=["learning"],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 422, 502)
    },
)


@router.post(
    "/delivery-events/batch",
    response_model=BatchReceipt,
    description="Course-professor JWT required. Accepts only local derived delivery events. Frames, boxes, file paths and student identity are forbidden. Conflicts reject the entire batch.",
)
def ingest_delivery(
    session_id: str, body: DeliveryBatch, actor: Actor, request: Request
) -> BatchReceipt:
    """Record lecture-delivery observations separately from private student signals."""
    return request.app.state.delivery_service.ingest(actor, session_id, body)
