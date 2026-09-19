"""Transcript-only WebSocket ingestion with reauthorization and bounded messages."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.timeline.contracts import (
    ErrorDetail,
    ErrorResponse,
    EventEnvelope,
    FeatureError,
    Identifier,
)
from app.timeline.dependencies import get_services
from app.timeline.http import MAX_REQUEST_BYTES
from app.transcript.models import TranscriptMessage

router = APIRouter()
IDLE_TIMEOUT_SECONDS = 60


@router.websocket("/ws/v1/sessions/{session_id}")
async def ingest_transcript_socket(socket: WebSocket, session_id: Identifier) -> None:
    """Accept only authorized producer JSON, acknowledge writes, and redact failures.

    Bearer credentials use the upgrade header, never a query string. Binary frames
    close with 1003, oversized frames with 1009, authorization failures with 1008.
    This feature does not broadcast students' signals or implement general live UI.
    """
    services = get_services(socket)
    authorization = socket.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or socket.query_params:
        await socket.close(code=1008)
        return
    try:
        grant = await services.access.authorize(token, session_id)
        if grant.session_id != session_id or not grant.can_transcribe:
            raise FeatureError("forbidden", "Producer access is required.", 403)
    except FeatureError:
        await socket.close(code=1008)
        return
    await socket.accept()
    sequence = 0
    try:
        while True:
            try:
                message = await asyncio.wait_for(socket.receive(), IDLE_TIMEOUT_SECONDS)
            except TimeoutError:
                await socket.close(code=1000)
                return
            if message["type"] == "websocket.disconnect":
                return
            text = message.get("text")
            if text is None:
                await socket.close(code=1003)
                return
            if len(text.encode("utf-8")) > MAX_REQUEST_BYTES:
                await socket.close(code=1009)
                return
            sequence += 1
            try:
                grant = await services.access.authorize(token, session_id)
                if grant.session_id != session_id or not grant.can_transcribe:
                    raise FeatureError("forbidden", "Producer access is required.", 403)
                submitted = TranscriptMessage.model_validate_json(text)
                receipt = await services.transcripts.ingest(grant, submitted.payload)
                envelope = EventEnvelope(
                    event_id=uuid4().hex,
                    event_type="transcript.batch.accepted",
                    session_id=session_id,
                    occurred_at=datetime.now(UTC),
                    sequence_number=sequence,
                    payload=receipt,
                )
            except (ValidationError, FeatureError) as error:
                if isinstance(error, FeatureError) and error.status_code in {401, 403}:
                    await socket.close(code=1008)
                    return
                detail = ErrorDetail(
                    code=error.code
                    if isinstance(error, FeatureError)
                    else "invalid_request",
                    message=error.message
                    if isinstance(error, FeatureError)
                    else "Request fields are invalid.",
                    request_id=uuid4().hex,
                )
                envelope = EventEnvelope(
                    event_id=uuid4().hex,
                    event_type="error.occurred",
                    session_id=session_id,
                    occurred_at=datetime.now(UTC),
                    sequence_number=sequence,
                    payload=ErrorResponse(error=detail),
                )
            await socket.send_json(envelope.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
