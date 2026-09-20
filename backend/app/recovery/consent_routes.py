"""Typed feature routes; authentication and contract rules follow ADR 0002."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import (
    ExternalTextConsent,
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


@router.put(
    "/external-text-consent",
    response_model=ExternalTextConsent,
    description="JWT member updates only their own provider-specific permission. Separate from signal/aggregation consent. Revocation clears their recovery cache; previously exported external copies are not deleted.",
)
def update_external_consent(
    session_id: str, body: ExternalTextConsent, actor: Actor, request: Request
) -> ExternalTextConsent:
    """Record or revoke this member's explicit bounded-text processing permission."""
    request.app.state.session_access.resolve_membership(actor, session_id)
    state = request.app.state.learning_state
    with request.app.state.recovery_service.execution_lock, state.lock:
        key = (session_id, actor.user_id, body.provider)
        if body.is_allowed:
            if len(state.external_consent) >= state.maximum_records:
                raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, "Consent capacity reached.")
            state.external_consent.add(key)
        else:
            state.external_consent.discard(key)
            store = request.app.state.store
            owned = {
                key
                for key, record in store.recovery_cards.items()
                if record.owner_user_id == actor.user_id
                and record.card.session_id == session_id
            }
            for key in [
                key for key, value in store.recovery_cache.items() if value in owned
            ]:
                del store.recovery_cache[key]
    return body
