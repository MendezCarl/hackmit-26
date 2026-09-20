"""Demo routes: gated synthetic orchestration and token minting.

Both routes are unavailable outside explicit demo or test mode. The run uses
only synthetic fixtures; no external providers are contacted.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app.auth.tokens import (
    AuthenticatedActor,
    issue_access_token,
)
from app.config import DEMO_ENV, TEST_ENV
from app.core.errors import AppError, ErrorCode
from app.demo.runner import DemoRunner, DemoRunResult

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


class DemoTokenRequest(BaseModel):
    """Synthetic actor to mint a demo access token for."""

    user_id: str = Field(min_length=1, max_length=128)
    role: str = Field(description="``student`` or ``professor``.")
    course_id: str | None = Field(default=None, max_length=128)


class DemoTokenResponse(BaseModel):
    """Issued synthetic access token."""

    access_token: str = Field(description="Signed demo access token.")
    token_type: str = Field(default="bearer", description="Token type.")
    user_id: str = Field(description="Synthetic user id.")
    role: str = Field(description="Synthetic role.")


def get_demo_runner(request: Request) -> DemoRunner:
    """Resolve the demo runner from application state."""

    return request.app.state.demo_runner


def require_demo_mode(request: Request) -> None:
    """Reject demo access outside explicit demo or test mode."""

    settings = request.app.state.settings
    if settings.app_env not in (DEMO_ENV, TEST_ENV):
        raise AppError(
            ErrorCode.DEMO_UNAVAILABLE,
            "Demo helpers are only available in explicit demo or test mode.",
            details={"app_env": settings.app_env},
        )


@router.post(
    "/runs",
    response_model=DemoRunResult,
    status_code=status.HTTP_201_CREATED,
    summary="Run the synthetic end-to-end demo",
)
def run_demo(
    request: Request,
    runner: Annotated[DemoRunner, Depends(get_demo_runner)],
    _mode: Annotated[None, Depends(require_demo_mode)],
) -> DemoRunResult:
    """Execute the full synthetic recovery pipeline for demonstration."""

    if request.app.state.settings.app_env != DEMO_ENV:
        # Test mode may inspect services directly but never runs the demo.
        raise AppError(
            ErrorCode.DEMO_UNAVAILABLE,
            "Demo runs require APP_ENV=demo.",
            details={"app_env": request.app.state.settings.app_env},
        )
    return runner.run()


@router.post(
    "/token",
    response_model=DemoTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint a synthetic demo access token",
)
def mint_demo_token(
    request: Request,
    request_body: DemoTokenRequest,
    _mode: Annotated[None, Depends(require_demo_mode)],
) -> DemoTokenResponse:
    """Mint a short-lived token for a named synthetic actor."""

    if request_body.role not in ("student", "professor"):
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            "Demo token role must be student or professor.",
        )
    actor = AuthenticatedActor(
        user_id=request_body.user_id,
        role=request_body.role,
        course_id=request_body.course_id,
    )
    token = issue_access_token(request.app.state.settings, actor)
    return DemoTokenResponse(
        access_token=token,
        user_id=request_body.user_id,
        role=request_body.role,
    )
