"""REST routes for lecture-session lifecycle."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import CreateSessionRequest, LectureSession
from app.sessions.service import SessionService

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def get_session_service(request: Request) -> SessionService:
    """Resolve the session service from application state."""

    return request.app.state.session_service


@router.post(
    "",
    response_model=LectureSession,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lecture session",
)
def create_session(
    request_body: CreateSessionRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[SessionService, Depends(get_session_service)],
) -> LectureSession:
    """Start one running occurrence of a lecture on the shared clock.

    The authenticated user becomes the session owner. The ``lecture_id``
    identifies the lecture record and the returned ``session_id`` identifies
    this occurrence.
    """

    return service.create_session(actor, request_body)


@router.get(
    "/{session_id}",
    response_model=LectureSession,
    summary="Retrieve a lecture session",
)
def read_session(
    session_id: str,
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[SessionService, Depends(get_session_service)],
) -> LectureSession:
    """Return the session for an authenticated owner, participant, or professor."""

    session = service.get_session(actor, session_id)
    response.headers["Cache-Control"] = "no-store"
    return session


@router.post(
    "/{session_id}/end",
    response_model=LectureSession,
    description="Session-owner JWT required. End the session idempotently; late student and delivery observations are rejected.",
)
def end_session(
    session_id: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    request: Request,
) -> LectureSession:
    """Finalize the trusted session lifecycle without accepting a client clock origin."""
    from app.contracts.models import SessionStatus
    from app.core.clock import utc_now_iso
    from app.core.errors import AppError, ErrorCode

    session = request.app.state.session_service.get_session(actor, session_id)
    if session.owner_id != actor.user_id:
        raise AppError(
            ErrorCode.FORBIDDEN, "Only the session owner can end the session."
        )
    if session.status != SessionStatus.ENDED:
        session.status = SessionStatus.ENDED
        session.ended_at = utc_now_iso()
    return session
