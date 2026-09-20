# Unified API Contracts

**Status:** Proposed  
**Owner:** Frontend + Backend/ML  
**Last updated:** 2026-09-19

## Recommendation

Use three complementary contract formats:

1. **OpenAPI 3.1** for REST endpoints. FastAPI generates this contract from typed routes and Pydantic models and exposes Swagger UI at `/docs`, ReDoc at `/redoc`, and the schema at `/openapi.json`.
2. **AsyncAPI 3.1** for WebSocket channels and event messages. OpenAPI describes HTTP well but should not be stretched into the source of truth for a bidirectional event stream.
3. **JSON Schema** for reusable payloads shared by REST and WebSocket contracts.

Use FastAPI REST endpoints for durable commands and queries. Use one authenticated WebSocket connection per active lecture session for realtime updates. Do not use GraphQL for the MVP; it adds another schema/runtime layer without solving a requirement that REST plus WebSockets does not already address.

Official references:

- [OpenAPI specification](https://spec.openapis.org/oas/)
- [AsyncAPI specification](https://www.asyncapi.com/docs/reference/specification/latest)
- [FastAPI OpenAPI and automatic documentation](https://fastapi.tiangolo.com/tutorial/first-steps/)

## Contract files

```text
docs/api/
├── unified_api_contracts.md   # Human-readable catalog and rules
├── openapi.json               # Generated, checked-in REST snapshot
└── asyncapi.yaml              # WebSocket channels and events

shared/contracts/
├── error_response.schema.json
├── lecture_session.schema.json
├── signal_event.schema.json
├── transcript_chunk.schema.json
├── recovery_card.schema.json
├── professor_summary.schema.json
├── privacy_settings.schema.json
└── websocket_envelope.schema.json
```

The backend Pydantic models and reusable JSON Schemas must remain equivalent. FastAPI regenerates the live Swagger schema from route annotations and route-bound Pydantic models every time the application starts. The repository also stores `docs/api/openapi.json` so contract changes can be reviewed. Continuous integration fails when that snapshot is stale.

### Swagger and OpenAPI workflow

Run the backend and open:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Raw OpenAPI: `http://127.0.0.1:8000/openapi.json`

After adding or changing a FastAPI endpoint or any Pydantic model referenced by a route, run:

```sh
python backend/scripts/generate_openapi_contract.py
```

Verify that the committed snapshot is current with:

```sh
python backend/scripts/generate_openapi_contract.py --check
```

The generator uses Python's standard library and FastAPI's `app.openapi()` output; it does not add a YAML dependency. CI runs check mode and rejects stale contracts.

## Global conventions

| Concern | Contract |
|---|---|
| Base REST path | `/api/v1` |
| WebSocket path | `/ws/v1/sessions/{session_id}` |
| JSON property naming | `snake_case` |
| Identifiers | UUID strings unless an external provider requires another format |
| Lecture-relative time | Integer milliseconds: `start_ms`, `end_ms`, `duration_ms` |
| Wall-clock time | UTC ISO 8601 strings ending in `Z` |
| Content type | `application/json` |
| Authentication | `Authorization: Bearer <token>` for protected application routes |
| Pagination | Cursor-based: `cursor` and `limit`; response returns `next_cursor` |
| Request tracing | Optional `X-Request-ID`; backend returns the effective request ID |
| Idempotency | `Idempotency-Key` for create/finalize operations that may be retried |
| Errors | One shared `ErrorResponse` schema |
| Raw media | Never accepted by the application REST API |

## Standard error response

```json
{
  "error": {
    "code": "invalid_time_range",
    "message": "end_ms must be greater than start_ms",
    "details": {
      "field": "end_ms"
    },
    "request_id": "req_7d9d2f"
  }
}
```

Error codes are stable machine-readable `snake_case` values. Human-facing copy should not depend on the exact `message` string.

## REST endpoint catalog

### Health

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `GET` | `/health` | Liveness check | None | `HealthResponse` |
| `GET` | `/ready` | Dependency readiness | None | `ReadinessResponse` |

### Current user and privacy

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/users/me` | Return the current user profile | None | `UserProfile` |
| `GET` | `/api/v1/users/me/privacy-settings` | Read consent, retention, and sharing settings | None | `PrivacySettings` |
| `PUT` | `/api/v1/users/me/privacy-settings` | Replace privacy settings | `PrivacySettingsUpdate` | `PrivacySettings` |
| `DELETE` | `/api/v1/users/me/data` | Request deletion of stored application data | `DataDeletionRequest` | `DeletionReceipt` |

No privacy-settings endpoint can enable raw webcam or raw system-audio upload because the API does not accept those payloads.

### Lecture sessions

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/sessions` | Start a lecture session and establish its clock | `CreateSessionRequest` | `LectureSession` |
| `GET` | `/api/v1/sessions/by-join-code/{join_code}` | Resolve a human-typeable code to an active lecture session | Path parameter | `LectureSession` |
| `GET` | `/api/v1/sessions/{session_id}` | Read session status and metadata | None | `LectureSession` |
| `PATCH` | `/api/v1/sessions/{session_id}` | Update allowed session metadata | `UpdateSessionRequest` | `LectureSession` |
| `POST` | `/api/v1/sessions/{session_id}/end` | End a session idempotently | `EndSessionRequest` | `LectureSession` |
| `GET` | `/api/v1/sessions` | List the current user's sessions | Query parameters | `PaginatedLectureSessions` |

### Privacy-preserving signal events

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/sessions/{session_id}/events/batch` | Submit coarse timestamped events or already-aggregated buckets | `SignalEventBatch` | `SignalEventBatchReceipt` |
| `GET` | `/api/v1/sessions/{session_id}/timeline` | Read the authorized merged timeline | `start_ms`, `end_ms`, `cursor`, `limit` | `TimelinePage` |
| `PATCH` | `/api/v1/sessions/{session_id}/events/{event_id}` | Record student confirmation/correction | `SignalEventFeedback` | `SignalEvent` |

The event API accepts labels and timestamps, not images, video frames, or raw audio.

### Transcript chunks

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/sessions/{session_id}/transcript-chunks/batch` | Submit permitted timestamped transcript chunks | `TranscriptChunkBatch` | `TranscriptChunkBatchReceipt` |
| `GET` | `/api/v1/sessions/{session_id}/transcript` | Retrieve an authorized transcript interval | `start_ms`, `end_ms` | `TranscriptInterval` |

For Zoom sessions, transcript chunks normally originate from RTMS. For non-Zoom sessions, they originate from the team's selected local or external transcription path.

### Recovery cards

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/sessions/{session_id}/recovery-cards` | Generate a grounded recovery card for a missed interval | `CreateRecoveryCardRequest` | `RecoveryCardJob` |
| `GET` | `/api/v1/sessions/{session_id}/recovery-cards` | List recovery cards | `cursor`, `limit` | `PaginatedRecoveryCards` |
| `GET` | `/api/v1/sessions/{session_id}/recovery-cards/{card_id}` | Read one recovery card | None | `RecoveryCard` |
| `PATCH` | `/api/v1/sessions/{session_id}/recovery-cards/{card_id}` | Save review state or student feedback | `RecoveryCardUpdate` | `RecoveryCard` |
| `POST` | `/api/v1/sessions/{session_id}/recovery-cards/{card_id}/questions` | Ask a grounded follow-up question | `RecoveryQuestionRequest` | `RecoveryQuestionResponse` |

Generation should be asynchronous. The POST route returns a job immediately, and the WebSocket later emits `recovery_card.completed` or `recovery_card.failed`.

### Professor summary

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/sessions/{session_id}/professor-summary/finalize` | Finalize the post-lecture aggregate report | `FinalizeProfessorSummaryRequest` | `ProfessorSummaryJob` |
| `GET` | `/api/v1/sessions/{session_id}/professor-summary` | Read the final authorized report | None | `ProfessorSummary` |

The summary response must omit identities and individual event histories. It returns metrics only when the team-defined minimum participation threshold is satisfied.

### Zoom integration

| Method | Path | Audience | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/integrations/zoom/authorize` | User-facing | Begin Zoom authorization |
| `GET` | `/api/v1/integrations/zoom/callback` | Provider callback | Complete authorization |
| `POST` | `/api/v1/integrations/zoom/webhooks` | Zoom only | Receive verified lifecycle events |
| `POST` | `/api/v1/sessions/{session_id}/zoom/rtms/start` | Host/admin | Request an RTMS stream when permitted |
| `GET` | `/api/v1/sessions/{session_id}/zoom/status` | User-facing | Return Meeting SDK/RTMS status |

RTMS media transport is handled by the Zoom integration layer and is not modeled as a public JSON upload endpoint.

### Dropbox integration

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/integrations/dropbox/authorize` | Begin Dropbox authorization | None | Redirect |
| `GET` | `/api/v1/integrations/dropbox/callback` | Complete authorization | Provider query | Redirect |
| `GET` | `/api/v1/integrations/dropbox/files` | Browse authorized course files | `path`, `cursor`, `limit` | `DropboxFilePage` |
| `POST` | `/api/v1/sessions/{session_id}/dropbox/materials` | Attach selected course materials | `AttachDropboxMaterialsRequest` | `AttachedMaterialList` |
| `POST` | `/api/v1/sessions/{session_id}/dropbox/exports` | Export a selected derived artifact | `DropboxExportRequest` | `DropboxExportReceipt` |

### Cost and evaluation metrics

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/sessions/{session_id}/cost-metrics` | Compare optimized and baseline LLM cost | None | `TokenCostMetrics` |
| `POST` | `/api/v1/sessions/{session_id}/evaluation/recovery-feedback` | Submit recovery-card quality feedback | `RecoveryEvaluation` | `EvaluationReceipt` |

## WebSocket contract

### Connection

```text
wss://<host>/ws/v1/sessions/{session_id}?access_token=<short_lived_token>
```

Prefer an authorization header when the client/runtime permits it. If a query token is required, it must be short-lived and must never appear in logs.

### Event envelope

```json
{
  "event_id": "evt_123",
  "event_type": "transcript.chunk.created",
  "schema_version": "1.0.0",
  "session_id": "session_123",
  "occurred_at": "2026-09-19T17:30:00Z",
  "sequence_number": 42,
  "payload": {}
}
```

### Server-to-client events

| Event type | Payload | Purpose |
|---|---|---|
| `session.started` | `LectureSession` | Confirm the session clock |
| `session.status_changed` | `SessionStatusChanged` | Report meeting/capture state |
| `transcript.chunk.created` | `TranscriptChunk` | Stream permitted transcript text |
| `signal.window.updated` | `MissedContentWindow` | Update the student's local recovery window |
| `recovery_card.started` | `RecoveryCardJob` | Show generation progress |
| `recovery_card.completed` | `RecoveryCard` | Display the final recovery card |
| `recovery_card.failed` | `JobFailure` | Report a recoverable failure |
| `professor_summary.ready` | `ProfessorSummaryAvailable` | Notify authorized professor clients |
| `integration.status_changed` | `IntegrationStatus` | Report Zoom/Dropbox state |
| `session.ended` | `LectureSession` | End the live session |
| `error.occurred` | `ErrorResponse` | Report a typed connection error |

### Client-to-server events

| Event type | Payload | Purpose |
|---|---|---|
| `client.heartbeat` | `Heartbeat` | Maintain connection health |
| `session.subscribe` | `SessionSubscription` | Select authorized event categories |
| `recovery_card.cancel` | `CancelJobRequest` | Cancel work when supported |

Do not stream raw local signal frames to the server. Periodic anonymous aggregates should use the REST batch endpoint unless the team explicitly proves that realtime event transport is required.

## Core schema summaries

### `LectureSession`

- `session_id`
- `owner_id`
- `course_id`
- `title`
- `mode`: `zoom` or `in_person`
- `status`: `created`, `active`, `ending`, `ended`, or `failed`
- `started_at`
- `ended_at`
- `session_clock_origin`
- `zoom_meeting_id` when authorized

### `SignalEvent`

- `event_id`
- `session_id`
- `event_type`
- `start_ms`
- `end_ms`
- `signals`
- `confidence`
- `user_confirmed`
- `client_generated_at`

### `TranscriptChunk`

- `chunk_id`
- `session_id`
- `start_ms`
- `end_ms`
- `text`
- `speaker_label` when permitted
- `source`: `zoom_rtms`, `local_transcription`, or `external_transcription`
- `is_final`

### `RecoveryCard`

- `card_id`
- `session_id`
- `source_event_ids`
- `topic`
- `what_you_missed`
- `key_facts`
- `example_from_lecture`
- `source_timestamps`
- `follow_up_question`
- `model_metadata`
- `created_at`

### `ProfessorSummary`

- `summary_id`
- `session_id`
- `participant_count`
- `minimum_group_size`
- `aggregation_window_ms`
- `highest_signal_intervals`
- `timeline_buckets`
- `suggested_actions`
- `generated_at`

The professor summary must not include student IDs, names, device IDs, or individual confidence values.

## Contract-change process

1. Update the relevant JSON Schema in `shared/contracts/`.
2. Update the FastAPI Pydantic model and route annotation.
3. Regenerate `docs/api/openapi.json` with `python backend/scripts/generate_openapi_contract.py`.
4. Update `docs/api/asyncapi.yaml` when a WebSocket event changes.
5. Regenerate frontend types.
6. Update examples and contract tests.
7. Obtain one frontend and one backend review for changes under `shared/contracts/` or `docs/api/`.

Breaking changes require a new API or event schema version. Do not silently rename or remove fields consumed by the other team.

## Definition of done for an endpoint

- Request and response Pydantic models exist.
- Every field has a type, description, and example where useful.
- Inputs, outputs, errors, authentication, and privacy behavior are documented.
- OpenAPI generation includes the endpoint.
- `python backend/scripts/generate_openapi_contract.py --check` passes.
- The frontend uses generated or contract-checked types.
- Unit and integration tests cover success and error behavior.
- No real student data or raw media appears in fixtures.
