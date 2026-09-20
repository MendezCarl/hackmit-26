# Feature 7: demo, health, metrics and tests

Status: Implemented and reviewed; publication authorized; no Feature 7 merge

Owner: Backend integration team

Last updated: 2026-09-19

## Branch and review boundary

`feature/backend-demo-health-metrics` starts at `9d9585f` on
`feature/backend-recovery-flow`. Its worktree is
`backend/.feature-worktrees/demo-health-metrics` under the original checkout.
Only this worktree is edited. Creating it neither merges nor modifies the eight
feature branches, their integration branch, backend, dev or main.

Review its diff against `feature/backend-recovery-flow`, so inherited features
do not obscure Feature 7. A future PR should target that integration branch while
it remains the dependency, or backend after the integration work has landed.
The user authorized committing and pushing this existing branch after review.
No pull request or merge is included in that authorization.

## Existing contracts retained

The foundation is [ADR 0002](../decisions/adr_0002_learning_plan_contracts.md),
[the unified contracts](../api/unified_api_contracts.md), and the existing typed
recovery/session/metrics models. Existing response fields are retained. Additions
use snake_case, integer lecture-relative milliseconds and standard error codes.
No new WebSocket message is introduced.

- `GET /health`: unchanged `200 {"status":"ok"}`, no authentication. Liveness
  only: no provider calls, database probes or secret/configuration output.
- `POST /api/v1/demo/runs`: no JWT because it operates only on isolated synthetic
  fixtures. Requires `APP_ENV=demo`; test/development/production receive 404
  `demo_unavailable`. Empty body, JSON null or `{}` are accepted. Unexpected
  media, identity, transcript or provider fields receive 422 `validation_failed`.
  The existing 1 MiB JSON boundary returns 413/415 for oversized/non-JSON bodies.
- Successful runs return 201 with `Cache-Control: no-store` and the existing
  `DemoRunResult` fields plus `professor_metrics`, `professor_metrics_suppressed`,
  `usage_records` and `token_cost_comparison`.
- Sessions in this response now have `status=ended`, because the current metrics
  service requires post-lecture reporting. These ephemeral demo IDs are returned
  for explanation only and are not registered in the host session API.
- Failed generation returns a sanitized 502 `provider_failure`, not an incomplete
  success response. A failed cache assertion returns standard 500 `internal_error`.

Machine-readable contracts:

- [Request JSON Schema](../../shared/contracts/demo_run_request.schema.json)
- [Response JSON Schema](../../shared/contracts/demo_run_result.schema.json)
- [Generated TypeScript handoff](../../shared/contracts/generated/demo_types.ts)
- [OpenAPI snapshot](../api/openapi.json)

Run `backend/venv/bin/python backend/scripts/generate_demo_contracts.py` and
`backend/venv/bin/python backend/scripts/generate_openapi_contract.py` after model
changes. Their `--check` modes verify drift. Pytest validates the actual response
against JSON Schema; generated declarations do not replace runtime validation.
Shared/API contract changes still need frontend and backend review before merge.

## What the demo actually does

1. Construct fresh in-memory storage, consent state, timeline, private recovery,
   usage ledger, professor services and a deterministic generator for one request.
   This construction never reads host session state, provider clients or credentials.
2. Create a synthetic lecture with 32 distinct transcript excerpts spanning a
   thirty-minute clock. These are compressed teaching excerpts, not a recording
   or a claim about natural speech rates.
3. Register five synthetic, consenting students. Ingest possible missed-content
   intervals at 931200–978700 ms and explicit observation coverage.
4. Retrieve four final transcript chunks around the interval and generate a mock
   card using the real recovery service, source validation and authorization.
5. Repeat the identical authorized request. The same card is reused and the ledger
   records a cache hit with zero additional generation characters.
6. End the session and produce coverage-aware anonymous metrics. Create a second,
   one-participant synthetic session to demonstrate suppression.
7. Compare the full final transcript text with the card's selected source text.
   Return the result and release the request-local runtime. Concurrent requests
   have separate sessions, providers, caches and subscribers.

