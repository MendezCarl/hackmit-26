"""Resolution of authenticated actors into session membership and consent.

``SessionAccess`` is the frozen shared interface both workstreams consume.
It resolves the actor, session membership, role, consent state, and the
session clock origin from server-side records, never from request bodies.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.auth.tokens import ROLE_PROFESSOR, AuthenticatedActor
from app.core.errors import AppError, ErrorCode
from app.storage.in_memory import InMemoryStore

SESSION_ROLE_OWNER: Literal["owner"] = "owner"
SESSION_ROLE_PARTICIPANT: Literal["participant"] = "participant"
SESSION_ROLE_COURSE_PROFESSOR: Literal["course_professor"] = "course_professor"
SessionRole = Literal["owner", "participant", "course_professor"]


class SessionMembership(BaseModel):
    """Resolved membership of one authenticated actor for one session."""

    session_id: str = Field(description="Session the actor resolved into.")
    actor: AuthenticatedActor = Field(description="Authenticated actor.")
    session_role: SessionRole = Field(
        description="``owner``, ``participant``, or ``course_professor``."
    )
    is_opted_in: bool = Field(
        description="Whether the actor consented to anonymous aggregation."
    )


class SessionAccess(Protocol):
    """Frozen interface resolving actor, membership, role, and consent."""

    def resolve_membership(
        self, actor: AuthenticatedActor, session_id: str
    ) -> SessionMembership:
        """Resolve the actor's membership for the session.

        Args:
            actor: Authenticated actor from a verified JWT.
            session_id: Session to resolve membership for.

        Returns:
            The resolved membership with role and consent state.

        Raises:
            AppError: ``not_found`` for unknown sessions and ``forbidden``
                when the actor has no relationship with the session.
        """
        ...


class StoreSessionAccess:
    """SessionAccess implementation backed by the injected in-memory store."""

    def __init__(self, store: InMemoryStore) -> None:
        """Bind the resolver to the shared store.

        Args:
            store: Injected storage connections used for membership lookup.
        """

        self._store = store

    def resolve_membership(
        self, actor: AuthenticatedActor, session_id: str
    ) -> SessionMembership:
        """Resolve membership using server-side session and consent records.

        Args:
            actor: Authenticated actor from a verified JWT.
            session_id: Session to resolve membership for.

        Returns:
            The resolved membership with role and consent state.

        Raises:
            AppError: ``not_found`` for unknown sessions and ``forbidden``
                when the actor has no relationship with the session.
        """

        session = self._store.sessions.get(session_id)
        if session is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Lecture session was not found.",
                details={"session_id": session_id},
            )

        if session.owner_id == actor.user_id:
            return SessionMembership(
                session_id=session_id,
                actor=actor,
                session_role=SESSION_ROLE_OWNER,
                is_opted_in=True,
            )

        participant = self._store.participants.get(session_id, {}).get(actor.user_id)
        if participant is not None:
            return SessionMembership(
                session_id=session_id,
                actor=actor,
                session_role=SESSION_ROLE_PARTICIPANT,
                is_opted_in=participant.is_opted_in,
            )

        if (
            actor.role == ROLE_PROFESSOR
            and actor.course_id is not None
            and actor.course_id == session.course_id
        ):
            return SessionMembership(
                session_id=session_id,
                actor=actor,
                session_role=SESSION_ROLE_COURSE_PROFESSOR,
                is_opted_in=False,
            )

        raise AppError(
            ErrorCode.FORBIDDEN,
            "This account is not a member of the lecture session.",
            details={"session_id": session_id},
        )
