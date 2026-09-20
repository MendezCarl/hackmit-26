"""Lecture-session lifecycle: creation and retrieval.

``lecture_id`` identifies the lecture record; ``session_id`` identifies one
running occurrence. Both appear where required and are validated to match;
they are never used interchangeably.
"""

from __future__ import annotations

from uuid import uuid4

from app.auth.access import SessionAccess
from app.auth.tokens import AuthenticatedActor
from app.config import Settings
from app.contracts.models import CreateSessionRequest, LectureSession, SessionStatus
from app.core.clock import utc_now_iso
from app.storage.in_memory import InMemoryStore


class SessionService:
    """Creation and retrieval of lecture sessions on one shared clock."""

    def __init__(self, store: InMemoryStore, settings: Settings, session_access: SessionAccess) -> None:
        """Bind the service to shared storage, settings, and access resolution.

        Args:
            store: Injected storage connections.
            settings: Application settings.
            session_access: Shared membership resolver.
        """

        self._store = store
        self._settings = settings
        self._session_access = session_access

    def create_session(
        self, actor: AuthenticatedActor, request: CreateSessionRequest
    ) -> LectureSession:
        """Create one running occurrence of a lecture.

        Args:
            actor: Authenticated user who becomes the session owner.
            request: Validated session-creation payload.

        Returns:
            The created, active lecture session.
        """

        session_id = f"session_{uuid4().hex}"
        clock_origin = utc_now_iso()
        session = LectureSession(
            session_id=session_id,
            lecture_id=request.lecture_id,
            owner_id=actor.user_id,
            course_id=request.course_id,
            title=request.title,
            mode=request.mode,
            status=SessionStatus.ACTIVE,
            started_at=clock_origin,
            session_clock_origin=clock_origin,
            zoom_meeting_id=request.zoom_meeting_id,
        )
        self._store.sessions[session_id] = session
        return session

    def get_session(
        self, actor: AuthenticatedActor, session_id: str
    ) -> LectureSession:
        """Return a session for an authorized member.

        Args:
            actor: Authenticated actor requesting the session.
            session_id: Session to retrieve.

        Returns:
            The lecture session record.

        Raises:
            AppError: ``not_found`` or ``forbidden`` via membership resolution.
        """

        membership = self._session_access.resolve_membership(actor, session_id)
        return self._store.sessions[membership.session_id]
