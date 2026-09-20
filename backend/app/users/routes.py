"""REST routes for user profiles and consent settings."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import ConsentSettings, UpdateConsentRequest, UserProfile
from app.users.service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def get_user_service(request: Request) -> UserService:
    """Resolve the user service from application state."""

    return request.app.state.user_service


@router.get(
    "/me",
    response_model=UserProfile,
    summary="Read the authenticated account",
)
def read_current_user(
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserProfile:
    """Return the authenticated account's public profile."""

    response.headers["Cache-Control"] = "no-store"
    return service.read_profile(actor)


@router.get(
    "/me/consent",
    response_model=ConsentSettings,
    summary="Read stored consent settings",
)
def read_consent(
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> ConsentSettings:
    """Return the authenticated account's consent choices."""

    response.headers["Cache-Control"] = "no-store"
    return service.read_consent(actor)


@router.put(
    "/me/consent",
    response_model=ConsentSettings,
    summary="Update stored consent settings",
)
def update_consent(
    request_body: UpdateConsentRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> ConsentSettings:
    """Store the account's analytics opt-in choice."""

    return service.update_consent(actor, request_body)
