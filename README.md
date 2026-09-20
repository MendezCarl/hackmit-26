# Bloom

Bloom is a privacy-first Electron desktop app with a Python FastAPI backend.

## Branding

Bloom's platform icons live in `frontend/build/`. The source SVG used by the renderer lives in `frontend/src/assets/`. The Electron package metadata defines the product name, application ID, platform icon paths, and packaged runtime icon resources.

## Vision Processing Roadmap

The MVP runs the vision model locally so raw camera frames remain on the device and computers without a dedicated GPU can use CPU inference.

In the future, we plan to offer an optional cloud-hosted vision service so computers that cannot meet the local performance target can still use visual lecture-quality features. The cloud implementation should run the same provider-neutral model container on an approved cloud platform rather than couple the product to one vendor.

Cloud vision will require explicit consent because camera frames must leave the device. It must never activate as a silent fallback. The future implementation must define encryption, authentication, region, retention, deletion, and no-image-logging requirements before release. Professor dashboards and AI feedback should continue receiving only approved derived events and anonymous aggregates.

See the [local object detection architecture](docs/architecture/local_object_detection.md) for the hardware targets, privacy boundary, cloud portability plan, and unresolved team decisions.

## Branch Workflow

- `main`: protected release branch; changes should land through pull requests.
- `dev`: integration branch for ongoing work.
- `frontend`: frontend feature branch.
- `backend`: backend feature branch.

## Frontend

```sh
cd backend
source .venv/bin/activate
fastapi dev app/main.py
```

In a second terminal:

```sh
cd frontend
npm install
npm run dev
```

The Electron renderer expects the backend at `http://127.0.0.1:8000` and
falls back to visibly labeled `Demo mode · synthetic data` fixtures when it is
offline. Live OpenAI recovery requires `PROVIDER_MODE=live` and
`OPENAI_API_KEY`; normal development uses synthetic behavior.

The current prototype follows the documented process and feature boundaries without adding a UI framework dependency:

```text
frontend/
├── index.html
├── src/
│   ├── main/                  # Electron main process
│   ├── preload/               # Safe renderer bridge
│   ├── assets/                # Bloom product assets
│   └── renderer/
│       ├── app/               # Routing and page composition
│       ├── components/        # Reusable presentation components
│       ├── features/          # Pages grouped by product feature
│       ├── fixtures/          # Synthetic prototype content
│       └── types/             # Frontend boundary types
└── tests/
    ├── unit/
    └── component/
```

See the [frontend wireframe implementation](docs/product/frontend_wireframe_implementation.md) for the implemented routes and component inventory, and the [repository structure](docs/architecture/repository_structure_and_branch_workflow.md) for the target React/Vite architecture.

## Backend

```sh
cd backend
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
fastapi dev app/main.py
```

FastAPI exposes interactive API docs at `http://127.0.0.1:8000/docs`.

## Electron With Python

Yes, an Electron app can use a Python backend. The common setup is to run Electron for the desktop UI and have it call a local or remote Python API over HTTP. This skeleton keeps those pieces separate so the backend can later be run manually, spawned by Electron, or deployed remotely.

## Feature 7: backend judge demo

This feature lives on `feature/backend-demo-health-metrics`, based on the existing
`feature/backend-recovery-flow` integration commit `9d9585f`. It does not change
other branches. From the original local checkout, its isolated folder is
`backend/.feature-worktrees/demo-health-metrics`; run the commands below from
that worktree's root. On another machine, check out the feature branch and run
from the repository root.

### Install and run

Python 3.14 is the CI version. All dependencies install inside this branch's venv:

```sh
python3.14 -m venv backend/venv
backend/venv/bin/python -m pip install -e './backend[dev,ai,vision]'
backend/venv/bin/python backend/scripts/demo_feature_seven.py
```

The final command calls the actual FastAPI demo endpoint in process and prints a
compact result. No API key, Docker service, camera, model artifact or live account
is required. The AI and vision extras support the inherited full test suite;
the judge demo itself needs only the backend and development dependencies.

To show the HTTP API, start a local server:

```sh
APP_ENV=demo PROVIDER_MODE=mock backend/venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal, from the same worktree root:

```sh
curl --fail --silent http://127.0.0.1:8000/health
backend/venv/bin/python backend/scripts/demo_feature_seven.py --url http://127.0.0.1:8000
```

The full response is also available directly:

```sh
curl --fail --silent -X POST http://127.0.0.1:8000/api/v1/demo/runs -H 'Content-Type: application/json' -d '{}' | backend/venv/bin/python -m json.tool
```

Swagger: <http://127.0.0.1:8000/docs>. `GET /health` reports process liveness only;
it does not certify Mongo, Redis or external providers. `POST /api/v1/demo/runs`
requires `APP_ENV=demo`, accepts only an empty optional JSON body, and returns
synthetic artifacts. Each run has fresh state; returned IDs cannot be used to
retrieve demo artifacts from ordinary session routes afterward.

### 90-second judge script

Prepare the server and second terminal before starting the timer.

| Time | Show and say |
|---|---|
| 0–10 seconds | Run `/health`. “Lumina helps a student recover lecture context without labeling them inattentive. This is a synthetic backend demonstration.” |
| 10–25 seconds | Run the compact demo command with `--url`. Point to `missed_interval_ms`: 931200–978700, about 15:31–16:19. “We receive coarse observations and timestamped text; raw camera and audio stay on the device.” |
| 25–45 seconds | Read the query/key and multi-head facts, then point to `source_timestamps`. “The missed moment selects four chunks from a longer lecture. The card links its recap to those chunks. Today's response is a deterministic mock, not a live AI call.” |
| 45–60 seconds | Point to `professor_hotspots` and `small_group_status`. “Five synthetic, consenting participants permit aggregate reporting. A small group is suppressed. No student identities or phone observations appear in the professor report.” |
| 60–80 seconds | Point to `token_cost_comparison` and `cache_status`. “This fixture shrinks the estimated transcript input from 1144 to 137 tokens. These are character-based estimates; dollars use an illustrative rate, not provider pricing. A repeat request reuses the card, avoiding a second generation.” |
| 80–90 seconds | “This demonstrates recovery, privacy boundaries and reuse. Live provider savings and human-rated recovery quality still need separate evaluation. No API credits were used here.” |

### Verify the branch

```sh
backend/venv/bin/python -m pytest backend/tests -q
backend/venv/bin/python -m ruff check backend/app backend/tests backend/scripts
backend/venv/bin/python -m ruff format --check backend/app backend/tests backend/scripts
backend/venv/bin/python -m mypy --follow-imports=silent --ignore-missing-imports backend/app
backend/venv/bin/python backend/scripts/generate_demo_contracts.py --check
backend/venv/bin/python backend/scripts/generate_learning_contracts.py --check
backend/venv/bin/python backend/scripts/generate_openapi_contract.py --check
backend/venv/bin/python -m pip check
```

CI on this branch is configured for pushes to `feature/backend-demo-health-metrics`
and relevant pull requests. A local pass is not a GitHub CI result.
See the [Feature 7 handoff](docs/implementation/feature_seven.md) for the contract,
file ownership, test coverage, limitations and review sequence.
