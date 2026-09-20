# New plan implementation

Status: Local mocked MVP verified; review and live integration gates pending

Owner: Backend team

## Baseline and sources

This work extends backend commit `88d7bbb`, fetched on 2026-09-19. That
commit already mounts sessions, transcript, signals, mocked recovery, professor
summaries and WebSockets. Earlier status documents describing only health routes
refer to `9cbbb85`, not this baseline. The original combined checkout is preserved.

Design inputs are `docs/professor_metrics_dashboard.md` and
`docs/ai_provider_tool_calling_plan.md` at `c882e6f`, and
`docs/architecture/local_object_detection.md` at `d5500e8`.
Contract precedence follows `docs/README.md`; examples in those plans do not
override checked-in schemas. Existing `/api/v1` paths remain supported.

## Dependency decisions

The OpenAI Python SDK supplies the maintained Responses client and error types;
custom HTTP/authentication is unnecessary. OpenCV supplies image resizing and
quality measurements; NumPy supplies bounded arrays; ONNX Runtime supplies CPU
model inference. These are optional runtime extras, never server requirements
for a mocked demonstration. No models are downloaded automatically. Model source,
license, checksum and evaluation approval are required before real inference.
Ruff, Mypy, Pytest and JSON Schema validation are development checks.

## Scope and gates

Implement professor coverage/hotspots, separate delivery events, bounded recovery
and OpenAI adapter, authorized read-only tools, professor recommendations, local
vision worker, and a combined synthetic demonstration. External text consent is
separate from anonymous aggregation. Real reporting requires an explicit policy.
No frontend changes, raw-media upload, automatic provider fallback or real-data
provider tests. Local model benchmarks and live provider verification are recorded
separately from mocked test results.

## Implemented behavior

| Feature | Implementation | Verification boundary |
|---|---|---|
| Professor metrics | Coverage ingestion; unioned observation intervals; fixed buckets; current-consent participant deduplication; hotspot and continuity measures; phone exclusions | Synthetic policy only; no approved real group-size policy |
| Delivery quality | Atomic professor-authorized batches; three derived delivery types; evidence limits; separate report lane | Simulated detector events; no server frame ingestion |
| Recovery cards | Existing pipeline extended with own-event/card/job authorization, bounded context, content-hash cache invalidation and private notifications | In-memory, synchronous jobs; not a durable queue |
| OpenAI | Optional SDK structured output; request-local source aliases; quote checks; sanitized failures; successful-call token usage | SDK-shaped mocks; live synthetic command supplied but not run |
| Read-only AI tools | Request-scoped typed registry; per-call membership checks; interval/output/round limits; loop detection; optional Responses adapter | Mock loop and SDK wire normalization tested; recovery route allowlists transcript tool only |
| Professor recommendations | Synthetic or OpenAI generator over safe hotspots; revision-bound caching and reviewed/dismissed/resolved feedback | Live provider needs external consent; no claim of causal teaching effects |
| Local vision | CPU ONNX adapter; manifest/digest gate; owned-frame lifecycle; presenter/occlusion/blur/contrast heuristics; adaptive sampling; local CLI and benchmark function | Synthetic arrays and fake detections; no approved model artifact or camera/hardware evaluation |
| Recovery export | Own-card resolution; explicit selected folder; confirmation; bounded Markdown; create-only destination port and mock receipt | Existing Dropbox SDK/OAuth work remains separate; no live export verified |
| Integration | Main app composition, body limits, additive API aliases, session end, consent routes, schema/type generation, synthetic flow and CI configuration | Local tests and checks; remote CI results must be checked on the published branches or PRs |

## Worktree and branch map

All new branches share a contract/scaffolding commit above `88d7bbb`, followed
by separate feature commits. They are prepared for publication to origin.
Worktrees are beneath `backend/.feature-worktrees/` in the original checkout.
Do not switch the original dirty checkout or merge it blindly into the new host.

| Worktree | Branch | Role |
|---|---|---|
| `professor-metrics` | `feature/backend-professor-metrics` | Coverage and aggregate metrics |
| `delivery-quality` | `feature/backend-delivery-quality` | Derived delivery ingestion |
| `local-lecture-vision` | `feature/local-lecture-vision` | On-device Python vision |
| `recovery-cards` | `feature/backend-recovery-cards` | Private recovery and cache checks |
| `openai-recovery` | `feature/backend-openai-recovery` | Structured provider adapter |
| `ai-read-tools` | `feature/backend-ai-read-tools` | Bounded model tools |
| `professor-recommendations` | `feature/backend-professor-recommendations` | Safe teaching suggestions and review |
| `recovery-export` | `feature/backend-recovery-export` | Selected derived artifact bridge |
| `recovery-flow` | `feature/backend-recovery-flow` | Full host integration and end-to-end verification |

