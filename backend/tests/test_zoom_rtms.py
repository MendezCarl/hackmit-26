"""Zoom RTMS transcript integration tests using synthetic provider fakes.

No test here opens a network connection. A scripted ``FakeRtmsServer`` plays
the Zoom signaling and media endpoints according to the documented RTMS
protocol so handshakes, keep-alives, transcript delivery, and failure paths
are exercised end to end through the FastAPI app.
"""

import asyncio
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi.testclient import TestClient

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.integrations.zoom.protocol import (
    RtmsMediaType,
    RtmsMessageType,
    RtmsStartedPayload,
    RtmsTranscriptContent,
    ZoomProtocolError,
    build_transcript_chunk_id,
    compute_webhook_signature,
    generate_rtms_signature,
    map_transcript_message,
    parse_clock_origin_epoch_ms,
    parse_transcript_message,
    verify_webhook_signature,
)
from app.integrations.zoom.rtms_client import (
    RtmsHandshakeError,
    RtmsStreamClosed,
    ZoomRtmsTranscriptStream,
)
from app.main import create_app

CLIENT_ID = "zoom-client-id"
CLIENT_SECRET = "zoom-client-secret"  # noqa: S105 - synthetic test value
WEBHOOK_SECRET = "zoom-webhook-secret"  # noqa: S105 - synthetic test value
MEETING_UUID = "meeting-uuid-1"
MEETING_ID = "123456789"
STREAM_ID = "stream-1"
SIGNALING_URL = "wss://fake.zoom.test/signaling"
MEDIA_URL = "wss://fake.zoom.test/media"
ORIGIN_ISO = "2026-01-01T10:00:00.000Z"
ORIGIN_EPOCH_MS = parse_clock_origin_epoch_ms(ORIGIN_ISO)

SETTINGS = Settings(
    app_env="test",
    zoom_client_id=CLIENT_ID,
    zoom_client_secret=CLIENT_SECRET,
    zoom_webhook_secret_token=WEBHOOK_SECRET,
)
UNCONFIGURED_SETTINGS = Settings(app_env="test")

_CLOSE = object()


def transcript_frame(
    start_ms: int, end_ms: int, text: str, speaker: str = "Prof. Ada"
) -> dict[str, Any]:
    """Build one ``MEDIA_DATA_TRANSCRIPT`` frame with epoch-ms timestamps."""

    return {
        "msg_type": int(RtmsMessageType.MEDIA_DATA_TRANSCRIPT),
        "content": {
            "user_id": 42,
            "user_name": speaker,
            "start_time": ORIGIN_EPOCH_MS + start_ms,
            "end_time": ORIGIN_EPOCH_MS + end_ms,
            "data": text,
        },
    }


class FakeRtmsConnection:
    """One scripted WebSocket endpoint of the fake Zoom RTMS server."""

    def __init__(self, server: FakeRtmsServer, role: str) -> None:
        self._server = server
        self._role = role
        self._inbound: asyncio.Queue[Any] = asyncio.Queue()
        self.closed = False

    async def send(self, message: str) -> None:
        if self.closed:
            raise RtmsStreamClosed("closed")
        decoded = json.loads(message)
        self._server.sent[self._role].append(decoded)
        for reply in self._server.reply_to(self._role, decoded):
            self._inbound.put_nowait(reply)

    async def recv(self) -> str | bytes:
        item = await self._inbound.get()
        if item is _CLOSE:
            self.closed = True
            raise RtmsStreamClosed("closed")
        return item if isinstance(item, str | bytes) else json.dumps(item)

    async def close(self) -> None:
        self.closed = True
        self._inbound.put_nowait(_CLOSE)


