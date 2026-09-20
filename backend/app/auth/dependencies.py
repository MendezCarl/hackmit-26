"""Reusable FastAPI authentication dependencies for feature routers."""

from __future__ import annotations

from fastapi import Request

from app.auth.tokens import AuthenticatedActor, verify_access_token

BEARER_PREFIX = "Bearer "


def get_current_actor(request: Request) -> AuthenticatedActor:
    """Resolve the authenticated actor from the ``Authorization`` header.

    Args:
        request: Incoming request carrying application state.

    Returns:
        The actor resolved from the verified JWT.

    Raises:
        AppError: ``unauthorized`` when the bearer token is missing or invalid.
    """

    authorization = request.headers.get("authorization", "")
    if not authorization.startswith(BEARER_PREFIX):
        from app.core.errors import AppError, ErrorCode

        raise AppError(ErrorCode.UNAUTHORIZED, "A bearer access token is required.")
    token = authorization[len(BEARER_PREFIX) :]
    return verify_access_token(request.app.state.settings, token)
