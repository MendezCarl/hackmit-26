# Lecture feature contracts and handoff

Status: Implemented, pending frontend/backend contract review and host integration

Owner: Backend team

Last updated: 2026-09-19

## Scope and ownership

This handoff describes features 2, 4 and 6 across three separate branches. Each
branch registers only its installed feature. This document does not imply that
every route below exists in every checkout. It does not implement the host's
authentication, sessions CRUD, recovery generation, job queue, cost accounting,
OAuth, or encrypted provider-token storage. No frontend files are changed.
Transcript WebSocket ingestion is included in feature 2; a general broadcast bus
and other live application updates remain outside this package.

The existing `app/main.py`, baseline contract generator, and baseline
OpenAPI/AsyncAPI files are unchanged. The dependency manifest was updated with an
explicit setuptools build backend and application-only package discovery to fix
fresh installations. The host integrates by calling
`register_features(app, services)` from `app.timeline.application` after creating
the explicitly injected dependencies. The separate demo app exercises these
features immediately with synthetic access and provider fakes.

See [implementation status](../implementation/backend_status.md) for the feature
commits, CI evidence, and remaining work. This handoff describes the combined
local package as well as the isolated features; each branch publishes its own
feature-specific snapshots and synthetic payload builders.

## Canonical feature payloads

The links below point to verified committed artifacts, so they work from any
feature branch. On the matching branch, the same files are available locally.

