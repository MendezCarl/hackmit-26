"""Lecture-session lifecycle: creation and retrieval.

``lecture_id`` identifies the lecture record; ``session_id`` identifies one
running occurrence. Both appear where required and are validated to match;
they are never used interchangeably.
"""

from __future__ import annotations

from uuid import uuid4

from app.auth.access import SessionAccess
from app.auth.tokens import ROLE_PROFESSOR, AuthenticatedActor
from app.config import Settings
from app.contracts.models import CreateSessionRequest, LectureSession, SessionStatus
from app.core.clock import utc_now_iso
from app.core.errors import AppError, ErrorCode
from app.sessions.join_codes import generate_join_code, normalize_join_code
from app.storage.in_memory import InMemoryStore
from app.ws.publisher import EventPublisher

SESSION_ENDED_EVENT = "session.ended"


class SessionService:
    """Creation and retrieval of lecture sessions on one shared clock."""

    def __init__(
        self,
        store: InMemoryStore,
        settings: Settings,
        session_access: SessionAccess,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        """Bind the service to shared storage, settings, and access resolution.

        Args:
            store: Injected storage connections.
            settings: Application settings.
            session_access: Shared membership resolver.
            event_publisher: Publisher notified when a session ends; optional so
                offline scenarios (demo runner) need no socket infrastructure.
        """

        self._store = store
        self._settings = settings
        self._session_access = session_access
        self._publisher = event_publisher

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
        join_code = generate_join_code(lambda code: code in self._store.session_join_codes)
        clock_origin = utc_now_iso()
        session = LectureSession(
            session_id=session_id,
            lecture_id=request.lecture_id,
            owner_id=actor.user_id,
            course_id=request.course_id,
            title=request.title,
            join_code=join_code,
            mode=request.mode,
            status=SessionStatus.ACTIVE,
            started_at=clock_origin,
            session_clock_origin=clock_origin,
            zoom_meeting_id=request.zoom_meeting_id,
        )
        self._store.sessions[session_id] = session
        self._store.session_join_codes[join_code] = session_id
        return session

    def resolve_join_code(self, actor: AuthenticatedActor, raw_code: str) -> LectureSession:
        """Resolve a normalized join code to an active lecture session.

        Args:
            actor: Any authenticated account requesting the lookup.
            raw_code: User-entered join code, including possible whitespace or
                lowercase characters.

        Returns:
            The active lecture session associated with the code.

        Raises:
            AppError: If the code is unknown or no longer points to an active
                session.
        """
        del actor
        code = normalize_join_code(raw_code)
        session_id = self._store.session_join_codes.get(code)
        session = self._store.sessions.get(session_id) if session_id else None
        if session is None or session.status != SessionStatus.ACTIVE:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "No active lecture session matches that join code.",
                details={"join_code": code},
            )
        return session

    def get_session(self, actor: AuthenticatedActor, session_id: str) -> LectureSession:
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

    def list_owned_sessions(
        self,
        actor: AuthenticatedActor,
        lecture_id: str | None = None,
        course_id: str | None = None,
    ) -> list[LectureSession]:
        """List professor-owned lecture sessions with optional filters.

        Args:
            actor: Authenticated professor requesting owned sessions.
            lecture_id: Optional lecture identifier filter.
            course_id: Optional course identifier filter.

        Returns:
            Sessions owned by the professor, newest first.

        Raises:
            AppError: If the actor is not a professor.
        """
        if actor.role != ROLE_PROFESSOR:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Only professors can list owned lecture sessions.",
            )
        return sorted(
            (
                session
                for session in self._store.sessions.values()
                if session.owner_id == actor.user_id
                and (lecture_id is None or session.lecture_id == lecture_id)
                and (course_id is None or session.course_id == course_id)
            ),
            key=lambda session: session.started_at,
            reverse=True,
        )

    def end_session(self, session_id: str) -> LectureSession:
        """End one session and persist the changed session record.

        Args:
            session_id: Session to finalize.

        Returns:
            The persisted ended session.

        Raises:
            KeyError: If the session does not exist.

        Side effects:
            Publishes one ``session.ended`` event to session subscribers the
            first time the session transitions to ended.
        """

        session = self._store.sessions[session_id]
        if session.status != SessionStatus.ENDED:
            session.status = SessionStatus.ENDED
            session.ended_at = utc_now_iso()
            self._store.sessions[session_id] = session
            self._store.session_join_codes.pop(session.join_code, None)
            if self._publisher is not None:
                self._publisher.publish(
                    self._publisher.build_envelope(
                        session_id, SESSION_ENDED_EVENT, session.model_dump(mode="json")
                    )
                )
        return session