class FakeRtmsServer:
    """Scripted signaling + media endpoints following the documented protocol."""

    def __init__(
        self,
        media_frames: list[Any] | None = None,
        *,
        reject_signaling: bool = False,
        reject_media: bool = False,
        close_media_after_frames: bool = True,
    ) -> None:
        self.media_frames = media_frames or []
        self.reject_signaling = reject_signaling
        self.reject_media = reject_media
        self.close_media_after_frames = close_media_after_frames
        self.sent: dict[str, list[dict[str, Any]]] = {"signaling": [], "media": []}
        self.connected_urls: list[str] = []
        self.expected_signature = generate_rtms_signature(
            CLIENT_ID, CLIENT_SECRET, MEETING_UUID, STREAM_ID
        )

    async def connect(self, url: str) -> FakeRtmsConnection:
        self.connected_urls.append(url)
        role = "signaling" if url == SIGNALING_URL else "media"
        return FakeRtmsConnection(self, role)

    def reply_to(self, role: str, message: dict[str, Any]) -> list[Any]:
        msg_type = message.get("msg_type")
        if role == "signaling" and msg_type == RtmsMessageType.SIGNALING_HAND_SHAKE_REQ:
            if self.reject_signaling or message["signature"] != self.expected_signature:
                return [
                    {
                        "msg_type": int(RtmsMessageType.SIGNALING_HAND_SHAKE_RESP),
                        "status_code": 6,
                        "reason": "invalid signature",
                    }
                ]
            return [
                {"msg_type": int(RtmsMessageType.KEEP_ALIVE_REQ), "timestamp": 1_000},
                {
                    "msg_type": int(RtmsMessageType.SIGNALING_HAND_SHAKE_RESP),
                    "status_code": 0,
                    "media_server": {"server_urls": {"transcript": MEDIA_URL}},
                },
            ]
        if role == "media" and msg_type == RtmsMessageType.DATA_HAND_SHAKE_REQ:
            if self.reject_media or message["signature"] != self.expected_signature:
                return [
                    {
                        "msg_type": int(RtmsMessageType.DATA_HAND_SHAKE_RESP),
                        "status_code": 6,
                    }
                ]
            replies: list[Any] = [
                {"msg_type": int(RtmsMessageType.DATA_HAND_SHAKE_RESP), "status_code": 0},
                {"msg_type": int(RtmsMessageType.KEEP_ALIVE_REQ), "timestamp": 2_000},
                *self.media_frames,
            ]
            if self.close_media_after_frames:
                replies.append(_CLOSE)
            return replies
        return []


def token_for(user_id: str, role: str = "professor") -> str:
    """Mint a synthetic access token."""

    return issue_access_token(SETTINGS, AuthenticatedActor(user_id=user_id, role=role))


def auth_headers(user_id: str, role: str = "professor") -> dict[str, str]:
    """Bearer headers for a synthetic user."""

    return {"Authorization": f"Bearer {token_for(user_id, role)}"}


def signed_webhook_headers(raw_body: bytes, timestamp: int | None = None) -> dict[str, str]:
    """Sign a webhook body exactly as Zoom does."""

    stamp = str(timestamp if timestamp is not None else int(time.time()))
    return {
        "x-zm-request-timestamp": stamp,
        "x-zm-signature": compute_webhook_signature(WEBHOOK_SECRET, stamp, raw_body),
        "content-type": "application/json",
    }


def create_session(client: TestClient, zoom_meeting_id: str | None = None) -> str:
    """Create a synthetic Zoom-mode session owned by ``owner-1``."""

    body: dict[str, Any] = {
        "lecture_id": "lecture-1",
        "course_id": "course-1",
        "title": "Synthetic Lecture",
        "mode": "zoom",
    }
    if zoom_meeting_id is not None:
        body["zoom_meeting_id"] = zoom_meeting_id
    response = client.post("/api/v1/sessions", json=body, headers=auth_headers("owner-1"))
    assert response.status_code == 201, response.text
    session_id = response.json()["session_id"]
    session = client.app.state.store.sessions[session_id]
    session.session_clock_origin = ORIGIN_ISO
    client.app.state.store.sessions[session_id] = session
    return session_id


def rtms_started_body(meeting_id: str = MEETING_ID, stream_id: str = STREAM_ID) -> bytes:
    """Raw ``meeting.rtms_started`` webhook body."""

    return json.dumps(
        {
            "event": "meeting.rtms_started",
            "event_ts": 1,
            "payload": {
                "meeting_uuid": MEETING_UUID,
                "meeting_id": meeting_id,
                "rtms_stream_id": stream_id,
                "server_urls": SIGNALING_URL,
                "operator_id": "op-1",
            },
        }
    ).encode()


