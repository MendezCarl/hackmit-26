# Backend implementation status

Status: Three feature branches implemented and pushed; host integration pending

Owner: Backend team

Last updated: 2026-09-19

## What this report records

This is a handoff for the work completed in this development session. It separates
implemented behavior, synthetic demonstrations, verified checks, and future work.
It does not replace [AGENTS.md](../../AGENTS.md), the
[contract precedence](../README.md#contract-source-of-truth-order), or an actual
inspection of the branch being used.

Three backend features were implemented: signal/transcript ingestion and the
lecture timeline; anonymous professor aggregation; and scoped Dropbox materials
and artifact export. Each feature was committed and pushed on its own branch.
No frontend, Electron, or React code was changed in this work. No feature branch
was merged into `backend`, `dev`, or `main` during this session.

OpenAI recovery generation was discussed and planned, not implemented. No OpenAI
calls were made and no OpenAI credits were used by this work.

## How the implemented pieces fit together

1. A local client supplies coarse observations and derived transcript text.
2. The backend validates their session, timestamps, authorization, and payloads.
3. The private timeline combines final transcript chunks with the caller's events
   and possible missed-content windows.
4. A context query selects the transcript chunks needed for a recovery interval.
5. The future recovery service will turn that context into an explanation.
6. Separate features produce threshold-safe professor summaries and export
   authorized derived artifacts to a user-selected Dropbox folder.

The combined demo exercises ingestion, context selection, a mock artifact export,
and a professor summary. Its exported card is a synthetic fixture. It does not
demonstrate an OpenAI-generated explanation or a real Dropbox account write.

## Feature 2: signal ingestion, transcripts, and timeline

### Coarse observations and student corrections

Implemented REST batch ingestion with strict Pydantic validation, bounded payloads,
and session-relative integer milliseconds. The URL selects the session; a supplied
lecture identifier must match the trusted session. Intervals are half-open:
`[start_ms, end_ms)`, with a positive duration.

Participant identity comes from the injected authorization boundary. Request-body
identity claims, unknown fields, and media-upload fields are rejected. The demo
uses fixed synthetic actors; this boundary is not a production JWT implementation.

Exact retries are duplicates. Different contents under an existing event ID are
conflicts. Batches are atomic. Only the originating participant may confirm or
dismiss an event. Original contents are preserved so a later retry cannot undo
the student's correction. Private timeline reads filter events by participant.

### Optional phone observations

`phone_visible` means that a phone appeared in the camera frame. It does not mean
that a student was distracted or failed to understand something. The backend
accepts optional local source metadata; it does not implement a camera detector.

Phone presence alone cannot create an automatic recovery window. The default
phone patterns require 20 seconds of overlap with `looking_down`, or 15 seconds
of overlap with both `window_unfocused` and `face_absent`. Gaps, dismissal,
confidence cutoffs, duplicate input, and participant separation are covered by tests.
Independent non-phone rules still apply and can qualify without phone evidence.

The [phone signal guide](../../backend/PHONE_SIGNALS.md) is the canonical human-readable
example and full rule description, including configurable confidence caps,
confirmation behavior, return markers, and explicit self-reports. These thresholds
are demo heuristics, not validated assessments of attention or comprehension.

### Transcript and context behavior

Implemented transcript REST batches and authenticated WebSocket ingestion.
Transcript records contain source IDs, intervals, finality, and revisions.
Out-of-order arrival is supported; stale/conflicting revisions and invalid
final-to-provisional transitions are rejected. Context uses final chunks only.

The timeline supports bounded reads and selected context with padding clamped to
session limits. Missing final transcript returns a typed error. Context preserves
source timestamps and transcript revision. These revisions support future cache
invalidation; a recovery cache has not yet been implemented.

Selection returns whole overlapping chunks. It is not word-level timestamp
alignment. Recovery consumers must cite actual returned sources.

The WebSocket is an ingestion acknowledgment stream with per-message permission
checks, size limits, and rejection of query credentials and binary media. It is
not a general event bus or an implemented recovery-ready notification service.

### Zoom boundary

The simulated adapter converts synthetic epoch timestamps to the trusted session
clock and submits transcript chunks through the existing ingestion path. It does
not implement live RTMS transport, OAuth, signed callbacks, audio, or video.
Its test packet format is not claimed to be Zoom's actual wire protocol.

## Feature 4: anonymous professor summaries

Implemented professor-only reads after a session ends. Reports use fixed buckets
over the session and unique consenting participants. Eligibility requires the
authoritative attendance interval to cover the entire bucket. Multiple events
from one participant do not increase the participant count.

Small groups have both counts and ratios suppressed. Reports omit private event
histories, student IDs, individual confidence, and signal categories. Consent and
corrections are applied when the report is read. Suggestions offer an optional
recap using compassionate language.

Phone events and bundles containing phone observations are excluded from professor
counts, even when confirmed. Return markers also do not contribute. Independent
non-phone evidence retains its aggregation behavior.

The demo policy is five participants and 15-second buckets. Production requires
an explicitly supplied policy; the synthetic setting is not production approval.
This is group-size suppression, not a claim of differential privacy or complete
protection from inference across reports. The anonymous clarification loop is
still planned.

## Feature 6: scoped Dropbox operations

Implemented explicit folder selection, bounded file listing, selected UTF-8 text
and Markdown reads, and export of authorized derived artifacts. Operations are
scoped by actor and session; exports require selection/confirmation and an
artifact ID resolved through the host's authorization boundary.

There is a fake provider and an adapter using the official SDK. The SDK adapter
checks metadata and download size, pins downloaded revisions, closes streams,
creates Markdown exports without overwriting, and sanitizes provider failures.
Provider-specific code is under `app/integrations/dropbox/`.

Real OAuth, encrypted token storage, and live-account verification are unfinished
host dependencies. The feature does not accept arbitrary raw-media uploads or
decode PDFs/slides. A mock receipt is labeled as mock and is not evidence of a
successful live export. Exported external copies are not automatically removed
by deleting application records.

## Shared foundation and integration limits

The features use typed interfaces, standard error handling, explicit dependency
injection, an in-memory repository, and a Motor/Mongo repository adapter.
Mongo writes use revision compare-and-swap with bounded retries. The memory
implementation is for a single-process demo and does not survive restart.

The repository has a session-deletion operation, but full retention scheduling,
per-student deletion, revocation coordination, and provider-token deletion remain
host work. These should not be described as completed production privacy controls.

There are three distinct application states:

| Application | What it contains | How to interpret it |
|---|---|---|
| Baseline `app.main` | Existing health/status endpoints | Feature routes have not been mounted here |
| Isolated feature branches | One feature's routes, tests, contracts, and shared support | Each branch is runnable independently |
| Local combined checkout, `feature/backend-lecture-features` | All three features and the synthetic integration demo | Combined changes remain uncommitted |

The original baseline OpenAPI snapshot remains a description of `app.main`.
Feature-specific snapshots describe their corresponding apps. The
[API handoff](../api/lecture_features.md) lists implemented routes and host
requirements; the [unified API catalog](../api/unified_api_contracts.md) includes
planned endpoints and must not be read as proof that all routes exist.

## Branches, commits, and verified CI

Each branch contains identical shared support needed to run independently. Shared
DTOs in a branch do not install another feature's service or endpoint. Tests verify
that unrelated feature routes are absent. Shared changes must remain synchronized
during review and integration; separate branches alone do not prevent conflicts.

| Feature branch | Implementation commit | Packaging fix / verified runtime commit | Successful CI run |
|---|---|---|---|
| `feature/backend-signal-timeline` | `b2c9a1d` | `138cff9` | [Signal timeline](https://github.com/MendezCarl/hackmit-26/actions/runs/35478095389) |
| `feature/backend-professor-aggregation` | `77a7619` | `c772618` | [Professor aggregation](https://github.com/MendezCarl/hackmit-26/actions/runs/35478095458) |
| `feature/backend-dropbox-integration` | `b2fd049` | `5c58361` | [Dropbox integration](https://github.com/MendezCarl/hackmit-26/actions/runs/35478095698) |

These runs were verified successful on 2026-09-19 for the specified commits. This
is a historical record, not a live CI dashboard. See the
[branch guide](../../backend/FEATURE_BRANCHES.md) for local worktree locations.
Those folders are local and are not included when someone clones the repository.

## Installation failure and repair

The first feature CI runs failed before tests ran. Setuptools automatically found
both `app` and `feature_tests` as top-level packages and rejected the editable
installation. Earlier testing used an existing environment and missed that clean
installation failure.

The error was reproduced in a fresh virtual environment. The fix in each branch's
`backend/pyproject.toml` declares setuptools as the build backend and explicitly
discovers only `app` and `app.*`, with namespace discovery disabled. Setuptools is
a build dependency, not a new runtime service. Test files remain in the checkout
and continue running in CI.

Each branch was then installed with its feature requirements in a separate fresh
virtual environment. Dependency, test, format, lint, type, and contract checks
passed locally; the packaging fixes were committed, pushed, and verified in CI.
The clean-environment CI installation step is the regression check for this bug.

## Verification results and their limits

| Suite | Most recent recorded passing tests | Recorded limitation |
|---|---:|---|
| Signal/timeline branch | 60 | One opt-in live Mongo test skipped |
| Professor branch | 14 | One opt-in live Mongo test skipped |
| Dropbox branch | 20 | One opt-in live Mongo test skipped |
| Combined local feature suite | 93 | One opt-in live Mongo test skipped; combined checkout is uncommitted |

Feature-branch verification also passed `pip check`, Ruff lint/format, Mypy, and
both feature and baseline contract checks. Tests use synthetic participants and
lecture text. Default suites make no live provider calls. Live Mongo persistence,
Zoom connectivity, and Dropbox account/OAuth behavior remain unverified.

The counts above record prior completed verification, not tests rerun merely for
this documentation update. API schemas and application behavior are unchanged by
the documentation update.

## Planned next work: recovery generation

OpenAI integration is ready to start against synthetic context and the existing
timeline interface. It does not require waiting for live Zoom or Dropbox. The
proposed `feature/backend-openai-recovery` branch has not been created in this work.
If timeline is still unmerged, recovery can be developed as a dependent branch
with that relationship made explicit during review.

The proposed sequence is:

1. Agree on typed context, recovery-card, job, and failure contracts.
2. Build a recovery service against a deterministic fake generator.
3. Validate authorization, source references, missing context, and failures.
4. Add the provider adapter under `app/integrations/openai/`.
5. Implement persistence, job status, bounded retries, usage accounting, and
   authorization-scoped caching tied to transcript/context revisions.
6. Run an explicit synthetic live API check after server-side configuration.

Real lecture use also requires consent specifically covering external processing
of selected text. Signal-collection consent is not automatically that permission.
The provider should receive only the necessary selected context, not raw media,
participant identity, or the observation that a phone appeared. A valid response
shape or an existing source ID does not by itself prove factual grounding.

Production JWT/session management, approved aggregation policy, retention and
deletion orchestration, Redis jobs, recovery notifications, live Zoom/Dropbox,
local transcription integration, and the clarification loop remain unfinished.
No real token-cost savings or end-to-end OpenAI recovery success has been measured.

## Where to continue

- [Feature runbook](../../backend/LECTURE_FEATURES.md): branch-specific instructions and local-only combined commands.
- [Feature branch guide](../../backend/FEATURE_BRANCHES.md): separate workspaces and runbooks.
- [Phone signal guide](../../backend/PHONE_SIGNALS.md): observation semantics and privacy.
- [API handoff](../api/lecture_features.md): routes, schemas, host responsibilities.

This report and its navigation documents are shared across the three existing
feature branches. The branch-specific `FEATURE_2.md`, `FEATURE_4.md`, or
`FEATURE_6.md` runbook identifies what is runnable in that checkout. Historical
commit IDs above identify the verified runtime code, not later documentation-only
commits. The combined application code remains local and uncommitted.