The feature branches export services/routers for host composition. Their
`FEATURE_<FEATURE_NAME>.md` files state exactly what they own and how to run focused tests.
Each branch also uses its own `backend/tests/feature_<feature_name>/` directory,
so feature tests and review guides have distinct paths when merged.
Their baseline `app.main` still serves the baseline application. The integration
worktree mounts all new feature endpoints. Shared contract/state scaffolding is
identical across branches, under one editor; other feature services are not
copied into each branch. `MetricsReader` and injected fakes avoid service dependencies.

`feature_file_ownership.json` records the exact path split. Shared scaffolding
is one common ancestor commit. Feature commits contain their own implementation,
tests and review guide. The integration branch incorporates feature histories
and adds host wiring and end-to-end checks. Merge feature PRs before the integration
PR so its remaining diff describes host integration. Publishing these branches
does not merge into `backend`, `dev` or `main`.

## Compatibility and privacy fixes in the host

Inspection of the newly fetched baseline found gaps that would undermine the new
features. The integration work also:

- Prevents another student from correcting an event or reading its recovery job.
- Prevents a session owner from reading another student's personal recovery card.
- Makes private recovery notifications actor-scoped and rechecks socket membership.
- Makes signal batch validation atomic and filters eligibility to the submitter.
- Preserves phone-as-supporting-signal rules, with configurable duration thresholds.
- Blocks the historical small-group-count summary outside synthetic demo/test.
- Adds request-body limits and JSON-only mutation payloads.
- Corrects successful live usage labels and retains measured tokens separately from characters.
- Applies formatting/import fixes and corrects pre-existing type annotations so the
  integrated backend passes its lint, format and type checks. Existing behavioral
  tests were retained; WebSocket tests now provide explicit private audiences.

No frontend/Electron/React files were edited. The generated TypeScript declarations
are shared contract artifacts. No keys, private transcripts or real media were
used. Synthetic arrays are generated in memory. New consent and coverage state is
process-local; full retention/deletion scheduling remains host work.

## Checks and practical limits

The original baseline passed 56 tests in the new virtual environment before edits.
The integrated suite and branch-specific results are recorded in the final review
below. All default checks use fakes; no API credits were consumed by verification.
The isolated branches were tested using the same clean tool environment with
branch-local import roots. Install extras in a local venv when reviewing a branch
on another machine; no globally installed packages are required.

Remaining external gates:

1. Frontend/backend public-contract review and team approval of the real reporting policy.
2. An approved redistributable model export plus accuracy, CPU/memory and OS evaluation.
3. Explicit synthetic live OpenAI verification and a priced benchmark before savings claims.
4. Live Dropbox host adapter wiring, OAuth/token storage and account verification.
5. Durable storage/jobs, full lifecycle deletion and a deployment-grade session enrollment flow.

Learning outcomes and helpfulness are marked `not_collected`, not represented by
fake rates. Meta provider availability is not assumed; the code does not fabricate
an unverified Meta adapter or silently move data between providers. The local
vision code is a tested worker and adapter implementation, not a validated shipped
classroom detector. Model output grounding still needs semantic quality evaluation.

## Final local review checks

- Integrated host: 109 tests (56 retained baseline tests and 53 new checks).
- Isolated feature branches: 57 tests each (56 baseline + focused feature check);
  local vision: 62 tests (56 baseline + six synthetic vision checks).
- Integrated Ruff lint and format checks, Mypy across 68 application source files,
  shared schema/type drift checks, OpenAPI drift check, editable package build,
  `pip check`, and the synthetic demo all passed locally.
- The only observed suite warning is a third-party Starlette/AnyIO deprecation.
- No TypeScript compiler is installed in this workspace. Generated handoff types
  are checked for deterministic schema correspondence; frontend compilation/review
  remains a handoff gate. No frontend files were changed to obtain a compiler.
- No live provider, real camera/model run, Docker database gate or remote CI run is
  claimed by these checks. Successful local mocks are not live integration proof.

The isolated worktrees intentionally retain their baseline host files except
feature-owned changes and installation configuration. Their focused lint/type
checks cover the new feature and shared interfaces; full host formatting/type
cleanup is owned and verified in the integration branch. Existing tests are not
removed or skipped to make the new features pass.