def wait_for_status(
    client: TestClient, session_id: str, expected: set[str]
) -> dict[str, Any]:
    """Poll the status route until the background stream reaches ``expected``."""

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        status = client.get(
            f"/api/v1/sessions/{session_id}/zoom/status", headers=auth_headers("owner-1")
        ).json()
        if status["status"] in expected:
            return status
        time.sleep(0.02)
    raise AssertionError(f"Stream never reached {expected}: {status}")


# ---------------------------------------------------------------- protocol


def test_rtms_signature_matches_documented_hmac() -> None:
    """Signature is HMAC-SHA256 over ``client_id,meeting_uuid,rtms_stream_id``."""

    expected = hmac.new(
        CLIENT_SECRET.encode(),
        f"{CLIENT_ID},{MEETING_UUID},{STREAM_ID}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert (
        generate_rtms_signature(CLIENT_ID, CLIENT_SECRET, MEETING_UUID, STREAM_ID)
        == expected
    )


def test_rtms_started_payload_picks_websocket_url_from_comma_separated_list() -> None:
    payload = RtmsStartedPayload(
        meeting_uuid="uuid",
        rtms_stream_id="stream",
        server_urls="tcp://rtms.example/tcp, wss://rtms.example/signaling,wss://alt",
    )
    assert payload.signaling_url() == "wss://rtms.example/signaling"
    single = RtmsStartedPayload(
        meeting_uuid="uuid", rtms_stream_id="stream", server_urls="wss://only"
    )
    assert single.signaling_url() == "wss://only"
    no_scheme = RtmsStartedPayload(
        meeting_uuid="uuid", rtms_stream_id="stream", server_urls="first,second"
    )
    assert no_scheme.signaling_url() == "first"


def test_webhook_signature_rejects_forged_stale_and_missing_headers() -> None:
    """Only a fresh, correctly signed request verifies."""

    body = b'{"event":"x"}'
    now = 1_700_000_000
    good = compute_webhook_signature(WEBHOOK_SECRET, str(now), body)
    assert verify_webhook_signature(WEBHOOK_SECRET, str(now), good, body, now + 10, 300)
    assert not verify_webhook_signature(
        WEBHOOK_SECRET, str(now), good, body, now + 301, 300
    )
    assert not verify_webhook_signature(WEBHOOK_SECRET, str(now), good, b"{}", now, 300)
    assert not verify_webhook_signature(WEBHOOK_SECRET, None, good, body, now, 300)
    assert not verify_webhook_signature(WEBHOOK_SECRET, str(now), None, body, now, 300)
    assert not verify_webhook_signature(WEBHOOK_SECRET, "nan", good, body, now, 300)


def test_transcript_mapping_uses_lecture_relative_half_open_interval() -> None:
    """Epoch timestamps become lecture-relative ms with a stable chunk id."""

    message = parse_transcript_message(transcript_frame(1_000, 2_500, "  Hello class.  "))
    chunk = map_transcript_message(
        message,
        session_id="session-1",
        rtms_stream_id=STREAM_ID,
        clock_origin_epoch_ms=ORIGIN_EPOCH_MS,
        max_text_chars=100,
        include_speaker_label=True,
    )
    assert chunk is not None
    assert (chunk.start_ms, chunk.end_ms) == (1_000, 2_500)
    assert chunk.text == "Hello class."
    assert chunk.speaker_label == "Prof. Ada"
    assert chunk.source.value == "zoom_rtms"
    assert chunk.is_final is True and chunk.revision == 1
    assert chunk.chunk_id == build_transcript_chunk_id(STREAM_ID, message.content)
    replay = parse_transcript_message(transcript_frame(1_000, 2_500, "  Hello class.  "))
    assert build_transcript_chunk_id(STREAM_ID, replay.content) == chunk.chunk_id


