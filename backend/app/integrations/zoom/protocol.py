"""Pure parsing, signing, and mapping for the Zoom RTMS transcript protocol.

Message shapes follow the Zoom RTMS event reference
(https://developers.zoom.us/docs/rtms/event-reference/) and the Zoom webhook
verification guide (https://developers.zoom.us/docs/api/webhooks/). This module
performs no I/O; the stream client and service own connections and storage.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.contracts.models import TranscriptChunk, TranscriptSource

WEBHOOK_SIGNATURE_HEADER = "x-zm-signature"
WEBHOOK_TIMESTAMP_HEADER = "x-zm-request-timestamp"
WEBHOOK_SIGNATURE_VERSION = "v0"

URL_VALIDATION_EVENT = "endpoint.url_validation"
RTMS_STARTED_EVENT = "meeting.rtms_started"
RTMS_STOPPED_EVENT = "meeting.rtms_stopped"

RTMS_PROTOCOL_VERSION = 1
FIRST_SEQUENCE = 1
RTMS_STATUS_OK = 0


class RtmsMessageType(IntEnum):
    """RTMS ``msg_type`` values used by the transcript-only client."""

    SIGNALING_HAND_SHAKE_REQ = 1
    SIGNALING_HAND_SHAKE_RESP = 2
    DATA_HAND_SHAKE_REQ = 3
    DATA_HAND_SHAKE_RESP = 4
    CLIENT_READY_ACK = 7
    STREAM_STATE_UPDATE = 8
    KEEP_ALIVE_REQ = 12
    KEEP_ALIVE_RESP = 13
    MEDIA_DATA_TRANSCRIPT = 17
    STREAM_CLOSE_REQ = 21


class RtmsMediaType(IntEnum):
    """RTMS ``media_type`` bit flags; only transcript is ever requested."""

    TRANSCRIPT = 8


class RtmsTranscriptContentType(IntEnum):
    """RTMS transcript ``content_type``; text is the only supported value."""

    TEXT = 5


class RtmsStreamState(IntEnum):
    """RTMS ``STREAM_STATE_UPDATE`` states relevant to lifecycle handling."""

    INACTIVE = 0
    ACTIVE = 1
    INTERRUPTED = 2
    TERMINATED = 3


class RtmsStartedPayload(BaseModel):
    """Verified ``meeting.rtms_started`` webhook payload."""

    model_config = ConfigDict(extra="ignore")

    meeting_uuid: str = Field(min_length=1, max_length=256)
    meeting_id: str | int | None = Field(default=None)
    rtms_stream_id: str = Field(min_length=1, max_length=256)
    server_urls: str = Field(
        min_length=1,
        description="Comma-separated signaling server URLs, one per protocol.",
    )

    def signaling_url(self) -> str:
        """Return the WebSocket signaling URL to connect to.

        Zoom may list several comma-separated URLs for different protocols;
        the first ``wss://``/``ws://`` entry is used, falling back to the
        first entry when none declares a WebSocket scheme.

        Returns:
            The signaling URL to open.
        """

        candidates = [url.strip() for url in self.server_urls.split(",") if url.strip()]
        for url in candidates:
            if url.startswith(("wss://", "ws://")):
                return url
        return candidates[0] if candidates else self.server_urls


class RtmsStoppedPayload(BaseModel):
    """Verified ``meeting.rtms_stopped`` webhook payload."""

    model_config = ConfigDict(extra="ignore")

    meeting_uuid: str = Field(min_length=1, max_length=256)
    meeting_id: str | int | None = Field(default=None)
    rtms_stream_id: str = Field(min_length=1, max_length=256)
    stop_reason: int | None = Field(default=None)


class ZoomWebhookEvent(BaseModel):
    """Envelope shared by every Zoom webhook delivery."""

    model_config = ConfigDict(extra="ignore")

    event: str = Field(min_length=1, max_length=128)
    event_ts: int | None = Field(default=None)
    payload: dict[str, Any] = Field(default_factory=dict)


class RtmsTranscriptContent(BaseModel):
    """``content`` object of one ``MEDIA_DATA_TRANSCRIPT`` message."""

    model_config = ConfigDict(extra="ignore")

    user_id: int | None = Field(default=None)
    user_name: str | None = Field(default=None, max_length=256)
    start_time: int = Field(ge=0, description="Unix epoch ms when speech began.")
    end_time: int = Field(ge=0, description="Unix epoch ms when speech ended.")
    timestamp: int | None = Field(default=None)
    language: int | None = Field(default=None)
    data: str = Field(min_length=1, description="UTF-8 transcript text.")


class RtmsTranscriptMessage(BaseModel):
    """One transcript media message received on the media connection."""

    model_config = ConfigDict(extra="ignore")

    msg_type: int = Field()
    content: RtmsTranscriptContent


class RtmsSignalingHandshakeResponse(BaseModel):
    """Signaling handshake response carrying media server URLs."""

    model_config = ConfigDict(extra="ignore")

    msg_type: int
    status_code: int = Field(default=RTMS_STATUS_OK)
    reason: str = Field(default="")
    media_server: dict[str, Any] = Field(default_factory=dict)

    def transcript_media_url(self) -> str | None:
        """Return the transcript media WebSocket URL when the app is scoped for it."""

        server_urls = self.media_server.get("server_urls")
        if not isinstance(server_urls, dict):
            return None
        url = server_urls.get("transcript") or server_urls.get("all")
        return str(url) if url else None


class RtmsMediaHandshakeResponse(BaseModel):
    """Media handshake response acknowledging the requested media types."""

    model_config = ConfigDict(extra="ignore")

    msg_type: int
    status_code: int = Field(default=RTMS_STATUS_OK)
    reason: str = Field(default="")


class ZoomProtocolError(ValueError):
    """A provider message violated the documented RTMS or webhook contract."""


def generate_rtms_signature(
    client_id: str, client_secret: str, meeting_uuid: str, rtms_stream_id: str
) -> str:
    """Sign an RTMS handshake with HMAC-SHA256 over ``client_id,uuid,stream``.

    Args:
        client_id: Zoom app client id.
        client_secret: Zoom app client secret; never logged.
        meeting_uuid: Meeting UUID from ``meeting.rtms_started``.
        rtms_stream_id: Stream id from ``meeting.rtms_started``.

    Returns:
        Lowercase hex digest expected by the RTMS signaling server.
    """

    message = f"{client_id},{meeting_uuid},{rtms_stream_id}".encode()
    return hmac.new(client_secret.encode(), message, hashlib.sha256).hexdigest()


def compute_webhook_signature(secret_token: str, timestamp: str, raw_body: bytes) -> str:
    """Compute the ``x-zm-signature`` value for one webhook delivery.

    Args:
        secret_token: Zoom webhook secret token.
        timestamp: Raw ``x-zm-request-timestamp`` header value.
        raw_body: Exact request body bytes as received.

    Returns:
        Signature in the ``v0=<hex>`` form Zoom sends.
    """

    message = f"{WEBHOOK_SIGNATURE_VERSION}:{timestamp}:".encode() + raw_body
    digest = hmac.new(secret_token.encode(), message, hashlib.sha256).hexdigest()
    return f"{WEBHOOK_SIGNATURE_VERSION}={digest}"


def verify_webhook_signature(
    secret_token: str,
    timestamp: str | None,
    signature: str | None,
    raw_body: bytes,
    now_epoch_seconds: float,
    tolerance_seconds: int,
) -> bool:
    """Check a webhook delivery's HMAC signature and timestamp freshness.

    Args:
        secret_token: Zoom webhook secret token.
        timestamp: ``x-zm-request-timestamp`` header value, if present.
        signature: ``x-zm-signature`` header value, if present.
        raw_body: Exact request body bytes.
        now_epoch_seconds: Current wall-clock time in Unix seconds.
        tolerance_seconds: Maximum accepted request age to limit replays.

    Returns:
        True only when the signature matches and the timestamp is fresh.
    """

    if not timestamp or not signature:
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(now_epoch_seconds - sent_at) > tolerance_seconds:
        return False
    expected = compute_webhook_signature(secret_token, timestamp, raw_body)
    return hmac.compare_digest(expected, signature)


def build_url_validation_response(secret_token: str, plain_token: str) -> dict[str, str]:
    """Answer Zoom's ``endpoint.url_validation`` challenge.

    Args:
        secret_token: Zoom webhook secret token.
        plain_token: ``plainToken`` from the challenge payload.

    Returns:
        JSON body with ``plainToken`` and the HMAC ``encryptedToken``.
    """

    encrypted = hmac.new(secret_token.encode(), plain_token.encode(), hashlib.sha256)
    return {"plainToken": plain_token, "encryptedToken": encrypted.hexdigest()}


def build_signaling_handshake(
    meeting_uuid: str, rtms_stream_id: str, signature: str
) -> dict[str, Any]:
    """Build the ``SIGNALING_HAND_SHAKE_REQ`` message.

    ``buffer_data`` stays false: transcript spoken before the app connected is
    not replayed, which keeps lecture-clock mapping monotonic.
    """

    return {
        "msg_type": int(RtmsMessageType.SIGNALING_HAND_SHAKE_REQ),
        "protocol_version": RTMS_PROTOCOL_VERSION,
        "sequence": FIRST_SEQUENCE,
        "meeting_uuid": meeting_uuid,
        "rtms_stream_id": rtms_stream_id,
        "signature": signature,
        "buffer_data": False,
    }


def build_transcript_media_handshake(
    meeting_uuid: str, rtms_stream_id: str, signature: str
) -> dict[str, Any]:
    """Build the ``DATA_HAND_SHAKE_REQ`` requesting only transcript text."""

    return {
        "msg_type": int(RtmsMessageType.DATA_HAND_SHAKE_REQ),
        "protocol_version": RTMS_PROTOCOL_VERSION,
        "sequence": FIRST_SEQUENCE,
        "meeting_uuid": meeting_uuid,
        "rtms_stream_id": rtms_stream_id,
        "signature": signature,
        "media_type": int(RtmsMediaType.TRANSCRIPT),
        "media_params": {
            "transcript": {"content_type": int(RtmsTranscriptContentType.TEXT)}
        },
    }


def build_client_ready_ack(rtms_stream_id: str) -> dict[str, Any]:
    """Build the ``CLIENT_READY_ACK`` sent on the signaling connection."""

    return {
        "msg_type": int(RtmsMessageType.CLIENT_READY_ACK),
        "rtms_stream_id": rtms_stream_id,
    }


def build_keep_alive_response(timestamp: int) -> dict[str, Any]:
    """Echo a ``KEEP_ALIVE_REQ`` timestamp back as ``KEEP_ALIVE_RESP``."""

    return {"msg_type": int(RtmsMessageType.KEEP_ALIVE_RESP), "timestamp": timestamp}


def build_stream_close_request(rtms_stream_id: str) -> dict[str, Any]:
    """Build the ``STREAM_CLOSE_REQ`` that gracefully ends a stream."""

    return {
        "msg_type": int(RtmsMessageType.STREAM_CLOSE_REQ),
        "rtms_stream_id": rtms_stream_id,
    }


def parse_transcript_message(message: dict[str, Any]) -> RtmsTranscriptMessage:
    """Validate a ``MEDIA_DATA_TRANSCRIPT`` message at the provider boundary.

    Args:
        message: Decoded JSON object from the media connection.

    Returns:
        The typed transcript message.

    Raises:
        ZoomProtocolError: When the message is not a well-formed transcript.
    """

    try:
        parsed = RtmsTranscriptMessage.model_validate(message)
    except ValidationError as exc:
        raise ZoomProtocolError("Malformed RTMS transcript message.") from exc
    if parsed.msg_type != RtmsMessageType.MEDIA_DATA_TRANSCRIPT:
        raise ZoomProtocolError("Message is not MEDIA_DATA_TRANSCRIPT.")
    if parsed.content.end_time < parsed.content.start_time:
        raise ZoomProtocolError("Transcript end_time precedes start_time.")
    return parsed


def parse_clock_origin_epoch_ms(session_clock_origin: str) -> int:
    """Convert a session's UTC ISO 8601 clock origin into Unix epoch ms.

    Args:
        session_clock_origin: ``YYYY-MM-DDTHH:MM:SS.mmmZ`` origin string.

    Returns:
        Epoch milliseconds of lecture time zero.
    """

    parsed = datetime.fromisoformat(session_clock_origin.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def build_transcript_chunk_id(rtms_stream_id: str, content: RtmsTranscriptContent) -> str:
    """Derive a stable chunk id so replayed provider messages dedupe.

    Args:
        rtms_stream_id: Stream the message arrived on.
        content: Parsed transcript content.

    Returns:
        A deterministic identifier within the 128-character contract limit.
    """

    speaker = content.user_id if content.user_id is not None else "channel"
    seed = f"{rtms_stream_id}|{speaker}|{content.start_time}|{content.end_time}"
    return f"zoom_{hashlib.sha256(seed.encode()).hexdigest()[:32]}"


def map_transcript_message(
    message: RtmsTranscriptMessage,
    session_id: str,
    rtms_stream_id: str,
    clock_origin_epoch_ms: int,
    max_text_chars: int,
    include_speaker_label: bool,
) -> TranscriptChunk | None:
    """Map one RTMS transcript message onto the shared lecture clock.

    Args:
        message: Validated transcript message.
        session_id: Lecture session the stream is bound to.
        rtms_stream_id: Stream identifier used to derive a stable chunk id.
        clock_origin_epoch_ms: Epoch ms of the session's lecture time zero.
        max_text_chars: Text limit; longer utterances are truncated.
        include_speaker_label: Whether the participant name may be stored.

    Returns:
        A final ``zoom_rtms`` chunk, or None when the utterance ended before
        the lecture clock started or carries only whitespace.
    """

    content = message.content
    text = content.data.strip()[:max_text_chars]
    if not text:
        return None
    end_ms = content.end_time - clock_origin_epoch_ms
    if end_ms <= 0:
        return None
    start_ms = max(0, content.start_time - clock_origin_epoch_ms)
    end_ms = max(start_ms + 1, end_ms)
    speaker_label = content.user_name if include_speaker_label else None
    return TranscriptChunk(
        chunk_id=build_transcript_chunk_id(rtms_stream_id, content),
        session_id=session_id,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        speaker_label=speaker_label or None,
        source=TranscriptSource.ZOOM_RTMS,
        is_final=True,
        revision=1,
    )
