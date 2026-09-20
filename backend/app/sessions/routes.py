"""REST routes for lecture-session lifecycle."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import (
    AvailableLectureSession,
    CreateSessionRequest,
    LectureSession,
)
from app.enrollments.service import EnrollmentService
from app.sessions.service import SessionService

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def get_session_service(request: Request) -> SessionService:
    """Resolve the session service from application state."""

    return request.app.state.session_service


def get_enrollment_service(request: Request) -> EnrollmentService:
    """Resolve the enrollment service from application state."""

    return request.app.state.enrollment_service


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
    "",
    response_model=list[LectureSession],
    summary="List owned lecture sessions",
)
def list_sessions(
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[SessionService, Depends(get_session_service)],
    lecture_id: str | None = None,
    course_id: str | None = None,
) -> list[LectureSession]:
    """List the authenticated professor's sessions with optional filters.

    Only professors can access this ownership-scoped list. Students receive a
    forbidden error. Results are ordered newest first by session start time.
    """

    return service.list_owned_sessions(actor, lecture_id, course_id)


@router.get(
    "/available",
    response_model=list[AvailableLectureSession],
    summary="List live sessions I can join without a code",
)
def list_available_sessions(
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[EnrollmentService, Depends(get_enrollment_service)],
    zoom_meeting_id: str | None = None,
) -> list[AvailableLectureSession]:
    """List active sessions matched to the student by enrollment or Zoom meeting.

    A session is included when its course is one of the caller's enrollments
    or when ``zoom_meeting_id`` equals the session's Zoom meeting id. Each
    match reports whether the caller already joined and whether the enrollment
    allows joining without a prompt. Results are newest first.
    """

    response.headers["Cache-Control"] = "no-store"
    return service.list_available_sessions(actor, zoom_meeting_id)


@router.get(
    "/by-join-code/{join_code}",
    response_model=LectureSession,
    summary="Resolve a join code",
)
def resolve_join_code(
    join_code: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[SessionService, Depends(get_session_service)],
) -> LectureSession:
    """Resolve a student-entered code to an active lecture session.

    Authentication is required, but the lookup is not restricted to session
    membership. Whitespace and lowercase input are normalized. Unknown codes
    and codes for inactive sessions return a not-found error.
    """

    return service.resolve_join_code(actor, join_code)


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
    description="Session-owner JWT required. End the session idempotently; late student and delivery observations are rejected. Publishes `session.ended` to session subscribers and closes any Zoom RTMS transcript stream.",
)
async def end_session(
    session_id: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    request: Request,
) -> LectureSession:
    """Finalize the trusted session lifecycle without accepting a client clock origin.

    Ending also closes any Zoom RTMS transcript stream bound to the session so
    no further provider transcript is received for an ended lecture.
    """
    from app.core.errors import AppError, ErrorCode

    session = request.app.state.session_service.get_session(actor, session_id)
    if session.owner_id != actor.user_id:
        raise AppError(ErrorCode.FORBIDDEN, "Only the session owner can end the session.")
    ended = request.app.state.session_service.end_session(session_id)
    await request.app.state.zoom_rtms_service.stop_session(session_id)
    return ended