def test_transcript_mapping_drops_pre_session_and_empty_text() -> None:
    """Speech that ended before lecture time zero or has no text is skipped."""

    common = {
        "session_id": "session-1",
        "rtms_stream_id": STREAM_ID,
        "clock_origin_epoch_ms": ORIGIN_EPOCH_MS,
        "max_text_chars": 100,
        "include_speaker_label": False,
    }
    before = parse_transcript_message(transcript_frame(-5_000, -1_000, "early"))
    assert map_transcript_message(before, **common) is None
    blank = parse_transcript_message(transcript_frame(0, 1_000, "   "))
    assert map_transcript_message(blank, **common) is None
    straddling = parse_transcript_message(transcript_frame(-500, 500, "straddle"))
    mapped = map_transcript_message(straddling, **common)
    assert mapped is not None and (mapped.start_ms, mapped.end_ms) == (0, 500)
    assert mapped.speaker_label is None
    zero_length = parse_transcript_message(transcript_frame(700, 700, "instant"))
    mapped = map_transcript_message(zero_length, **common)
    assert mapped is not None and mapped.end_ms == mapped.start_ms + 1


def test_transcript_parser_rejects_malformed_messages() -> None:
    """Missing content, negative or non-integer times, and wrong types fail."""

    with pytest.raises(ZoomProtocolError):
        parse_transcript_message({"msg_type": 17})
    with pytest.raises(ZoomProtocolError):
        parse_transcript_message(
            {"msg_type": 17, "content": {"start_time": -1, "end_time": 5, "data": "x"}}
        )
    with pytest.raises(ZoomProtocolError):
        parse_transcript_message(
            {"msg_type": 17, "content": {"start_time": "a", "end_time": 5, "data": "x"}}
        )
    with pytest.raises(ZoomProtocolError):
        parse_transcript_message(
            {"msg_type": 17, "content": {"start_time": 1, "end_time": 2}}
        )
    parsed = parse_transcript_message(
        {"msg_type": 17, "content": {"start_time": 1, "end_time": 2, "data": "ok"}}
    )
    assert isinstance(parsed.content, RtmsTranscriptContent)


# ------------------------------------------------------------ stream client


def run_stream(server: FakeRtmsServer) -> list[Any]:
    """Run the client against the fake server and return delivered messages."""

    delivered: list[Any] = []
    states: list[str] = []

    async def on_transcript(message: Any) -> None:
        delivered.append(message)

    async def main() -> None:
        stream = ZoomRtmsTranscriptStream(
            meeting_uuid=MEETING_UUID,
            rtms_stream_id=STREAM_ID,
            signaling_url=SIGNALING_URL,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            on_transcript=on_transcript,
            connector=server.connect,
            on_state_change=states.append,
        )
        await asyncio.wait_for(stream.run(), timeout=5.0)

    asyncio.run(main())
    assert states == ["connecting", "streaming", "stopped"]
    return delivered


def test_stream_client_completes_documented_handshakes_and_delivers_transcripts() -> None:
    """Signaling then transcript-only media handshake; keep-alives answered."""

    server = FakeRtmsServer(
        [
            transcript_frame(0, 900, "first"),
            "not json",
            {"msg_type": 99},
            {"msg_type": 17, "content": {"start_time": "bad"}},
            transcript_frame(900, 1_800, "second"),
        ]
    )
    delivered = run_stream(server)

    assert server.connected_urls == [SIGNALING_URL, MEDIA_URL]
    signaling_sent = server.sent["signaling"]
    assert signaling_sent[0]["msg_type"] == RtmsMessageType.SIGNALING_HAND_SHAKE_REQ
    assert signaling_sent[0]["meeting_uuid"] == MEETING_UUID
    assert signaling_sent[0]["rtms_stream_id"] == STREAM_ID
    assert signaling_sent[0]["signature"] == server.expected_signature
    assert {"msg_type": 13, "timestamp": 1_000} in signaling_sent
    assert {"msg_type": 7, "rtms_stream_id": STREAM_ID} in signaling_sent

    media_sent = server.sent["media"]
    assert media_sent[0]["msg_type"] == RtmsMessageType.DATA_HAND_SHAKE_REQ
    assert media_sent[0]["media_type"] == RtmsMediaType.TRANSCRIPT
    assert set(media_sent[0]["media_params"]) == {"transcript"}
    assert {"msg_type": 13, "timestamp": 2_000} in media_sent

    assert [message.content.data for message in delivered] == ["first", "second"]


