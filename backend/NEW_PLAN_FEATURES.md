# New learning features: implementation and review guide

Status: Implemented; feature branches prepared for review

Owner: Backend team

Last updated: 2026-09-19

## What changed

The remote backend advanced to `88d7bbb` while this work began. Its already-wired
mocked recovery, sessions and JWT boundaries are the host for these additions.
The old combined checkout and three previously published feature branches are
preserved. Do not assume their models can be dropped into the newer host unchanged.

Read [the contract decision](../docs/decisions/adr_0002_learning_plan_contracts.md),
[API handoff](../docs/api/learning_plan_contracts.md), and
[implementation report](../docs/implementation/new_plan_execution.md).

## Run the integrated synthetic MVP

Run from the `feature/backend-recovery-flow` worktree root:

```sh
python3 -m venv backend/venv
backend/venv/bin/python -m pip install -e './backend[dev,ai,vision]'
backend/venv/bin/python backend/scripts/demo_new_plan.py
APP_ENV=demo PROVIDER_MODE=mock backend/venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The demo script uses real in-process routing and verified synthetic JWTs. It
produces a sourced mock recovery card, demonstrates a cache hit and bounded tool
loop, exports derived Markdown to a mock selected folder, reports a delivery
finding, generates a teaching suggestion, and verifies suppression after consent
withdrawal. No webcam, model download, provider call or external write occurs.

## Live text generation

Install the optional `ai` extra. Configure `OPENAI_API_KEY` privately in your shell
or secret store; never put it in a request body or commit it. Set `OPENAI_MODEL`
to a model your project can access. The implementation does not guess model access
or pricing. With `PROVIDER_MODE=live`, setup checks for these variables, constructs
the maintained SDK client with a 20-second timeout and one SDK retry, and still
requires each actor's `/external-text-consent` before processing selected text.

An explicit synthetic verification command is available:

```sh
backend/venv/bin/python backend/scripts/check_openai_synthetic.py --live
```

This command consumes credits and is not run by tests or CI. It prints provider
usage metadata only. Normal live recovery stores measured input/output tokens for
successful generations. Cache hits avoid generation; there is no priced baseline
or measured savings benchmark yet. Failed requests may still incur provider usage
not captured in the success ledger; reconcile with provider billing before making
cost claims. Recommendation/tool usage is not part of the recovery-job cost ledger.

Implementation references: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
and [function calling](https://developers.openai.com/api/docs/guides/function-calling).
The OpenAI Docs skill was used to verify this boundary. SDK output stays inside
`app/integrations/openai/`; the domain consumes typed models.

## Local vision

Install the optional `vision` extra only on the device that owns the camera.
`app.local_ml.worker` requires `--consent-local-camera`, a local model path,
a manifest, and the current session-relative `--clock-offset-ms`.

The manifest requires source, license, version, SHA-256, an explicit approval flag,
input size <=320 and the exact `xyxy_score_class_normalized` output contract.
The adapter accepts NCHW RGB float input and Nx6 normalized boxes/score/class.
It does not guess arbitrary YOLO layouts. Use a reviewed model export matching
this contract; no approved artifact is shipped or automatically downloaded.

The worker implements presenter framing, optional manually supplied board-region
occlusion and blur/contrast heuristics. Low-power mode runs framing only. It emits
completed sustained intervals; camera loss discards incomplete candidates. It
lowers sample rate under load, processes one frame at a time, and clears owned
arrays on exit. Blur/contrast are possible legibility evidence, not OCR or a
judgment of handwriting quality. The CLI accepts normalized `--presenter-region X1 Y1 X2 Y2` and
`--board-region X1 Y1 X2 Y2` values. Its default `--profile auto` runs a short
synthetic inference benchmark before opening the camera; profiles can also be
selected explicitly. This startup measurement is not a lecture-length evaluation.

No real-camera evaluation, redistribution approval, packaged desktop integration,
Windows/Linux benchmark or lecture-length battery measurement is claimed.
See [ONNX Runtime](https://onnxruntime.ai/docs/api/python/api_summary.html) and
[OpenCV capture](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html)
for the provider APIs used.

## Feature ownership

Each feature has its own branch/worktree. Shared contract/state files are identical
interface scaffolding, edited by the integration owner. Feature branches export
services and routers; the integration branch owns `app/main.py`, full app wiring,
the combined OpenAPI snapshot, runtime compatibility fixes and end-to-end tests.
Review the branch-specific `FEATURE_<FEATURE_NAME>.md` for its paths and dependency gates.
The old baseline app is not advertised as mounting new feature routers on every
isolated branch. Complete routing is verified on the integration worktree.

## Verification

```sh
backend/venv/bin/python -m pytest backend/tests -q
backend/venv/bin/python -m ruff check backend/app backend/tests backend/scripts
backend/venv/bin/python -m ruff format --check backend/app backend/tests backend/scripts
backend/venv/bin/python -m mypy --follow-imports=silent --ignore-missing-imports backend/app
backend/venv/bin/python backend/scripts/generate_learning_contracts.py --check
backend/venv/bin/python backend/scripts/generate_openapi_contract.py --check
```

Default tests use synthetic text, arrays, fake SDK responses and a fake export
destination. Fresh editable installation is checked in an isolated environment.
Public-contract review and provider/policy/model gates are separate from tests.
