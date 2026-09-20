"""Authenticated WebSocket transport for session-scoped events.

Connections are authorized by JWT and session membership before any event is
delivered. The publisher's bounded, per-subscriber queues drop the oldest
envelopes when a client falls behind.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.tokens import verify_access_token
from app.core.errors import AppError
from app.ws.publisher import WebSocketEventPublisher

router = APIRouter()
POLL_INTERVAL_SECONDS = 0.05
WS_UNAUTHORIZED_CLOSE_CODE = 4401
SESSION_CONNECTED_EVENT = "session.connected"
CLIENT_HEARTBEAT_EVENT = "client.heartbeat"


def _receive_client_message(websocket: WebSocket) -> asyncio.Task[str]:
    """Create a receive task for one client message."""

    return asyncio.create_task(websocket.receive_text())


async def _drain_queued_envelope(websocket: WebSocket, queue: asyncio.Queue[Any]) -> bool:
    """Forward queued envelopes until the queue is momentarily empty.

    Args:
        websocket: Authorized client connection.
        queue: This subscriber's bounded queue.

    Returns:
        True when at least one envelope was delivered in this drain pass.
    """

    delivered_any = False
    while True:
        try:
            envelope = queue.get_nowait()
        except asyncio.QueueEmpty:
            return delivered_any
        await websocket.send_text(envelope.model_dump_json())
        delivered_any = True


async def _wait_briefly_for_client_message(
    websocket: WebSocket, queue: asyncio.Queue[Any]
) -> None:
    """Wait briefly for a client message, tolerating heartbeats.

    Args:
        websocket: Authorized client connection.
        queue: This subscriber's bounded queue, re-checked after messages.
    """

    receive_task = _receive_client_message(websocket)
    done, _pending = await asyncio.wait({receive_task}, timeout=POLL_INTERVAL_SECONDS)
    if receive_task in done:
        receive_task.result()
        # Client messages (heartbeats) are accepted and never answered with
        # per-user data; the queue is re-checked immediately afterwards.
        if await _drain_queued_envelope(websocket, queue):
            return
    else:
        receive_task.cancel()
        # CancelledError derives from BaseException and must be listed
        # explicitly; letting it escape would terminate the connection.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await receive_task


@router.websocket("/ws/v1/sessions/{session_id}")
async def connect_session_events(websocket: WebSocket, session_id: str) -> None:
    """Authorize and stream session events to one WebSocket client.

    Args:
        websocket: Incoming client connection.
        session_id: Session whose events the client subscribes to.

    The client must present a valid JWT whose subject is an owner,
    participant, or course professor for the session. Unauthorized
    connections are closed before any session data is sent.
    """

    settings = websocket.app.state.settings
    publisher: WebSocketEventPublisher = websocket.app.state.event_publisher
    token = websocket.query_params.get("token", "")
    try:
        actor = verify_access_token(settings, token)
        session_access = websocket.app.state.session_access
        session_access.resolve_membership(actor, session_id)
    except AppError:
        await websocket.close(code=WS_UNAUTHORIZED_CLOSE_CODE)
        return

    await websocket.accept()
    queue = publisher.subscribe(session_id, actor.user_id)
    welcome = publisher.build_envelope(
        session_id,
        SESSION_CONNECTED_EVENT,
        {"user_id": actor.user_id, "role": actor.role},
    )
    await websocket.send_text(welcome.model_dump_json())
    try:
        while True:
            verify_access_token(settings, token)
            session_access.resolve_membership(actor, session_id)
            if await _drain_queued_envelope(websocket, queue):
                continue
            await _wait_briefly_for_client_message(websocket, queue)
    except (WebSocketDisconnect, AppError):
        pass
    finally:
        publisher.unsubscribe(session_id, queue)