def test_stream_client_raises_when_signaling_handshake_is_rejected() -> None:
    """A rejected signature never opens a media connection."""

    server = FakeRtmsServer(reject_signaling=True)
    with pytest.raises(RtmsHandshakeError):
        run_stream(server)
    assert server.connected_urls == [SIGNALING_URL]


def test_stream_client_raises_when_media_handshake_is_rejected() -> None:
    """A rejected media handshake surfaces as a handshake error."""

    with pytest.raises(RtmsHandshakeError):
        run_stream(FakeRtmsServer(reject_media=True))


# ------------------------------------------------------------ REST + WS flow


def test_rtms_start_requires_owner_and_configuration() -> None:
    """Only the owner can bind a meeting, and only on a configured backend."""

    with TestClient(create_app(UNCONFIGURED_SETTINGS)) as client:
        session_id = create_session(client)
        status = client.get(
            f"/api/v1/sessions/{session_id}/zoom/status", headers=auth_headers("owner-1")
        )
        assert status.status_code == 200
        assert status.json()["status"] == "not_configured"
        start = client.post(
            f"/api/v1/sessions/{session_id}/zoom/rtms/start",
            json={"zoom_meeting_id": MEETING_ID},
            headers=auth_headers("owner-1"),
        )
        assert start.status_code == 502
        assert start.json()["error"]["code"] == "provider_failure"

    with TestClient(create_app(SETTINGS)) as client:
        session_id = create_session(client)
        assert (
            client.get(
                f"/api/v1/sessions/{session_id}/zoom/status",
                headers=auth_headers("owner-1"),
            ).json()["status"]
            == "not_linked"
        )
        forbidden = client.post(
            f"/api/v1/sessions/{session_id}/zoom/rtms/start",
            json={"zoom_meeting_id": MEETING_ID},
            headers=auth_headers("stranger-1", role="student"),
        )
        assert forbidden.status_code == 403
        accepted = client.post(
            f"/api/v1/sessions/{session_id}/zoom/rtms/start",
            json={"zoom_meeting_id": MEETING_ID},
            headers=auth_headers("owner-1"),
        )
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "awaiting_stream"
        assert accepted.json()["zoom_meeting_id"] == MEETING_ID
        stranger_status = client.get(
            f"/api/v1/sessions/{session_id}/zoom/status",
            headers=auth_headers("stranger-1", role="student"),
        )
        assert stranger_status.status_code == 403


