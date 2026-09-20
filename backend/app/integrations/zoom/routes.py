"""REST routes for the Zoom RTMS transcript integration.

The webhook route is authenticated by Zoom's HMAC signature rather than a
bearer token; session-scoped routes use the standard bearer dependency.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import ValidationError

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.core.errors import AppError, ErrorCode
from app.integrations.zoom.protocol import ZoomWebhookEvent
from app.integrations.zoom.service import (
    StartZoomRtmsRequest,
    ZoomRtmsService,
    ZoomRtmsStatus,
    ZoomUrlValidationResponse,
    ZoomWebhookAck,
)

router = APIRouter(prefix="/api/v1", tags=["zoom"])


def get_zoom_rtms_service(request: Request) -> ZoomRtmsService:
    """Resolve the Zoom RTMS service from application state."""

    return request.app.state.zoom_rtms_service


@router.post(
    "/integrations/zoom/webhooks",
    response_model=ZoomWebhookAck | ZoomUrlValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive verified Zoom RTMS lifecycle webhooks",
)
async def receive_zoom_webhook(
    request: Request,
    service: Annotated[ZoomRtmsService, Depends(get_zoom_rtms_service)],
) -> ZoomWebhookAck | ZoomUrlValidationResponse:
    """Verify a Zoom webhook signature, then start or stop the matching stream.

    Zoom authenticates deliveries with ``x-zm-signature`` and
    ``x-zm-request-timestamp``; unsigned, stale, or forged requests are
    rejected with ``unauthorized``. ``endpoint.url_validation`` returns the
    challenge answer; ``meeting.rtms_started`` opens a transcript-only stream
    for the active session bound to that meeting and ``meeting.rtms_stopped``
    closes it. No media bytes are accepted on this route.
    """

    raw_body = await request.body()
    service.verify_webhook(dict(request.headers), raw_body)
    try:
        event = ZoomWebhookEvent.model_validate_json(raw_body)
    except ValidationError as exc:
        raise AppError(
            ErrorCode.VALIDATION_FAILED, "Zoom webhook body is not a valid event."
        ) from exc
    return await service.handle_webhook(event)


@router.post(
    "/sessions/{session_id}/zoom/rtms/start",
    response_model=ZoomRtmsStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bind a session to its Zoom meeting for realtime transcripts",
)
def start_zoom_rtms(
    session_id: str,
    request_body: StartZoomRtmsRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[ZoomRtmsService, Depends(get_zoom_rtms_service)],
) -> ZoomRtmsStatus:
    """Record which Zoom meeting feeds this session and await its RTMS stream.

    Only the session owner may call this. The stream itself begins when Zoom
    delivers ``meeting.rtms_started`` for the bound meeting, so the response
    reports ``awaiting_stream`` until then.
    """

    return service.link_session(actor, session_id, request_body)


@router.get(
    "/sessions/{session_id}/zoom/status",
    response_model=ZoomRtmsStatus,
    summary="Read Zoom realtime transcript status for a session",
)
def read_zoom_status(
    session_id: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[ZoomRtmsService, Depends(get_zoom_rtms_service)],
) -> ZoomRtmsStatus:
    """Return the stream lifecycle state for any session member."""

    return service.read_status(actor, session_id)
