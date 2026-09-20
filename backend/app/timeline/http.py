"""Feature-scoped safe errors and bounded JSON bodies without altering host routes."""

from collections.abc import Callable, Coroutine
from typing import Any
from uuid import uuid4

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.timeline.contracts import ErrorDetail, ErrorResponse, FeatureError

MAX_REQUEST_BYTES = 256_000
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in {
        400: "Invalid interval, identifiers, or feature request.",
        401: "Missing or invalid host bearer token.",
        403: "Session access, role, consent, or selected-folder scope denied.",
        404: "Authorized resource not found.",
        409: "Conflicting revision or invalid session state.",
        413: "Body, batch, or feature storage capacity exceeded.",
        415: "Only bounded JSON and supported derived text are accepted.",
        422: "Invalid typed payload; supplied values are never echoed.",
        502: "Provider failure; external details are redacted.",
        503: "Required host dependency or approved privacy policy is unavailable.",
    }.items()
}


def error_response(error: FeatureError) -> JSONResponse:
    """Serialize a stable safe error, excluding request bodies and provider details."""
    payload = ErrorResponse(
        error=ErrorDetail(code=error.code, message=error.message, request_id=uuid4().hex)
    )
    return JSONResponse(
        status_code=error.status_code, content=payload.model_dump(mode="json")
    )


class FeatureRoute(APIRoute):
    """Keep standard errors local to these routes rather than overriding Person A's handlers."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Wrap validation/domain failures without echoing potentially private input."""
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)
            except FeatureError as error:
                return error_response(error)
            except (RequestValidationError, ValidationError):
                return error_response(
                    FeatureError("invalid_request", "Request fields are invalid.", 422)
                )

        return guarded


class BoundedJsonMiddleware:
    """Cap feature request bytes before JSON decoding, including chunked transfers."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the standalone feature app; hosts must enforce equivalent ingress limits."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Buffer bounded HTTP bodies, reject media, and pass through WebSockets."""
        if scope["type"] != "http" or scope.get("method") not in {
            "POST",
            "PUT",
            "PATCH",
        }:
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_REQUEST_BYTES:
                await error_response(
                    FeatureError(
                        "request_too_large", "Request body exceeds the size limit.", 413
                    )
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
        if body and content_type != b"application/json":
            await error_response(
                FeatureError(
                    "unsupported_media_type",
                    "Only JSON derived-data payloads are accepted.",
                    415,
                )
            )(scope, receive, send)
            return
        has_delivered = False

        async def replay() -> Message:
            nonlocal has_delivered
            if not has_delivered:
                has_delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
