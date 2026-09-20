"""JWT access-token issuing and verification.

Uses the maintained ``PyJWT`` library; JWT handling is security-sensitive and
must not be reimplemented by hand. Identity and roles are always derived from
the verified token, never from request-body claims.
"""

from __future__ import annotations

import time

import jwt
from pydantic import BaseModel, Field

from app.config import Settings
from app.core.errors import AppError, ErrorCode

ROLE_STUDENT = "student"
ROLE_PROFESSOR = "professor"
KNOWN_ROLES = (ROLE_STUDENT, ROLE_PROFESSOR)


class AuthenticatedActor(BaseModel):
    """Identity resolved from a verified JWT; roles never come from bodies."""

    user_id: str = Field(min_length=1, description="Authenticated user identifier.")
    role: str = Field(description="Role: ``student`` or ``professor``.")
    course_id: str | None = Field(
        default=None, description="Course the actor teaches, for professors."
    )
    display_name: str | None = Field(default=None, description="Optional display name.")


def issue_access_token(settings: Settings, actor: AuthenticatedActor) -> str:
    """Sign a short-lived JWT for one actor.

    Args:
        settings: Application settings providing the secret and algorithm.
        actor: Identity and role embedded as verified claims.

    Returns:
        A signed JWT access token.
    """

    issued_at = int(time.time())
    claims: dict[str, object] = {
        "sub": actor.user_id,
        "role": actor.role,
        "iat": issued_at,
        "exp": issued_at + settings.jwt_ttl_seconds,
    }
    if actor.course_id is not None:
        claims["course_id"] = actor.course_id
    if actor.display_name is not None:
        claims["display_name"] = actor.display_name
    return jwt.encode(claims, settings.app_secret, algorithm=settings.jwt_algorithm)


def verify_access_token(settings: Settings, token: str) -> AuthenticatedActor:
    """Verify a JWT and resolve the authenticated actor.

    Args:
        settings: Application settings providing the secret and algorithm.
        token: Signed JWT from the ``Authorization`` header or WS query.

    Returns:
        The authenticated actor with identity and role from verified claims.

    Raises:
        AppError: ``unauthorized`` when the token is missing, expired, or invalid.
    """

    if not token:
        raise AppError(ErrorCode.UNAUTHORIZED, "Access token is required.")
    try:
        claims = jwt.decode(
            token,
            settings.app_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, "Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, "Access token is invalid.") from exc

    user_id = claims.get("sub")
    role = claims.get("role")
    if not isinstance(user_id, str) or not user_id:
        raise AppError(ErrorCode.UNAUTHORIZED, "Access token is missing a subject.")
    if role not in KNOWN_ROLES:
        raise AppError(ErrorCode.UNAUTHORIZED, "Access token has an unknown role.")

    course_id = claims.get("course_id")
    display_name = claims.get("display_name")
    return AuthenticatedActor(
        user_id=user_id,
        role=str(role),
        course_id=course_id if isinstance(course_id, str) else None,
        display_name=display_name if isinstance(display_name, str) else None,
    )
