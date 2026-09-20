"""Transcript-only Zoom RTMS stream client.

One ``ZoomRtmsTranscriptStream`` owns a signaling connection and a transcript
media connection for a single ``rtms_stream_id``. It performs the documented
handshake, answers keep-alives, and hands validated transcript messages to a
callback. Audio, video, share, and chat media are never requested.

Connections are created through an injected ``RtmsConnector`` so tests drive
the protocol with in-memory fakes instead of Zoom servers.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.integrations.zoom.protocol import (
    RTMS_STATUS_OK,
    RtmsMediaHandshakeResponse,
    RtmsMessageType,
    RtmsSignalingHandshakeResponse,
    RtmsStreamState,
    RtmsTranscriptMessage,
    ZoomProtocolError,
    build_client_ready_ack,
    build_keep_alive_response,
    build_signaling_handshake,
    build_stream_close_request,
    build_transcript_media_handshake,
    generate_rtms_signature,
    parse_transcript_message,
)

LOGGER = logging.getLogger("app.integrations.zoom")
HANDSHAKE_TIMEOUT_SECONDS = 15.0
# Zoom sends keep-alives every 10 s; silence past this bound means the link is dead.
IDLE_TIMEOUT_SECONDS = 65.0


class RtmsStreamClosed(Exception):
    """The remote side closed an RTMS connection."""


class RtmsHandshakeError(Exception):
    """The RTMS server rejected a handshake or answered with an unusable shape."""


class RtmsConnection(Protocol):
    """Minimal duplex text connection used by the stream client."""

    async def send(self, message: str) -> None:
        """Send one text frame."""
        ...

    async def recv(self) -> str | bytes:
        """Receive one frame.

        Raises:
            RtmsStreamClosed: When the peer closed the connection.
        """
        ...

    async def close(self) -> None:
        """Close the connection; safe to call more than once."""
        ...


RtmsConnector = Callable[[str], Awaitable[RtmsConnection]]
TranscriptHandler = Callable[[RtmsTranscriptMessage], Awaitable[None]]
StateHandler = Callable[[str], None]

STATE_CONNECTING = "connecting"
STATE_STREAMING = "streaming"
STATE_STOPPED = "stopped"


class WebsocketsRtmsConnection:
    """Adapter translating ``websockets`` closure errors into ``RtmsStreamClosed``."""

    def __init__(self, websocket: Any) -> None:
        """Wrap an open ``websockets`` client connection."""

        self._websocket = websocket

    async def send(self, message: str) -> None:
        """Send one text frame, mapping closure to ``RtmsStreamClosed``."""

        from websockets.exceptions import ConnectionClosed

        try:
            await self._websocket.send(message)
        except ConnectionClosed as exc:
            raise RtmsStreamClosed(str(exc.code)) from exc

    async def recv(self) -> str | bytes:
        """Receive one frame, mapping closure to ``RtmsStreamClosed``."""

        from websockets.exceptions import ConnectionClosed

        try:
            frame: str | bytes = await self._websocket.recv()
        except ConnectionClosed as exc:
            raise RtmsStreamClosed(str(exc.code)) from exc
        return frame

    async def close(self) -> None:
        """Close the underlying connection."""

        await self._websocket.close()


async def connect_with_websockets(url: str) -> RtmsConnection:
    """Default connector opening a TLS WebSocket with the ``websockets`` library.

    Args:
        url: ``wss://`` URL provided by Zoom.

    Returns:
        A connection adapter ready for the handshake.
    """

    import websockets

    websocket = await websockets.connect(url, open_timeout=HANDSHAKE_TIMEOUT_SECONDS)
    return WebsocketsRtmsConnection(websocket)


def _decode_frame(frame: str | bytes) -> dict[str, Any] | None:
    """Decode one JSON text frame; return None for non-object payloads."""

    try:
        decoded = json.loads(frame)
    except ValueError, UnicodeDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


class ZoomRtmsTranscriptStream:
    """Signaling plus transcript media connections for one RTMS stream."""

    def __init__(
        self,
        *,
        meeting_uuid: str,
        rtms_stream_id: str,
        signaling_url: str,
        client_id: str,
        client_secret: str,
        on_transcript: TranscriptHandler,
        connector: RtmsConnector = connect_with_websockets,
        on_state_change: StateHandler | None = None,
    ) -> None:
        """Prepare a stream; nothing connects until ``run`` is awaited.

        Args:
            meeting_uuid: Meeting UUID from ``meeting.rtms_started``.
            rtms_stream_id: Stream id from ``meeting.rtms_started``.
            signaling_url: ``server_urls`` value from the webhook.
            client_id: Zoom app client id used in the handshake signature.
            client_secret: Zoom app client secret; never logged.
            on_transcript: Awaited for every validated transcript message.
            connector: Opens connections; injected for tests.
            on_state_change: Optional observer of connecting/streaming/stopped.
        """

        self._meeting_uuid = meeting_uuid
        self._rtms_stream_id = rtms_stream_id
        self._signaling_url = signaling_url
        self._signature = generate_rtms_signature(
            client_id, client_secret, meeting_uuid, rtms_stream_id
        )
        self._on_transcript = on_transcript
        self._connector = connector
        self._on_state_change = on_state_change
        self._signaling: RtmsConnection | None = None
        self._media: RtmsConnection | None = None
        self._stop_requested = asyncio.Event()

    @property
    def rtms_stream_id(self) -> str:
        """Stream identifier this client is bound to."""

        return self._rtms_stream_id

    def _set_state(self, state: str) -> None:
        if self._on_state_change is not None:
            self._on_state_change(state)

    async def run(self) -> None:
        """Handshake, then pump both connections until closed or stopped.

        Raises:
            RtmsHandshakeError: When either handshake is rejected or times out.
            RtmsStreamClosed: When a connection closes during the handshake.
        """

        self._set_state(STATE_CONNECTING)
        try:
            self._signaling = await self._connector(self._signaling_url)
            media_url = await self._complete_signaling_handshake(self._signaling)
            self._media = await self._connector(media_url)
            await self._complete_media_handshake(self._media)
            await self._send(self._signaling, build_client_ready_ack(self._rtms_stream_id))
            self._set_state(STATE_STREAMING)
            await self._pump_until_closed(self._signaling, self._media)
        finally:
            await self._close_connections()
            self._set_state(STATE_STOPPED)

    async def stop(self) -> None:
        """Request a graceful close and release both connections."""

        self._stop_requested.set()
        if self._signaling is not None:
            with contextlib.suppress(RtmsStreamClosed):
                await self._send(
                    self._signaling, build_stream_close_request(self._rtms_stream_id)
                )
        await self._close_connections()

    async def _close_connections(self) -> None:
        for connection in (self._media, self._signaling):
            if connection is not None:
                try:
                    await connection.close()
                except Exception:  # noqa: BLE001 - closing must never raise.
                    LOGGER.debug("RTMS connection close failed", exc_info=True)
        self._media = None
        self._signaling = None

    async def _send(self, connection: RtmsConnection, message: dict[str, Any]) -> None:
        await connection.send(json.dumps(message))

    async def _receive_message(
        self, connection: RtmsConnection, timeout_seconds: float
    ) -> dict[str, Any]:
        """Receive one decoded object, answering keep-alives transparently."""

        while True:
            frame = await asyncio.wait_for(connection.recv(), timeout=timeout_seconds)
            message = _decode_frame(frame)
            if message is None:
                continue
            if message.get("msg_type") == RtmsMessageType.KEEP_ALIVE_REQ:
                timestamp = message.get("timestamp")
                if isinstance(timestamp, int):
                    await self._send(connection, build_keep_alive_response(timestamp))
                continue
            return message

    async def _complete_signaling_handshake(self, signaling: RtmsConnection) -> str:
        await self._send(
            signaling,
            build_signaling_handshake(
                self._meeting_uuid, self._rtms_stream_id, self._signature
            ),
        )
        response = await self._await_message_type(
            signaling, RtmsMessageType.SIGNALING_HAND_SHAKE_RESP
        )
        parsed = RtmsSignalingHandshakeResponse.model_validate(response)
        if parsed.status_code != RTMS_STATUS_OK:
            raise RtmsHandshakeError(
                f"Signaling handshake rejected with status {parsed.status_code}."
            )
        media_url = parsed.transcript_media_url()
        if media_url is None:
            raise RtmsHandshakeError(
                "Signaling handshake returned no transcript media URL."
            )
        return media_url

    async def _complete_media_handshake(self, media: RtmsConnection) -> None:
        await self._send(
            media,
            build_transcript_media_handshake(
                self._meeting_uuid, self._rtms_stream_id, self._signature
            ),
        )
        response = await self._await_message_type(
            media, RtmsMessageType.DATA_HAND_SHAKE_RESP
        )
        parsed = RtmsMediaHandshakeResponse.model_validate(response)
        if parsed.status_code != RTMS_STATUS_OK:
            raise RtmsHandshakeError(
                f"Media handshake rejected with status {parsed.status_code}."
            )

    async def _await_message_type(
        self, connection: RtmsConnection, expected: RtmsMessageType
    ) -> dict[str, Any]:
        try:
            while True:
                message = await self._receive_message(connection, HANDSHAKE_TIMEOUT_SECONDS)
                if message.get("msg_type") == expected:
                    return message
        except TimeoutError as exc:
            raise RtmsHandshakeError(f"Timed out waiting for msg_type {expected}.") from exc

    async def _pump_until_closed(
        self, signaling: RtmsConnection, media: RtmsConnection
    ) -> None:
        pumps = [
            asyncio.ensure_future(self._pump_signaling(signaling)),
            asyncio.ensure_future(self._pump_media(media)),
            asyncio.ensure_future(self._stop_requested.wait()),
        ]
        try:
            await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)

    async def _pump_signaling(self, signaling: RtmsConnection) -> None:
        try:
            while True:
                message = await self._receive_message(signaling, IDLE_TIMEOUT_SECONDS)
                if message.get("msg_type") == RtmsMessageType.STREAM_STATE_UPDATE and (
                    message.get("state") == RtmsStreamState.TERMINATED
                ):
                    return
        except RtmsStreamClosed, TimeoutError:
            return

    async def _pump_media(self, media: RtmsConnection) -> None:
        try:
            while True:
                message = await self._receive_message(media, IDLE_TIMEOUT_SECONDS)
                if message.get("msg_type") != RtmsMessageType.MEDIA_DATA_TRANSCRIPT:
                    continue
                try:
                    transcript = parse_transcript_message(message)
                except ZoomProtocolError:
                    LOGGER.warning("Dropped malformed RTMS transcript message.")
                    continue
                await self._on_transcript(transcript)
        except RtmsStreamClosed, TimeoutError:
            return