The historical `professor_summary` fields remain for compatibility and are
synthetic-only. The judge script uses the current `professor_metrics` reports,
which suppress per-bucket counts, ratios and sources below the threshold. The
synthetic minimum of five is not approval for real-world reporting.

## Token and cost accounting

The current fixture contains 4575 Unicode characters; the selected text contains
546. The explicit heuristic `ceil(unicode_characters / 4)` yields 1144 and 137
estimated tokens. It is not a model tokenizer and excludes prompts, serialized
metadata, separators and generated output. The estimated input reduction is
about 88%; it is not a measured reduction in provider billing.

The illustrative input rate is exactly $1 per million estimated tokens. It is
an arbitrary demonstration assumption, not an OpenAI price. Illustrated inputs
cost $0.001144 and $0.000137 under that assumption. Measured input/output tokens
and measured dollar savings remain null. External API calls are zero. Mock
invocation count and cache-hit count come from the run's synthetic usage ledger.

No Token Company transport or live baseline experiment is claimed. Genuine
provider savings need opt-in synthetic full-context and selected-context calls,
actual usage, explicit current pricing and a quality comparison.

## Files and responsibilities

- `backend/app/demo/`: fixture, isolated composition, scenario orchestration,
  optional empty request model, response additions and cost illustration.
- `backend/app/main.py`: removes the old demo runner bound to host state. Health
  behavior and other feature composition remain unchanged.
- `backend/tests/e2e/`: API isolation, media rejection, exact fixture grounding,
  usage/cache accounting, threshold boundaries, failure sanitization and schemas.
  Existing tests now expect a completed session and 32 transcript chunks.
- `backend/scripts/demo_feature_seven.py`: compact judge display from the actual
  endpoint, in process or against a running server with `--url`.
- `backend/scripts/generate_demo_contracts.py`, the shared TypeScript generator
  (preserves numeric usage dictionaries as `Record<string, number>`), `shared/contracts/`,
  `docs/api/openapi.json`: synchronized contract artifacts and handoff types.
- `.github/workflows/backend_contracts.yml`: trigger this feature branch on push,
  include shared-contract path changes, and verify the demo contract and script.
- Root `README.md`: exact venv/server/test commands and the 90-second script.

No dependency manifest or frontend/Electron/React code is changed.

## Validation and remaining limits

Focused tests cover demo mode gates; media and identity rejection; concurrent
isolation; a live-configured host whose generator must never be used; blocked
network access; exact source times and fixture facts; one mock generation plus
one cache hit; heuristic arithmetic; rejection of live usage in the synthetic
comparison; k-1/k/k+1 aggregation; sanitized failures; and contract drift.

The inherited suite also covers cross-user authorization, raw-media limits,
phone-signal exclusion, consent, provider errors and successful measured-usage
accounting. Fixture grounding tests are not a human study or a semantic-quality
benchmark for live models. No live provider/camera call is required or performed.
Production persistence, approved aggregation policy and live provider verification
remain the integration project's separately documented gates.


## Local verification results

- Full backend suite: **148 passed** (122 inherited + 26 Feature 7 cases).
- Focused Feature 7 and existing contract-flow checks after the generator update:
  **34 passed**. Focused runs explicitly set their script import root and do not
  depend on test collection order.
- Ruff lint and formatting, Mypy (70 application files), dependency consistency,
  OpenAPI, learning and demo contract drift checks passed.
- Actual local HTTP smoke: Uvicorn returned 200 from `/health` and 201 from the
  demo endpoint; the documented compact HTTP command succeeded. The temporary
  server was stopped after verification.
- All provider usage remained mocked. The only suite warning was the inherited
  Starlette/AnyIO deprecation. Generated TypeScript schemas/types were checked for
  deterministic correspondence; a frontend TypeScript build was not run.
- Remote CI results must be checked for the published commit; local checks do not
  establish a GitHub CI result. No merges were made for Feature 7.