| Feature | JSON Schema | OpenAPI | Synthetic payload builders |
|---|---|---|---|
| 2 | [Schema](https://github.com/MendezCarl/hackmit-26/blob/138cff9/shared/contracts/signal_timeline.schema.json) | [OpenAPI](https://github.com/MendezCarl/hackmit-26/blob/138cff9/docs/api/signal_timeline.openapi.json) | [Examples](https://github.com/MendezCarl/hackmit-26/blob/138cff9/backend/feature_tests/signal_timeline/factories.py) |
| 4 | [Schema](https://github.com/MendezCarl/hackmit-26/blob/c772618/shared/contracts/professor_aggregation.schema.json) | [OpenAPI](https://github.com/MendezCarl/hackmit-26/blob/c772618/docs/api/professor_aggregation.openapi.json) | [Examples](https://github.com/MendezCarl/hackmit-26/blob/c772618/backend/feature_tests/professor_aggregation/factories.py) |
| 6 | [Schema](https://github.com/MendezCarl/hackmit-26/blob/5c58361/shared/contracts/dropbox_integration.schema.json) | [OpenAPI](https://github.com/MendezCarl/hackmit-26/blob/5c58361/docs/api/dropbox_integration.openapi.json) | [Examples](https://github.com/MendezCarl/hackmit-26/blob/5c58361/backend/feature_tests/dropbox_integration/factories.py) |

[Transcript AsyncAPI](https://github.com/MendezCarl/hackmit-26/blob/138cff9/docs/api/signal_timeline.asyncapi.json)
belongs to the signal/timeline branch. The combined `lecture_features.*` snapshots
and combined fixture file remain local to the uncommitted integration checkout;
they are not required to use these published feature contracts.

The feature snapshot includes explicitly labeled demo routes; production registration
omits those routes. The existing `openapi.json` still describes the original app.
The generator and drift tests keep these separate documents equivalent to their
respective app/model definitions. The host integrator regenerates the original snapshot after
mounting the features. Consumer type generation is a handoff task; frontend files
must not be edited as part of this backend-only assignment.

## Implemented HTTP routes

All application paths below are under `/api/v1/sessions/{session_id}`. Bearer
membership is required; the host supplies roles and current consent. Event,
transcript, timeline, and Zoom simulation routes belong to feature 2; professor
summary belongs to feature 4; Dropbox routes belong to feature 6. The `/demo/end`
route is available only in explicit synthetic demo apps.

| Method | Suffix | Authorization and behavior |
|---|---|---|
| POST | `/events/batch` | Own consented coarse events; atomic batch |
| POST | `/signals` | Alias using exactly the same payload and service |
| PATCH | `/events/{event_id}` | Owner-only confirmation/dismissal |
| POST | `/transcript-chunks/batch` | Authorized transcript producer only |
| GET | `/timeline` | Final text plus only the caller's events/windows |
| GET | `/transcript` | Selected final context with bounded padding |
| GET | `/professor-summary` | Professor, ended session, approved policy |
| PUT | `/dropbox/folder` | Explicit non-root folder choice for the actor/session |
| GET | `/dropbox/files` | Paginated text-file metadata within the chosen folder |
| POST | `/dropbox/materials` | Selected bounded UTF-8 text or Markdown source |
| POST | `/dropbox/exports` | Authorized derived artifact ID and explicit confirmation |

No unversioned `/sessions/...` route is added. Demo-only routes are
`/zoom/simulated-transcript-chunks` and `/demo/end` beneath the same session prefix.

The WebSocket path is `/ws/v1/sessions/{session_id}`. Send the bearer credential
in the upgrade header. Each `transcript.batch.submitted` receives a typed
`transcript.batch.accepted` or `error.occurred` envelope. Sequences are per connection;
this is an ingestion acknowledgment stream, not a replayable broadcast history.
Credentials/producer permissions are checked at connection and again per message.
The connection closes after 60 idle seconds. Query credentials and binary frames
are rejected. The host must configure a matching transport-level frame size limit.

## Timeline semantics

- The URL selects the session; `lecture_id` in input must match the trusted session.
- Every interval is half-open `[start_ms, end_ms)`, with integer milliseconds.
- Session duration is bounded to eight hours; reads span at most ten minutes.
- Up to 100 items fit in a batch. JSON bodies and WS frames are limited to 256000 bytes.
- A signal ID is unique within a participant/session. Exact request retries are
  no-ops; different content under the same ID is a 409. Retrying the original
  request never undoes a later confirmation/dismissal.
- Transcript IDs are session-scoped. Revisions increase for corrections/finality;
  stale/conflicting revisions and final-to-provisional transitions fail with 409.
- Chunks may arrive out of order. Reads sort them and exclude provisional text.
- A transcript write increments the transcript revision for cache invalidation.
- Whole overlapping chunks retain their original timestamps; text cannot be cut
  to word boundaries without word alignment. Recovery must cite actual sources.
- Padding is zero to 30000 ms and clamped to the session. Empty final context is a
  typed 409, never invented text. No OpenAI call happens in this package.
- Signals are uncertain observations. Configurable demo duration/confidence/gap
  heuristics merge possible missed windows. Confirmation can override the usual
  non-phone thresholds; phone-only observations remain insufficient, even when
  confirmed. Dismissal excludes an event. See the [phone rules](../../backend/PHONE_SIGNALS.md)
  for corroboration, passive markers, and explicit self-reports. These are not
  empirically validated attention rules.
- Ingestion stops when the trusted session ends. The owner may still correct signals.

## Professor privacy

Production requires an explicitly injected `AggregationPolicy`; there is no
silent production default. The demo uses five participants and 15000-ms buckets,
marked `synthetic-demo-only`. This is not team approval of a real privacy policy.

The denominator is the set of distinct, opted-in participants whose authoritative
attendance covers the entire bucket. Each participant contributes at most one
eligible non-dismissed coarse-signal indication per bucket. Phone events, bundles
containing phone observations, and return markers do not contribute. Small groups receive null
counts and ratios, including in ranked intervals and suggestions. No individual
events, confidence values, student IDs or signal categories appear in reports.
Reports always use fixed full-session buckets; callers cannot filter by subgroup.
Current consent and corrections are applied at read time. This is threshold-based
suppression, not a claim of differential privacy or protection against all inference.

## Host dependency contract

`FeatureServices` in `app/timeline/dependencies.py` exposes the interfaces used by
the installed feature. The combined app needs all of them; isolated apps configure
only their relevant services:

1. `SessionAccess.authorize(token, session_id)` returning a validated `SessionGrant`.
   The host verifies JWT signature/expiry, membership, role and consent. The feature
   boundary checks returned session binding as well. Tokens never come from bodies.
2. `SessionAccess.participants(session_id)` returning current authoritative opted-in
   attendance, not a list inferred from signal submissions. Participant keys must
   be stable for deduplication and private to the backend.
3. A `SessionRepository`: memory for single-process tests/demo, or the provided
   Motor `MongoSessionRepository` with an injected collection. The host owns client
   lifecycle, encryption-at-rest policy, retention scheduling and access revocation.
4. `ArtifactReader.read(grant, artifact_id)` returning an authorized, derived
   recovery card/review note. Cross-user/session access must fail. Raw upload bytes
   cannot substitute for an artifact ID.
5. `SdkDropboxGateway(client_for_actor)` resolving each actor's authorized SDK
   client using the host's OAuth and approved encrypted credential store. Configure
   finite provider timeouts and bounded retries. The feature never persists tokens.

The host installs equivalent bounded-JSON middleware and sanitized infrastructure
error handling. Feature routes already redact validation/domain/provider errors
without overriding unrelated host handlers. Production ingress must also enforce
request-rate limits and the WS frame limit. No raw transcript/token logging is added.

## Storage and deletion

One bounded document per session holds the lecture features' derived content. Mongo updates
use `_id` plus revision compare-and-swap; a conflicting write retries at most five
times. Batches fail atomically. The adapter supports multiple processes; the memory
fake does not persist or coordinate across processes.

Limits are 5000 signal records, 1000 transcript chunks and 1000 folder links per
session. This is a bounded hackathon storage design, not an unbounded lecture archive.
The host must revoke session access before calling `repository.delete(session_id)`
so concurrent authorized writers cannot recreate deleted data. Per-student deletion
and provider-token revocation must be coordinated by the host before production.
Dropbox exports are explicitly external user-selected copies; app deletion must
explain that those copies are not automatically removed.

## Provider boundaries and honest status

Zoom support is a deterministic synthetic text-packet adapter with epoch-to-session
mapping. It does not implement RTMS transport, OAuth, webhooks, audio or video. The
simulated packet schema is not represented as Zoom's actual wire format. This
satisfies the assignment's simulated-packet option. Real RTMS requires a separately
verified transcript-only producer with host approval and callback verification.
Local faster-whisper is outside this server: local clients submit derived chunks.

The live Dropbox adapter uses the [official SDK](https://dropbox-sdk-python.readthedocs.io/en/latest/api/dropbox.html).
Only explicitly selected `.txt` and `.md` supporting files are read. PDF/slide
decoding and raw media are unsupported. Metadata is checked before downloads;
downloads pin a revision, enforce a byte cap, and close response streams. Exports
create Markdown files without overwrite/autorename. Mock receipts say `mock`;
live receipts require an actual SDK response. Provider errors contain no private paths
or credentials. No live provider was contacted during implementation tests.

There are no OAuth endpoints until the host supplies the required approved token
storage/auth layer. Do not substitute a shared account token or plaintext token file.

## Verification and dependencies

See [the runbook](../../backend/LECTURE_FEATURES.md). Tests are synthetic by default, cover
runtime/JSON schema agreement, and check contract snapshots. A separate environment-
gated local Mongo test verifies actual CAS behavior when a disposable Mongo server
is available. Dropbox SDK method shapes use real SDK metadata objects with fake I/O;
live account/scopes/OAuth behavior remains unverified until credentials are supplied.

## Optional phone observations

The shared `SignalEvent` schema now includes `phone_visible`, additional coarse
observations, and optional local `source` metadata. See the
[canonical phone example and behavior](../../backend/PHONE_SIGNALS.md).
Phone-related input is private recovery evidence and excluded from professor aggregates.