def test_webhook_rejects_unsigned_stale_and_forged_requests() -> None:
    """Webhook deliveries without a valid fresh signature are unauthorized."""

    with TestClient(create_app(SETTINGS)) as client:
        body = rtms_started_body()
        unsigned = client.post(
            "/api/v1/integrations/zoom/webhooks",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert unsigned.status_code == 401
        stale = client.post(
            "/api/v1/integrations/zoom/webhooks",
            content=body,
            headers=signed_webhook_headers(body, timestamp=int(time.time()) - 3_600),
        )
        assert stale.status_code == 401
        headers = signed_webhook_headers(body)
        forged = client.post(
            "/api/v1/integrations/zoom/webhooks",
            content=body.replace(b"stream-1", b"stream-2"),
            headers=headers,
        )
        assert forged.status_code == 401

    with TestClient(create_app(UNCONFIGURED_SETTINGS)) as client:
        body = rtms_started_body()
        response = client.post(
            "/api/v1/integrations/zoom/webhooks",
            content=body,
            headers=signed_webhook_headers(body),
        )
        assert response.status_code == 502


def test_webhook_url_validation_answers_challenge() -> None:
    """Zoom's URL validation challenge is answered with the documented HMAC."""

    body = json.dumps(
        {"event": "endpoint.url_validation", "payload": {"plainToken": "abc123"}}
    ).encode()
    with TestClient(create_app(SETTINGS)) as client:
        response = client.post(
            "/api/v1/integrations/zoom/webhooks",
            content=body,
            headers=signed_webhook_headers(body),
        )
    assert response.status_code == 200
    expected = hmac.new(WEBHOOK_SECRET.encode(), b"abc123", hashlib.sha256).hexdigest()
    assert response.json() == {"plainToken": "abc123", "encryptedToken": expected}


def test_rtms_started_webhook_streams_transcripts_to_authorized_subscribers() -> None:
    """Webhook -> fake RTMS -> TranscriptService -> WebSocket, session-scoped."""

    server = FakeRtmsServer(
        [
            transcript_frame(0, 1_200, "Welcome to lecture."),
            transcript_frame(1_200, 2_400, "Today: eigenvalues."),
            transcript_frame(0, 1_200, "Welcome to lecture."),  # provider replay
        ]
    )
    with TestClient(create_app(SETTINGS, rtms_connector=server.connect)) as client:
        bound_session = create_session(client, zoom_meeting_id=MEETING_ID)
        other_session = create_session(client)
        ws_token = token_for("owner-1")

        with (
            client.websocket_connect(
                f"/ws/v1/sessions/{bound_session}?token={ws_token}"
            ) as bound_socket,
            client.websocket_connect(
                f"/ws/v1/sessions/{other_session}?token={ws_token}"
            ) as other_socket,
        ):
            assert bound_socket.receive_json()["event_type"] == "session.connected"
            assert other_socket.receive_json()["event_type"] == "session.connected"

            body = rtms_started_body()
            accepted = client.post(
                "/api/v1/integrations/zoom/webhooks",
                content=body,
                headers=signed_webhook_headers(body),
            )
            assert accepted.status_code == 200
            assert accepted.json() == {
                "status": "accepted",
                "event": "meeting.rtms_started",
            }

            first = bound_socket.receive_json()
            assert first["event_type"] == "transcript.chunk.created"
            assert first["session_id"] == bound_session
            assert first["payload"]["text"] == "Welcome to lecture."
            assert first["payload"]["source"] == "zoom_rtms"
            assert (first["payload"]["start_ms"], first["payload"]["end_ms"]) == (0, 1_200)
            summary = bound_socket.receive_json()
            assert summary["event_type"] == "transcript.ingested"
            assert summary["payload"]["accepted_chunk_ids"] == [
                first["payload"]["chunk_id"]
            ]
            second = bound_socket.receive_json()
            assert second["payload"]["text"] == "Today: eigenvalues."
            assert bound_socket.receive_json()["event_type"] == "transcript.ingested"

            final_status = wait_for_status(client, bound_session, {"stopped", "failed"})
            assert final_status["status"] == "stopped"
            assert final_status["rtms_stream_id"] == STREAM_ID
            assert final_status["transcript_chunk_count"] == 2
            assert final_status["last_error"] is None

            # The isolated session must see nothing but its own welcome.
            probe = client.app.state.event_publisher.build_envelope(
                other_session, "recovery_card.completed", {"card_id": "probe"}
            )
            client.app.state.event_publisher.publish(probe, audience_user_id="owner-1")
            assert other_socket.receive_json()["payload"] == {"card_id": "probe"}

        window = client.get(
            f"/api/v1/sessions/{bound_session}/transcript",
            params={"start_ms": 0, "end_ms": 5_000},
            headers=auth_headers("owner-1"),
        )
        assert window.status_code == 200, window.text
        texts = [chunk["text"] for chunk in window.json()["chunks"]]
        assert texts == ["Welcome to lecture.", "Today: eigenvalues."]
        assert {chunk["source"] for chunk in window.json()["chunks"]} == {"zoom_rtms"}

        unrelated = client.get(
            f"/api/v1/sessions/{other_session}/transcript",
            params={"start_ms": 0, "end_ms": 5_000},
            headers=auth_headers("owner-1"),
        )
        assert unrelated.json()["chunks"] == []


def test_rtms_started_for_unknown_meeting_is_ignored_and_stopped_closes_stream() -> None:
    """Unbound meetings are ignored; ``meeting.rtms_stopped`` closes a live stream."""

    server = FakeRtmsServer(
        [transcript_frame(0, 1_000, "hold")], close_media_after_frames=False
    )
    with TestClient(create_app(SETTINGS, rtms_connector=server.connect)) as client:
        body = rtms_started_body(meeting_id="000000")
        ignored = client.post(
            "/api/v1/integrations/zoom/webhooks",
            content=body,
            headers=signed_webhook_headers(body),
        )
        assert ignored.json() == {"status": "ignored", "event": "meeting.rtms_started"}
        assert server.connected_urls == []

        session_id = create_session(client, zoom_meeting_id=MEETING_ID)
        body = rtms_started_body()
        client.post(
            "/api/v1/integrations/zoom/webhooks",
            content=body,
            headers=signed_webhook_headers(body),
        )
        streaming = wait_for_status(client, session_id, {"streaming"})
        assert streaming["rtms_stream_id"] == STREAM_ID

        stop_body = json.dumps(
            {
                "event": "meeting.rtms_stopped",
                "payload": {
                    "meeting_uuid": MEETING_UUID,
                    "rtms_stream_id": STREAM_ID,
                    "stop_reason": 1,
                },
            }
        ).encode()
        stopped = client.post(
            "/api/v1/integrations/zoom/webhooks",
            content=stop_body,
            headers=signed_webhook_headers(stop_body),
        )
        assert stopped.json() == {"status": "accepted", "event": "meeting.rtms_stopped"}
        assert (
            wait_for_status(client, session_id, {"stopped"})["transcript_chunk_count"] == 1
        )
        assert {"msg_type": 21, "rtms_stream_id": STREAM_ID} in server.sent["signaling"]


def test_rtms_handshake_failure_is_reported_in_status() -> None:
    """A provider rejection leaves the session in ``failed`` with a safe message."""

    server = FakeRtmsServer(reject_signaling=True)
    with TestClient(create_app(SETTINGS, rtms_connector=server.connect)) as client:
        session_id = create_session(client, zoom_meeting_id=MEETING_ID)
        body = rtms_started_body()
        client.post(
            "/api/v1/integrations/zoom/webhooks",
            content=body,
            headers=signed_webhook_headers(body),
        )
        failed = wait_for_status(client, session_id, {"failed"})
        assert "rejected" in failed["last_error"]
        assert CLIENT_SECRET not in json.dumps(failed)


def test_ending_session_closes_stream_and_notifies_subscribers() -> None:
    """Ending the lecture stops RTMS and pushes ``session.ended`` on the socket."""

    server = FakeRtmsServer(
        [transcript_frame(0, 1_000, "hold")], close_media_after_frames=False
    )
    with TestClient(create_app(SETTINGS, rtms_connector=server.connect)) as client:
        session_id = create_session(client, zoom_meeting_id=MEETING_ID)
        with client.websocket_connect(
            f"/ws/v1/sessions/{session_id}?token={token_for('owner-1')}"
        ) as socket:
            assert socket.receive_json()["event_type"] == "session.connected"
            body = rtms_started_body()
            client.post(
                "/api/v1/integrations/zoom/webhooks",
                content=body,
                headers=signed_webhook_headers(body),
            )
            wait_for_status(client, session_id, {"streaming"})
            assert socket.receive_json()["event_type"] == "transcript.chunk.created"
            assert socket.receive_json()["event_type"] == "transcript.ingested"

            ended = client.post(
                f"/api/v1/sessions/{session_id}/end", headers=auth_headers("owner-1")
            )
            assert ended.status_code == 200, ended.text
            assert ended.json()["status"] == "ended"

            notice = socket.receive_json()
            assert notice["event_type"] == "session.ended"
            assert notice["session_id"] == session_id
            assert notice["payload"]["status"] == "ended"
            assert notice["payload"]["ended_at"] is not None

        status = wait_for_status(client, session_id, {"stopped"})
        assert status["transcript_chunk_count"] == 1
        assert {"msg_type": 21, "rtms_stream_id": STREAM_ID} in server.sent["signaling"]

        # Ending again is idempotent and publishes nothing new.
        again = client.post(
            f"/api/v1/sessions/{session_id}/end", headers=auth_headers("owner-1")
        )
        assert again.status_code == 200
        assert again.json()["ended_at"] == ended.json()["ended_at"]
