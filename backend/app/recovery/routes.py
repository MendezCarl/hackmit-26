"""REST routes for recovery jobs, cards, and cost metrics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import (
    CostMetrics,
    CreateRecoveryJobRequest,
    RecoveryCard,
    RecoveryJob,
)
from app.recovery.service import RecoveryService

router = APIRouter(prefix="/api/v1/sessions/{session_id}", tags=["recovery"])


def get_recovery_service(request: Request) -> RecoveryService:
    """Resolve the recovery service from application state."""

    return request.app.state.recovery_service


@router.post(
    "/recovery-cards",
    response_model=RecoveryJob,
    status_code=202,
    summary="Request recovery using the unified contract path",
)
@router.post(
    "/recovery/jobs",
    response_model=RecoveryJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a recovery card for an interval",
)
def create_recovery_job(
    session_id: str,
    request_body: CreateRecoveryJobRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Retries with the same key return the original job.",
        ),
    ] = None,
) -> RecoveryJob:
    """Recover missed content for ``[start_ms, end_ms)`` in one session.

    Supplying an ``Idempotency-Key`` header makes the request safe to retry:
    the same key returns the original job instead of creating a duplicate.
    """

    return service.create_job(actor, session_id, request_body, idempotency_key)


@router.get(
    "/recovery/jobs/{job_id}",
    response_model=RecoveryJob,
    summary="Retrieve a recovery job",
)
def read_recovery_job(
    session_id: str,
    job_id: str,
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
) -> RecoveryJob:
    """Return the job status, card reference, or typed failure."""

    response.headers["Cache-Control"] = "no-store"
    return service.get_job(actor, session_id, job_id)


@router.get(
    "/recovery-cards/{card_id}",
    response_model=RecoveryCard,
    summary="Read a private recovery card",
    operation_id="read_recovery_card_unified",
)
@router.get(
    "/recovery/cards/{card_id}",
    response_model=RecoveryCard,
    summary="Retrieve a recovery card",
)
def read_recovery_card(
    session_id: str,
    card_id: str,
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
) -> RecoveryCard:
    """Return one personal recovery card exclusively to its requesting student."""

    response.headers["Cache-Control"] = "no-store"
    return service.get_card(actor, session_id, card_id)


@router.get(
    "/cost/metrics",
    response_model=list[CostMetrics],
    summary="List cost metrics for the session",
)
def read_cost_metrics(
    session_id: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
) -> list[CostMetrics]:
    """Return recorded provider usage, labeled synthetic in mock mode."""

    return service.list_cost_metrics(actor, session_id)
