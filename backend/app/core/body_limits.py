"""Bound derived JSON before parsing; media content types are never accepted."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ErrorCode, build_error_payload

MAX_REQUEST_BYTES = 1_048_576


class DerivedJsonLimit:
    """ASGI limit applies to chunked bodies as well as Content-Length requests."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the application without opening files, providers or request logs."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject oversized/non-JSON mutation bodies, otherwise replay bounded bytes."""
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
            block = message.get("body", b"")
            if len(body) + len(block) > MAX_REQUEST_BYTES:
                await JSONResponse(
                    build_error_payload(
                        ErrorCode.PAYLOAD_TOO_LARGE,
                        "Request exceeds the derived-data limit.",
                    ),
                    status_code=413,
                )(scope, receive, send)
                return
            body.extend(block)
            if not message.get("more_body", False):
                break
        content_type = (
            dict(scope.get("headers", []))
            .get(b"content-type", b"")
            .split(b";", 1)[0]
            .strip()
            .lower()
        )
        if body and content_type != b"application/json":
            await JSONResponse(
                build_error_payload(
                    ErrorCode.VALIDATION_FAILED,
                    "Only derived JSON payloads are accepted.",
                ),
                status_code=415,
            )(scope, receive, send)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
