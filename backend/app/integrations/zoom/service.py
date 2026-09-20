"""Zoom RTMS lifecycle: webhook verification, session binding, and ingestion.

Streams are keyed by lecture session. A ``meeting.rtms_started`` webhook is
matched to the active session whose ``zoom_meeting_id`` equals the meeting id
or UUID; transcript messages from that stream are mapped onto the session
clock and ingested through ``TranscriptService`` on behalf of the session
owner, so every existing validation, revision, and publishing rule applies.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.auth.access import SESSION_ROLE_OWNER, SessionAccess
from app.auth.tokens import ROLE_PROFESSOR, AuthenticatedActor
from app.config import Settings
from app.contracts.models import IngestTranscriptRequest, LectureSession, SessionStatus
from app.core.clock import utc_now_iso
from app.core.errors import AppError, ErrorCode
from app.integrations.zoom.protocol import (
    RTMS_STARTED_EVENT,
    RTMS_STOPPED_EVENT,
    URL_VALIDATION_EVENT,
    WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_TIMESTAMP_HEADER,
    RtmsStartedPayload,
    RtmsStoppedPayload,
    RtmsTranscriptMessage,
    ZoomWebhookEvent,
    build_url_validation_response,
    map_transcript_message,
    parse_clock_origin_epoch_ms,
    verify_webhook_signature,
)
from app.integrations.zoom.rtms_client import (
    STATE_STREAMING,
    RtmsConnector,
    RtmsHandshakeError,
    RtmsStreamClosed,
    ZoomRtmsTranscriptStream,
    connect_with_websockets,
)
from app.storage.in_memory import InMemoryStore
from app.transcript.service import TranscriptService

LOGGER = logging.getLogger("app.integrations.zoom")


class ZoomRtmsStreamStatus(str, Enum):
    """Lifecycle of the Zoom realtime transcript link for one session."""

    NOT_CONFIGURED = "not_configured"
    NOT_LINKED = "not_linked"
    AWAITING_STREAM = "awaiting_stream"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    STOPPED = "stopped"
    FAILED = "failed"


class ZoomRtmsStatus(BaseModel):
    """Zoom realtime transcript status for one lecture session."""

    session_id: str = Field(description="Lecture session the status describes.")
    zoom_meeting_id: str | None = Field(
        default=None, description="Zoom meeting bound to the session, when any."
    )
    status: ZoomRtmsStreamStatus = Field(description="Current stream lifecycle state.")
    rtms_stream_id: str | None = Field(
        default=None, description="Active or last RTMS stream id from Zoom."
    )
    transcript_chunk_count: int = Field(
        default=0, ge=0, description="Chunks ingested from Zoom during this session."
    )
    last_transcript_at: str | None = Field(
        default=None, description="UTC ISO 8601 time of the last ingested chunk."
    )
    last_error: str | None = Field(
        default=None, description="Safe description of the last stream failure."
    )
    updated_at: str = Field(description="UTC ISO 8601 time of the last change.")


class StartZoomRtmsRequest(BaseModel):
    """Bind a lecture session to the Zoom meeting whose RTMS stream feeds it."""

    model_config = ConfigDict(extra="forbid")

    zoom_meeting_id: str = Field(
        min_length=1,
        max_length=128,
        description="Zoom meeting number or UUID reported in RTMS webhooks.",
    )


class ZoomWebhookAck(BaseModel):
    """Acknowledgement returned for verified lifecycle webhooks."""

    status: str = Field(description="``accepted`` or ``ignored``.")
    event: str = Field(description="Zoom event type that was processed.")


class ZoomUrlValidationResponse(BaseModel):
    """Challenge response Zoom requires when validating the webhook URL.

    Field names are camelCase because Zoom dictates this payload shape.
    """

    plainToken: str = Field(description="Echoed challenge token.")  # noqa: N815
    encryptedToken: str = Field(description="HMAC-SHA256 of the token.")  # noqa: N815


WEBHOOK_ACCEPTED = "accepted"
WEBHOOK_IGNORED = "ignored"

StreamFactory = Callable[..., ZoomRtmsTranscriptStream]


class _SessionStreamState:
    """Mutable per-session bookkeeping for the bound Zoom stream."""

    def __init__(self) -> None:
        self.status = ZoomRtmsStreamStatus.AWAITING_STREAM
        self.rtms_stream_id: str | None = None
        self.transcript_chunk_count = 0
        self.last_transcript_at: str | None = None
        self.last_error: str | None = None
        self.updated_at = utc_now_iso()
        self.stream: ZoomRtmsTranscriptStream | None = None
        self.task: asyncio.Task[None] | None = None

    def touch(self) -> None:
        self.updated_at = utc_now_iso()


class ZoomRtmsService:
    """Bind sessions to Zoom meetings and run their realtime transcript streams."""

    def __init__(
        self,
        store: InMemoryStore,
        settings: Settings,
        session_access: SessionAccess,
        transcript_service: TranscriptService,
        connector: RtmsConnector = connect_with_websockets,
        stream_factory: StreamFactory = ZoomRtmsTranscriptStream,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Bind the service to storage, settings, and the transcript pipeline.

        Args:
            store: Injected storage connections.
            settings: Settings carrying Zoom credentials and limits.
            session_access: Shared membership resolver for status reads.
            transcript_service: Pipeline every mapped chunk is ingested through.
            connector: Opens RTMS WebSocket connections; injected for tests.
            stream_factory: Builds stream clients; injected for tests.
            clock: Wall clock in Unix seconds used for webhook freshness.
        """

        self._store = store
        self._settings = settings
        self._session_access = session_access
        self._transcript_service = transcript_service
        self._connector = connector
        self._stream_factory = stream_factory
        self._clock = clock
        self._states: dict[str, _SessionStreamState] = {}

    # ------------------------------------------------------------------ REST

    def link_session(
        self, actor: AuthenticatedActor, session_id: str, request: StartZoomRtmsRequest
    ) -> ZoomRtmsStatus:
        """Bind an active session to a Zoom meeting so its RTMS stream is accepted.

        Args:
            actor: Authenticated session owner.
            session_id: Session to bind.
            request: Meeting identifier to bind.

        Returns:
            The session's Zoom transcript status after binding.

        Raises:
            AppError: ``forbidden`` for non-owners, ``validation_failed`` for
                ended sessions, ``provider_failure`` when Zoom credentials are
                not configured.
        """

        membership = self._session_access.resolve_membership(actor, session_id)
        if membership.session_role != SESSION_ROLE_OWNER:
            raise AppError(
                ErrorCode.FORBIDDEN, "Only the session owner can link a Zoom meeting."
            )
        if not self._settings.zoom_rtms_configured():
            raise AppError(
                ErrorCode.PROVIDER_FAILURE,
                "Zoom RTMS credentials are not configured on this backend.",
            )
        session = self._store.sessions[session_id]
        if session.status == SessionStatus.ENDED:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "Cannot link a Zoom meeting to an ended session.",
            )
        session.zoom_meeting_id = request.zoom_meeting_id.strip()
        self._store.sessions[session_id] = session
        state = self._states.setdefault(session_id, _SessionStreamState())
        if state.stream is None:
            state.status = ZoomRtmsStreamStatus.AWAITING_STREAM
            state.last_error = None
        state.touch()
        return self._build_status(session, state)

    def read_status(self, actor: AuthenticatedActor, session_id: str) -> ZoomRtmsStatus:
        """Return the Zoom transcript status for any session member.

        Args:
            actor: Authenticated owner, participant, or course professor.
            session_id: Session whose status is read.

        Returns:
            The current status; ``not_configured`` or ``not_linked`` when no
            stream can ever arrive.

        Raises:
            AppError: ``not_found`` or ``forbidden`` from membership resolution.
        """

        self._session_access.resolve_membership(actor, session_id)
        session = self._store.sessions[session_id]
        return self._build_status(session, self._states.get(session_id))

    def _build_status(
        self, session: LectureSession, state: _SessionStreamState | None
    ) -> ZoomRtmsStatus:
        if not self._settings.zoom_rtms_configured():
            status = ZoomRtmsStreamStatus.NOT_CONFIGURED
        elif state is None:
            status = (
                ZoomRtmsStreamStatus.AWAITING_STREAM
                if session.zoom_meeting_id
                else ZoomRtmsStreamStatus.NOT_LINKED
            )
        else:
            status = state.status
        return ZoomRtmsStatus(
            session_id=session.session_id,
            zoom_meeting_id=session.zoom_meeting_id,
            status=status,
            rtms_stream_id=state.rtms_stream_id if state else None,
            transcript_chunk_count=state.transcript_chunk_count if state else 0,
            last_transcript_at=state.last_transcript_at if state else None,
            last_error=state.last_error if state else None,
            updated_at=state.updated_at if state else session.started_at,
        )

    # -------------------------------------------------------------- Webhooks

    def verify_webhook(self, headers: dict[str, str], raw_body: bytes) -> None:
        """Reject webhook deliveries that are unsigned, stale, or forged.

        Args:
            headers: Lower-cased request headers.
            raw_body: Exact request body bytes.

        Raises:
            AppError: ``provider_failure`` when credentials are missing and
                ``unauthorized`` when the signature does not verify.
        """

        secret = self._settings.zoom_webhook_secret_token
        if not secret:
            raise AppError(
                ErrorCode.PROVIDER_FAILURE,
                "Zoom webhook secret token is not configured on this backend.",
            )
        is_valid = verify_webhook_signature(
            secret,
            headers.get(WEBHOOK_TIMESTAMP_HEADER),
            headers.get(WEBHOOK_SIGNATURE_HEADER),
            raw_body,
            self._clock(),
            self._settings.zoom_webhook_tolerance_seconds,
        )
        if not is_valid:
            raise AppError(ErrorCode.UNAUTHORIZED, "Zoom webhook signature is invalid.")

    async def handle_webhook(
        self, event: ZoomWebhookEvent
    ) -> ZoomWebhookAck | ZoomUrlValidationResponse:
        """Process one verified Zoom webhook event.

        Args:
            event: Parsed webhook envelope.

        Returns:
            The URL-validation challenge answer or a lifecycle acknowledgement.

        Raises:
            AppError: ``validation_failed`` when a known event has a malformed
                payload.
        """

        if event.event == URL_VALIDATION_EVENT:
            plain_token = event.payload.get("plainToken")
            if not isinstance(plain_token, str) or not plain_token:
                raise AppError(ErrorCode.VALIDATION_FAILED, "plainToken is required.")
            secret = self._settings.zoom_webhook_secret_token or ""
            return ZoomUrlValidationResponse(
                **build_url_validation_response(secret, plain_token)
            )
        if event.event == RTMS_STARTED_EVENT:
            started = self._parse_payload(RtmsStartedPayload, event.payload)
            return await self._handle_rtms_started(started)
        if event.event == RTMS_STOPPED_EVENT:
            stopped = self._parse_payload(RtmsStoppedPayload, event.payload)
            return await self._handle_rtms_stopped(stopped)
        return ZoomWebhookAck(status=WEBHOOK_IGNORED, event=event.event)

    @staticmethod
    def _parse_payload[T: BaseModel](model: type[T], payload: dict[str, Any]) -> T:
        try:
            return model.model_validate(payload)
        except ValueError as exc:
            raise AppError(
                ErrorCode.VALIDATION_FAILED, "Zoom webhook payload is malformed."
            ) from exc

    def _find_session_for_meeting(
        self, meeting_uuid: str, meeting_id: str | int | None
    ) -> LectureSession | None:
        candidates = {meeting_uuid}
        if meeting_id is not None:
            candidates.add(str(meeting_id))
        for session in self._store.sessions.values():
            if session.status == SessionStatus.ENDED or not session.zoom_meeting_id:
                continue
            bound = session.zoom_meeting_id.strip()
            if bound in candidates or bound.replace(" ", "") in candidates:
                return session
        return None

    async def _handle_rtms_started(self, payload: RtmsStartedPayload) -> ZoomWebhookAck:
        session = self._find_session_for_meeting(payload.meeting_uuid, payload.meeting_id)
        if session is None or not self._settings.zoom_rtms_configured():
            return ZoomWebhookAck(status=WEBHOOK_IGNORED, event=RTMS_STARTED_EVENT)
        state = self._states.setdefault(session.session_id, _SessionStreamState())
        if state.stream is not None and state.rtms_stream_id == payload.rtms_stream_id:
            return ZoomWebhookAck(status=WEBHOOK_ACCEPTED, event=RTMS_STARTED_EVENT)
        await self._stop_stream(state)
        await self.start_stream(session, payload)
        return ZoomWebhookAck(status=WEBHOOK_ACCEPTED, event=RTMS_STARTED_EVENT)

    async def _handle_rtms_stopped(self, payload: RtmsStoppedPayload) -> ZoomWebhookAck:
        for state in self._states.values():
            if state.rtms_stream_id == payload.rtms_stream_id:
                await self._stop_stream(state)
                state.status = ZoomRtmsStreamStatus.STOPPED
                state.touch()
                return ZoomWebhookAck(status=WEBHOOK_ACCEPTED, event=RTMS_STOPPED_EVENT)
        return ZoomWebhookAck(status=WEBHOOK_IGNORED, event=RTMS_STOPPED_EVENT)

    async def stop_session(self, session_id: str) -> None:
        """Close the RTMS stream for a session that has ended.

        Args:
            session_id: Session whose transcript stream should stop.

        Side effects:
            Cancels the stream task and marks the status ``stopped`` when a
            stream was running; a session without a stream is left untouched.
        """

        state = self._states.get(session_id)
        if state is None or (state.stream is None and state.task is None):
            return
        await self._stop_stream(state)
        state.status = ZoomRtmsStreamStatus.STOPPED
        state.touch()

    # --------------------------------------------------------------- Streams

    async def start_stream(
        self, session: LectureSession, payload: RtmsStartedPayload
    ) -> asyncio.Task[None]:
        """Open the RTMS transcript stream for a session in a background task.

        Args:
            session: Bound lecture session.
            payload: Verified ``meeting.rtms_started`` payload.

        Returns:
            The task running the stream until it closes or fails.
        """

        client_id = self._settings.zoom_client_id or ""
        client_secret = self._settings.zoom_client_secret or ""
        state = self._states.setdefault(session.session_id, _SessionStreamState())
        state.rtms_stream_id = payload.rtms_stream_id
        state.last_error = None
        state.status = ZoomRtmsStreamStatus.CONNECTING
        state.touch()

        clock_origin_epoch_ms = parse_clock_origin_epoch_ms(session.session_clock_origin)

        async def ingest(message: RtmsTranscriptMessage) -> None:
            await self._ingest_transcript(
                session.session_id, payload.rtms_stream_id, clock_origin_epoch_ms, message
            )

        def observe(stream_state: str) -> None:
            if stream_state == STATE_STREAMING:
                state.status = ZoomRtmsStreamStatus.STREAMING
                state.touch()

        stream = self._stream_factory(
            meeting_uuid=payload.meeting_uuid,
            rtms_stream_id=payload.rtms_stream_id,
            signaling_url=payload.signaling_url(),
            client_id=client_id,
            client_secret=client_secret,
            on_transcript=ingest,
            connector=self._connector,
            on_state_change=observe,
        )
        state.stream = stream
        task = asyncio.get_running_loop().create_task(self._run_stream(state, stream))
        state.task = task
        return task

    async def _run_stream(
        self, state: _SessionStreamState, stream: ZoomRtmsTranscriptStream
    ) -> None:
        try:
            await stream.run()
            if state.status != ZoomRtmsStreamStatus.FAILED:
                state.status = ZoomRtmsStreamStatus.STOPPED
        except (RtmsHandshakeError, RtmsStreamClosed) as exc:
            state.status = ZoomRtmsStreamStatus.FAILED
            state.last_error = str(exc) or exc.__class__.__name__
            LOGGER.warning("Zoom RTMS stream ended with a provider error.")
        except asyncio.CancelledError:
            state.status = ZoomRtmsStreamStatus.STOPPED
            raise
        except Exception:  # noqa: BLE001 - never let a provider fault kill the loop.
            state.status = ZoomRtmsStreamStatus.FAILED
            state.last_error = "Zoom RTMS stream failed unexpectedly."
            LOGGER.exception("Zoom RTMS stream failed unexpectedly.")
        finally:
            if state.stream is stream:
                state.stream = None
                state.task = None
            state.touch()

    async def _stop_stream(self, state: _SessionStreamState) -> None:
        stream, task = state.stream, state.task
        state.stream = None
        state.task = None
        if stream is not None:
            await stream.stop()
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _ingest_transcript(
        self,
        session_id: str,
        rtms_stream_id: str,
        clock_origin_epoch_ms: int,
        message: RtmsTranscriptMessage,
    ) -> None:
        session = self._store.sessions.get(session_id)
        state = self._states.get(session_id)
        if session is None or state is None:
            return
        if session.status == SessionStatus.ENDED:
            # Ended sessions accept no more transcript; close the provider
            # stream from outside the receive loop it is currently inside.
            asyncio.get_running_loop().create_task(self.stop_session(session_id))
            return
        chunk = map_transcript_message(
            message,
            session_id=session_id,
            rtms_stream_id=rtms_stream_id,
            clock_origin_epoch_ms=clock_origin_epoch_ms,
            max_text_chars=self._settings.max_transcript_text_chars,
            include_speaker_label=True,
        )
        if chunk is None:
            return
        owner = self._store.users.get(session.owner_id)
        actor = AuthenticatedActor(
            user_id=session.owner_id, role=owner.role if owner else ROLE_PROFESSOR
        )
        try:
            self._transcript_service.ingest_batch(
                actor,
                session_id,
                IngestTranscriptRequest(lecture_id=session.lecture_id, chunks=[chunk]),
            )
        except AppError as exc:
            if exc.code == ErrorCode.DUPLICATE:
                return
            LOGGER.warning("Zoom transcript chunk rejected: %s", exc.code.value)
            return
        state.transcript_chunk_count += 1
        state.last_transcript_at = utc_now_iso()
        state.touch()

    async def shutdown(self) -> None:
        """Stop every running stream; called from application shutdown."""

        for state in list(self._states.values()):
            await self._stop_stream(state)
