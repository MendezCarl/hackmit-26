# ADR 0002: Implement the learning plans on the current backend contracts

Status: Implemented locally; contract review pending. Not approval of production reporting thresholds or a vision model.

Owner: Backend team

Last updated: 2026-09-19

## Context

The plan branches `docs/professor-metrics-ai-plan` (`c882e6f`) and
`docs/local-object-detection` (`d5500e8`) propose features, not canonical wire
contracts. Backend commit `88d7bbb` arrived during implementation and already
contains a composed mock recovery pipeline. Its Pydantic models, corresponding
shared schemas and established paths are the compatibility baseline. The earlier
isolated feature branches remain separate; they are not silently overwritten.

## Decisions

1. Retain `session_id` as one running occurrence and `lecture_id` as its lecture.
   New routes derive session from their URL and identity from verified JWTs. All
   new intervals are half-open integer milliseconds `[start_ms, end_ms)`, bounded
   to eight hours. Recovery requests select at most ten minutes.
2. Keep baseline `/transcript/batch`, `/recovery/jobs` and `/recovery/cards/{card_id}`.
   Add `/transcript-chunks/batch`, `/recovery-cards` and
   `/recovery-cards/{card_id}` aliases to match the earlier unified API catalog.
   Do not silently rename existing request bodies; transcript batches still carry
   `lecture_id`, and chunks still carry `session_id` as in the new baseline.
3. Introduce dedicated `/coverage/batch` and `/delivery-events/batch` resources.
   Delivery uses the local detection plan's `signal_type`, not student
   `event_type`. It is a different domain. Do not map presenter absence to a
   student's absence or create student recovery windows from delivery events.
4. A coverage record explicitly says whether a local observation interval was
   available. Missing records are unknown. Overlapping available records are
   unioned, never summed. Any unavailable span invalidates that participant's
   coverage for the affected bucket. No coverage record is an attention score.
5. Report eligible **registered, currently opted-in participants** as the coverage
   denominator. This baseline has no authoritative per-bucket attendance model;
   do not claim this denominator measures attendance. Fully covered participants
   form the missed-context denominator. Both released groups must reach the
   configured group-size threshold. Below-threshold coverage is withheld entirely.
6. Fixed buckets span the final transcript horizon (maximum eight hours). A
   synthetic hotspot needs a configured ratio of qualifying participants and a
   configured duration/confidence of eligible observations. These are heuristics,
   not validated learning metrics. A participant counts once. Dismissed events,
   phone observations and phone-containing bundles are excluded. Delivery findings
   are released only when their full interval is covered by available safe buckets.
7. New `/professor-metrics` requires an ended session and the course professor.
   An explicit approved policy is required outside demo/test. The older
   `/professor/summary` payload reveals small-group counts by its historical
   contract, so it remains only a synthetic compatibility endpoint. It is blocked
   outside demo/test and is not used by AI tools or recommendations.
8. External bounded-text consent is provider-specific and separate from
   aggregation consent. A cache hit still requires current authorization and live
   consent. Cache keys hash the full selected context in addition to actor, session,
   interval, provider, model and prompt/schema versions. This fixes invalidation
   when a changed chunk does not change the session's maximum chunk revision.
9. Recovery job/card ownership is narrower than session membership. The session
   owner cannot read another participant's private card. Recovery notifications
   require an explicit actor audience. Private events without an audience are
   dropped. No audience identity is added to the public event envelope.
10. OpenAI receives request-local source aliases and selected transcript text,
    without names, session IDs, titles, signal categories or phone evidence.
    Structured output is validated again, including exact quote/source checks.
    Exact quotes and valid schemas are necessary checks, not semantic proof of
    grounding. The SDK is optional; live configuration is explicit and never used
    by default tests. No automatic cross-provider fallback.
11. Model tools are read-only and bound to a request's actor/session/interval.
    Arguments cannot select another session, actor or filesystem path. Each call
    reauthorizes; round limits, duplicate-call detection and output limits apply.
    The live recovery route initially exposes transcript retrieval only. The
    registry also implements course context, own recovery history, own selected
    intervals and professor metrics for future explicitly authorized workflows.
12. Local vision runs in a separate Python process, never an HTTP media endpoint.
    The CPU adapter requires an approved manifest with license, source, version,
    digest, dimensions and exact output format. Frames are consumed and cleared
    in success/failure paths; no files, telemetry or network fallback are used.
    This is not a claim of forensic erasure of all native-library allocations.

## Contract authority and review

`shared/contracts/*.schema.json` are reusable review artifacts. Their new models
live in `backend/app/contracts/learning.py`; generation/check tooling verifies
correspondence. FastAPI generates `docs/api/openapi.json`. The generated handoff
at `shared/contracts/generated/learning_types.ts` is outside `frontend/`.

No new WebSocket payload shape is introduced. Existing AsyncAPI events retain
session-relative payloads and the envelope; audience restrictions are internal.
Frontend/backend review remains required before merging public contracts. No
frontend or Electron implementation is included in this work.

## Deferred policy and external verification

The synthetic policy is k=5, 30-second buckets, 60% coverage, 40% hotspot ratio,
10-second qualifying duration and 0.5 confidence. These are test settings only.
The team must approve real policy and evaluate inference risks across reports.
An ONNX artifact, redistribution review, cross-platform benchmarks and detector
accuracy evaluation remain required before claiming a working real detector.
Live OpenAI and Dropbox account checks remain opt-in. No real savings are claimed.
