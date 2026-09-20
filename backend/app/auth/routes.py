"""REST routes for account registration and login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.contracts.models import AuthSession, LoginRequest, RegisterUserRequest
from app.users.service import UserService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_user_service(request: Request) -> UserService:
    """Resolve the user service from application state."""

    return request.app.state.user_service


@router.post(
    "/register",
    response_model=AuthSession,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
)
def register(
    request_body: RegisterUserRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> AuthSession:
    """Create one account and issue its first access token.

    The role chosen here is embedded in future verified JWTs; roles never
    come from any other request body.
    """

    return service.register(request_body)


@router.post(
    "/login",
    response_model=AuthSession,
    summary="Log in to an existing account",
)
def login(
    request_body: LoginRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> AuthSession:
    """Verify credentials and issue a fresh access token."""

    return service.login(request_body)
