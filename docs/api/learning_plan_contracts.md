# New learning feature API contracts

Status: Implemented locally; review pending

Owner: Backend team

Last updated: 2026-09-20

Read [ADR 0002](../decisions/adr_0002_learning_plan_contracts.md) for the mapping
from the two planning branches to the implemented wire contracts. The new
backend foundation at `88d7bbb` is the host, not the old standalone feature app.

## Contract map

Every route below begins `/api/v1/sessions/{session_id}`. Authentication is a
verified bearer JWT. Request-body identities, unknown properties and media fields
are rejected. New mutation bodies are capped at 1 MiB before JSON parsing.

| Method and suffix | Request / response | Authorization and behavior |
|---|---|---|
| `POST /coverage/batch` | `CoverageBatch` / `BatchReceipt` | Registered student with current aggregation consent; atomic batches and exact retries |
| `POST /delivery-events/batch` | `DeliveryBatch` / `BatchReceipt` | Course professor; no student camera observations; closed intervals only |
| `GET /professor-metrics` | none / `ProfessorMetrics` | Course professor, ended session, explicit policy; current consent recomputed |
| `PUT /aggregation-consent` | `AggregationConsent` / same | Own student participation; withdrawal erases own coverage |
| `PUT /external-text-consent` | `ExternalTextConsent` / same | Own session membership; provider-specific, revocable permission |
| `POST /professor-recommendations` | none / `RecommendationReport` | On request only. Safe report first; lecture excerpts analyzed locally in mock mode, in live mode only with the professor's own external-text consent; otherwise `intervals_only` |
| `PUT /professor-recommendations/reviews` | `RecommendationReview` / same | Current generated report revision and valid suggestion index required |
| `POST /recovery/tool-runs` | `LectureInterval` / `ToolRecoveryResult` | Own bounded recovery; read-only tool loop, no arbitrary files or writes |
| `PUT /artifacts/folder` | `FolderSelection` / same | Own explicitly selected, authorized destination |
| `POST /artifacts/exports` | `ArtifactExport` / `ExportReceipt` | Own existing card and confirmation; create-only derived Markdown |
| `POST /end` | none / `LectureSession` | Session owner; idempotent lifecycle finalization |

Recovery/transcript aliases preserve both the baseline and earlier unified paths.
Inspect `/docs` in the integration worktree for complete required fields, types,
errors and examples. Its `docs/api/openapi.json` is the complete host snapshot.
On isolated feature branches, that filename describes the baseline host; the new
routers are exported for integration rather than advertised as already mounted. Do not substitute the old standalone
feature branch's batch shapes for these host contracts.

## Shared payloads

- [Coverage](../../shared/contracts/coverage_batch.schema.json): records have
  `coverage_id`, `start_ms`, `end_ms`, `is_available`; no identity supplied by client.
- [Delivery](../../shared/contracts/delivery_batch.schema.json): `signal_type` is
  one of presenter absence, board/screen occlusion or possible low slide legibility.
  Evidence contains only sample counts and a profile. Batches have at most 50 events.
- [Professor metrics](../../shared/contracts/professor_metrics.schema.json): fixed
  buckets have `available`, `suppressed` or `insufficient_evidence` states. Missing
  values are null, not fabricated zeroes. Continuity uses available buckets only.
- [Recovery draft](../../shared/contracts/recovery_draft.schema.json): each fact
  has a source reference and exact evidence quote. Server owns timestamps/card IDs.
- [Recommendations](../../shared/contracts/recommendation_report.schema.json):
  suggestions reference released intervals and a content-derived report revision.
  `evidence_scope` is `lecture_transcript` when bounded excerpts (final transcript
  chunks overlapping each hotspot, at most 2 000 characters per interval, no speaker
  labels or participant data) were analyzed; then each suggestion may carry `topic`,
  `medium` (`explanation`, `pace`, `example`, `terminology`) and up to three
  `evidence` facts whose `evidence_quote` is verified verbatim against the cited
  `chunk_id`. Suggestions whose evidence fails verification, or whose wording infers
  attention, emotion, comprehension, disability or causation, are dropped. With
  `intervals_only`, `evidence_note` explains why (consent not granted, or no
  transcript overlaps the hotspots) and no lecture text leaves the service.
- [Type handoff](../../shared/contracts/generated/learning_types.ts): generated
  TypeScript declarations, with runtime range/privacy validation still on the backend.

## Errors and persistence

Use the existing `ErrorResponse`: `error.code`, `error.message`, optional
`error.details`. Stable codes include `forbidden`, `duplicate`, `validation_failed`,
`payload_too_large` and provider failure codes. Provider exception text is not
returned. Reads containing personal or aggregate content use `Cache-Control: no-store`.

New state is bounded, process-local and injected per application. Restart clears
coverage, consent, delivery records and recommendation reviews. Existing jobs are
still executed synchronously behind their job API; this implementation does not
claim a durable Redis queue. Deploy only as a single-process MVP until persistence,
shared authorization state and retention orchestration are integrated.

## Regeneration and review

```sh
backend/venv/bin/python backend/scripts/generate_learning_contracts.py
backend/venv/bin/python backend/scripts/generate_learning_contracts.py --check
backend/venv/bin/python backend/scripts/generate_openapi_contract.py
backend/venv/bin/python backend/scripts/generate_openapi_contract.py --check
```

Run the schema drift and behavior tests together. Contract reviews must consider
both the new schemas and the existing host aliases. Mock exports are not live
Dropbox writes. A valid AI citation is not proof that its paraphrase is correct.
