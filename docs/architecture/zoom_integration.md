# Zoom Realtime Transcript Integration

**Status:** Implemented (transcript streaming); OAuth linking planned  
**Owner:** Backend and Frontend teams  
**Last updated:** 2026-09-20

## Purpose

Feed the live captions of a Zoom meeting into a Bloom lecture session so
students and professors see the transcript as it is spoken, without Bloom ever
receiving meeting audio or video.

Zoom Realtime Media Streams (RTMS) pushes meeting media to an app over
WebSockets. Bloom requests **transcript media only**. Each transcript message is
converted into the canonical `TranscriptChunk` contract, persisted through the
existing transcript service, and fanned out to authorized session clients over
the existing session WebSocket.

Related documents:

- [Unified API Contracts](../api/unified_api_contracts.md) — Zoom REST routes and `transcript.chunk.created`
- [AsyncAPI](../api/asyncapi.yaml) — session WebSocket messages
- `shared/contracts/transcript_chunk.schema.json`, `zoom_rtms_status.schema.json`, `start_zoom_rtms_request.schema.json`

## Boundaries

| Layer | Location | Responsibility |
|---|---|---|
| Provider protocol | `backend/app/integrations/zoom/protocol.py` | RTMS message types, HMAC signatures, webhook verification, transcript parsing and mapping |
| Provider transport | `backend/app/integrations/zoom/rtms_client.py` | Signaling + media WebSocket handshakes, keep-alive, transcript receive loop |
| Session orchestration | `backend/app/integrations/zoom/service.py` | Link sessions to meetings, react to webhooks, run one stream per session, report status |
| REST routes | `backend/app/integrations/zoom/routes.py` | Thin handlers for webhooks, `rtms/start`, and `status` |
| Canonical ingestion | `backend/app/transcript/service.py` | Existing validation, revision handling, storage, and event publication |
| Live fan-out | `backend/app/ws/` | Existing session-scoped WebSocket publisher with membership checks |
| Desktop bridge | `frontend/src/main/session_events.ts` | Main-process WebSocket subscriber; bearer token never leaves the main process |
| Renderer | `frontend/src/renderer/services/live_session_events.mts` | Validates envelopes, merges chunks by `chunk_id`/`revision`, keeps lecture-time order |

Nothing outside `backend/app/integrations/zoom/` knows about RTMS message
types. Only typed `TranscriptChunk` values cross into the application.

## End-to-end flow

```text
Professor (Electron)                    Bloom backend                                Zoom
────────────────────                    ─────────────                                ────
POST /sessions/{id}/zoom/rtms/start ──► ZoomRtmsService.link_session
   {zoom_meeting_id | zoom_join_url}    parse_zoom_join_url ➜ meeting id + pwd
                                        session.zoom_meeting_id = <id>
                                        session.zoom_join_url = <normalized https>
                                        status = awaiting_stream
                                                                     ◄── POST /integrations/zoom/webhooks
                                        verify x-zm-signature / timestamp        meeting.rtms_started
                                        match meeting_uuid | meeting_id
                                        start ZoomRtmsTranscriptStream
                                        ── signaling handshake (msg_type 1) ────────►
                                        ◄── media_server.server_urls.transcript ────
                                        ── media handshake (msg_type 3, media_type 8) ►
                                        ── client ready ack (msg_type 7) ────────────►
                                        ◄── MEDIA_DATA_TRANSCRIPT (msg_type 17) ─────
                                        map ➜ TranscriptChunk(source=zoom_rtms)
                                        TranscriptService.ingest_batch
                                        publish transcript.chunk.created
Student / professor (Electron) ◄──────── /ws/v1/sessions/{id} (members only)
   renderer upserts chunk, repaints
                                                                     ◄── meeting.rtms_stopped
                                        close stream, status = stopped
```

Keep-alive requests (`msg_type` 12) are answered with `msg_type` 13 on both
sockets. On `meeting.rtms_stopped`, stream close, backend shutdown, or the
owner ending the lecture (`POST /sessions/{id}/end`) the stream task is
cancelled and the status becomes `stopped` (or `failed` with a sanitized
reason). Ending the lecture also publishes one `session.ended` envelope
(payload: the ended `LectureSession`) so every connected client leaves its live
state without polling.

## Timestamp mapping

Zoom transcript timestamps are Unix epoch milliseconds. Bloom's shared lecture
clock is `LectureSession.session_clock_origin` (UTC ISO 8601). Each chunk maps
as:

```text
start_ms = max(0, content.start_time - origin_epoch_ms)
end_ms   = max(start_ms + 1, content.end_time - origin_epoch_ms)
```

Messages that end before the session origin are dropped. Intervals stay
half-open with `0 <= start_ms < end_ms`, matching every other transcript source.

## Deduplication and corrections

`chunk_id` is `zoom_` plus a truncated SHA-256 of the RTMS stream id, the
Zoom participant id (or `channel`), and the message's start/end times, so a
replayed provider message maps to the same id and is rejected by
`TranscriptService` as a duplicate rather than stored twice. Corrections follow the existing revision rules: a chunk with a
higher `revision` for an existing `chunk_id` supersedes the earlier text both
in storage and in connected renderers.

## Security

- **Webhooks**: every request must carry `x-zm-request-timestamp` within
  `ZOOM_WEBHOOK_TOLERANCE_SECONDS` and an `x-zm-signature` equal to
  `v0=HMAC_SHA256(secret, "v0:{timestamp}:{raw_body}")`. `endpoint.url_validation`
  is answered with the HMAC of `plainToken`.
- **RTMS handshakes**: signed with
  `HMAC_SHA256(client_secret, "client_id,meeting_uuid,rtms_stream_id")`.
