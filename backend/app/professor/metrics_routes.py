"""Typed feature routes; authentication and contract rules follow ADR 0002."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import (
    AggregationConsent,
    BatchReceipt,
    CoverageBatch,
    ProfessorMetrics,
)
from app.contracts.models import ErrorResponse
from app.core.errors import AppError, ErrorCode

Actor = Annotated[AuthenticatedActor, Depends(get_current_actor)]
router = APIRouter(
    prefix="/api/v1/sessions/{session_id}",
    tags=["learning"],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 422, 502)
    },
)


@router.post(
    "/coverage/batch",
    response_model=BatchReceipt,
    description="JWT student membership and current aggregation consent required. Accepts bounded availability intervals only. Exact retries are duplicates; conflicting batches are atomic. No raw media or identity claims.",
)
def ingest_coverage(
    session_id: str, body: CoverageBatch, actor: Actor, request: Request
) -> BatchReceipt:
    """Record authenticated student's explicit available/unavailable observation intervals."""
    return request.app.state.professor_metrics.ingest_coverage(actor, session_id, body)


@router.get(
    "/professor-metrics",
    response_model=ProfessorMetrics,
    description="Authorized course professor, ended session and configured policy required. Returns fixed buckets with safe counts or suppression; unknown coverage is never healthy continuity. Phone observations are excluded.",
)
def read_metrics(
    session_id: str, actor: Actor, request: Request, response: Response
) -> ProfessorMetrics:
    """Return a fresh consent-aware report; intermediaries must not cache it."""
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.professor_metrics.report(actor, session_id)


@router.put(
    "/aggregation-consent",
    response_model=AggregationConsent,
    description="JWT participant changes only their own aggregation consent. Withdrawal removes coverage and affects every subsequent report. It does not change external text consent.",
)
def update_aggregation_consent(
    session_id: str, body: AggregationConsent, actor: Actor, request: Request
) -> AggregationConsent:
    """Revoke or restore participant consent; never restore erased coverage implicitly."""
    request.app.state.session_access.resolve_membership(actor, session_id)
    store = request.app.state.store
    participants = store.participants.get(session_id, {})
    participant = participants.get(actor.user_id)
    if participant is None or actor.role != "student":
        raise AppError(ErrorCode.FORBIDDEN, "Registered student participation is required.")
    state = request.app.state.learning_state
    with state.lock:
        participant.is_opted_in = body.is_allowed
        store.participants[session_id] = participants
        if not body.is_allowed:
            state.coverage = {
                key: value
                for key, value in state.coverage.items()
                if key[:2] != (session_id, actor.user_id)
            }
    return body