- **Authorization**: only the session owner may link a meeting; any session
  member may read status; WebSocket delivery uses the existing membership
  check. Hiding UI is never the authorization mechanism.
- **Desktop**: the JWT is appended to the WebSocket URL in the Electron main
  process only. The renderer receives validated, session-scoped envelopes over
  IPC and never sees the token.
- **Join links**: `backend/app/integrations/zoom/join_link.py` accepts only
  `https://` links on `zoom.us`, `zoom.com`, `zoomgov.com` (and subdomains)
  with a meeting or personal-room path, no userinfo, no explicit port, and at
  most a `pwd` passcode; everything else (`javascript:`, `file:`, plain HTTP,
  look-alike hosts, tracking parameters, fragments) is rejected or stripped.
  The renderer never opens URLs itself: the `zoom:open-join` IPC handler in
  `frontend/src/main/zoom_join_link.ts` re-runs the same allowlist on the
  stored URL before calling `shell.openExternal`, preferring the
  `zoommtg://<apex>/join?action=join&confno=…&pwd=…` desktop deep link and
  falling back to the normalized HTTPS URL when no Zoom client is registered.
- **Secrets**: `ZOOM_CLIENT_SECRET` and `ZOOM_WEBHOOK_SECRET_TOKEN` are read
  from settings and never logged. Error strings surfaced through
  `ZoomRtmsStatus.last_error` contain no secrets, signatures, or transcript
  text.

## Privacy

- Only `media_type` 8 (transcript) is requested from Zoom. Audio, video,
  screen share, and chat are never requested and no code path can receive
  them.
- Transcript text is treated like any other transcript source: bounded by
  `MAX_TRANSCRIPT_TEXT_CHARS`, stored per session, and covered by the
  existing retention and deletion controls.
- Speaker labels come from Zoom's participant display name and are stored in
  `speaker_label`; Zoom participant ids only contribute to the hashed
  `chunk_id` and are never stored in clear form.
- No raw media leaves the student's device; this feature adds no upload path.

## Configuration

| Variable | Purpose |
|---|---|
| `ZOOM_CLIENT_ID` | Zoom app client id used in RTMS handshake signatures |
| `ZOOM_CLIENT_SECRET` | Zoom app client secret used for RTMS HMAC; never logged |
| `ZOOM_WEBHOOK_SECRET_TOKEN` | Verifies webhook signatures and URL validation |
| `ZOOM_WEBHOOK_TOLERANCE_SECONDS` | Maximum accepted webhook age (default 300) |

When any of the first three is unset, `/zoom/status` returns `not_configured`,
`/zoom/rtms/start` fails with `provider_failure`, and the professor UI hides
the link form. Everything else in the app keeps working.

Zoom app setup (outside this repository): enable the RTMS feature and the
`meeting.rtms_started` / `meeting.rtms_stopped` event subscriptions, and point
the event notification URL at `POST /api/v1/integrations/zoom/webhooks`.

## Frontend behavior

- Professors see a **Zoom realtime transcript** panel on an active lecture
  page. Pasting a Zoom join link (sent as `zoom_join_url`) or a bare meeting
  id (sent as `zoom_meeting_id`) calls `rtms/start`; the status line follows
  `awaiting_stream → connecting → streaming → stopped`.
- When the active session carries a validated `zoom_join_url`, a **Join Zoom
  meeting** button appears in the professor panel, on the student live-lecture
  prompt and active-session card, and in the student summary header. The
  button is omitted (not merely hidden) when the link is `null` or the session
  has ended; clicking it invokes `bloomDesktop.openZoomJoinLink`, which
  resolves to `desktop`, `browser`, or `rejected` so the UI can explain a
  refused link.
- The Electron main process subscribes to `/ws/v1/sessions/{id}` for the
  active session, reconnects with exponential backoff (1 s → 30 s), sends
  `client.heartbeat` every 15 s, and stops permanently on close code 4401
  (unauthorized).
- The renderer applies `transcript.chunk.created` only when the envelope and
  payload `session_id` match the active session, merges by `chunk_id` and
  `revision`, sorts by `start_ms`, and repaints just the transcript tab so the
  student's current tab is preserved.
- On `session.ended` for the active session the renderer marks that session
  ended, drops the live status line, and unsubscribes the main-process socket.

## Testing

`backend/tests/test_zoom_rtms.py` drives the full path with an in-process fake
RTMS server injected through `create_app(rtms_connector=...)`: signaling and
media handshakes, transcript-only media request, keep-alives, timestamp
mapping, malformed frames, duplicate replay, revision behavior, provider
disconnects, signature failures, and WebSocket session isolation.
`frontend/tests/unit/zoom_live_transcript.test.cjs` covers envelope/payload
validation, revision-aware merging, subscription lifecycle, and page rendering.
`backend/tests/test_zoom_join_link.py` and
`frontend/tests/unit/zoom_join_link.test.cjs` cover the join-link allowlist on
both sides (unsafe schemes, look-alike hosts, userinfo, ports, malformed paths
and passcodes), meeting-id derivation, member-only exposure, the deep-link
then-HTTPS fallback order, and button visibility.

No test contacts Zoom. Live sandbox verification, if needed, must be an explicit
opt-in run with a Zoom developer account and synthetic meeting content.

## Open items

- OAuth `authorize`/`callback` routes are documented in the API contract but
  not implemented: the repository has no approved encrypted token store yet.
  RTMS handshakes only need the app credentials, so transcript streaming does
  not depend on it.
- Zoom's provisional (non-final) transcript variants are not requested; every
  chunk is stored as `is_final = true` with `revision = 1`.
