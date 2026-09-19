# Repository Structure and Branch Workflow

## Repository approach

Use a single monorepo. The Electron application, FastAPI backend, local ML pipeline, shared data contracts, documentation, and infrastructure should live in the same repository so the frontend and backend teams can integrate against one versioned API contract.

The structure below is intentionally modular without turning every component into a separate microservice. That keeps it manageable during a hackathon while leaving clear boundaries for future growth.

## Proposed repository structure

```text
lecture-recovery-assistant/
├── AGENTS.md
├── CLAUDE.md
├── .agents.md                            # Compatibility pointer to AGENTS.md
├── .claude.md                            # Compatibility pointer to CLAUDE.md
├── README.md
├── CONTRIBUTING.md
├── LICENSE
├── .env.example
├── .gitignore
├── docker-compose.yml
│
├── frontend/                              # Owned primarily by frontend branch/team
│   ├── package.json
│   ├── package-lock.json
│   ├── electron-builder.yml
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   │
│   ├── src/
│   │   ├── main/                         # Electron main process
│   │   │   ├── index.ts
│   │   │   ├── windows.ts
│   │   │   ├── permissions.ts            # Camera, microphone, and screen permissions
│   │   │   ├── systemAudio.ts            # Required system-audio capture
│   │   │   ├── localMedia.ts             # Private on-device media lifecycle
│   │   │   └── zoom.ts                   # Meeting SDK lifecycle
│   │   │
│   │   ├── preload/                      # Safe Electron IPC bridge
│   │   │   ├── index.ts
│   │   │   └── api.ts
│   │   │
│   │   ├── renderer/                     # React application
│   │   │   ├── app/
│   │   │   │   ├── App.tsx
│   │   │   │   ├── router.tsx
│   │   │   │   └── providers.tsx
│   │   │   ├── features/
│   │   │   │   ├── lecture-session/      # Start/end session and live status
│   │   │   │   ├── recovery-cards/       # Student missed-content explanations
│   │   │   │   ├── professor-summary/    # Post-lecture aggregate metrics
│   │   │   │   ├── timeline/             # Transcript and signal visualization
│   │   │   │   ├── zoom/                 # Embedded Zoom experience
│   │   │   │   ├── dropbox/              # Course-folder selection and sync
│   │   │   │   └── privacy-settings/     # Consent, retention, and deletion controls
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── services/
│   │   │   │   ├── apiClient.ts
│   │   │   │   ├── websocketClient.ts
│   │   │   │   └── localSignalClient.ts
│   │   │   ├── store/
│   │   │   ├── types/
│   │   │   │   └── generated/             # Generated from shared contracts
│   │   │   └── utils/
│   │   │
│   │   └── shared/                        # Code shared by Electron processes
│   │       ├── ipcChannels.ts
│   │       ├── sessionClock.ts
│   │       └── constants.ts
│   │
│   └── tests/
│       ├── unit/
│       ├── component/
│       └── e2e/
│
├── backend/                               # Owned primarily by backend branch/team
│   ├── pyproject.toml
│   ├── requirements.lock
│   ├── Dockerfile
│   │
│   ├── app/
│   │   ├── main.py                        # FastAPI entry point
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   │
│   │   ├── api/
│   │   │   ├── router.py
│   │   │   └── routes/
│   │   │       ├── health.py
│   │   │       ├── sessions.py
│   │   │       ├── events.py
│   │   │       ├── recovery.py
│   │   │       ├── professor_summary.py
│   │   │       ├── zoom.py
│   │   │       └── dropbox.py
│   │   │
│   │   ├── schemas/                       # Pydantic request/response models
│   │   │   ├── events.py
│   │   │   ├── transcripts.py
│   │   │   ├── recovery.py
│   │   │   └── professor_summary.py
│   │   │
│   │   ├── services/
│   │   │   ├── session_service.py
│   │   │   ├── timeline_service.py
│   │   │   ├── recovery_service.py
│   │   │   ├── aggregation_service.py
│   │   │   ├── privacy_service.py
│   │   │   └── token_metrics_service.py
│   │   │
│   │   ├── ml/
│   │   │   ├── signals/
│   │   │   │   ├── detector.py
│   │   │   │   ├── rules.py              # Owned by ML/backend team
│   │   │   │   ├── thresholds.py         # Owned by ML/backend team
│   │   │   │   └── smoothing.py
│   │   │   ├── vision/
│   │   │   │   ├── mediapipe_pipeline.py
│   │   │   │   ├── opencv_pipeline.py
│   │   │   │   └── object_detection.py
│   │   │   ├── transcription/
│   │   │   │   ├── local_transcriber.py
│   │   │   │   └── transcript_padding.py # Owned by ML/backend team
│   │   │   └── evaluation/
│   │   │       ├── signal_metrics.py
│   │   │       └── recovery_metrics.py
│   │   │
│   │   ├── integrations/
│   │   │   ├── openai/
│   │   │   │   ├── client.py
│   │   │   │   ├── prompts.py
│   │   │   │   └── structured_output.py
│   │   │   ├── zoom/
│   │   │   │   ├── rtms_receiver.py
│   │   │   │   ├── webhooks.py
│   │   │   │   ├── timeline_mapper.py
│   │   │   │   └── auth.py
│   │   │   ├── dropbox/
│   │   │   │   ├── client.py
│   │   │   │   ├── ingestion.py
│   │   │   │   └── export.py
│   │   │   └── meta/
│   │   │       └── transcription.py
│   │   │
│   │   ├── repositories/
│   │   │   ├── sessions.py
│   │   │   ├── events.py
│   │   │   ├── transcripts.py
│   │   │   └── recovery_cards.py
│   │   │
│   │   ├── workers/
│   │   │   ├── queue.py
│   │   │   ├── transcription_jobs.py
│   │   │   ├── recovery_jobs.py
│   │   │   └── aggregation_jobs.py
│   │   │
│   │   └── realtime/
│   │       ├── websocket_manager.py
│   │       └── events.py
│   │
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/
│
├── shared/                                # Requires frontend + backend review
│   ├── contracts/
│   │   ├── event.schema.json
│   │   ├── transcript-chunk.schema.json
│   │   ├── recovery-card.schema.json
│   │   └── professor-summary.schema.json
│   ├── examples/
│   │   ├── event.example.json
│   │   ├── recovery-card.example.json
│   │   └── professor-summary.example.json
│   └── README.md
│
├── docs/                                  # Shared ownership
│   ├── README.md                          # Agent/developer context index
│   ├── product/
│   │   ├── student-user-story.md
│   │   ├── professor-user-story.md
│   │   └── demo-script.md
│   ├── architecture/
│   │   ├── overview.md
│   │   ├── timestamp-model.md
│   │   ├── local-media-boundary.md
│   │   └── zoom-integration.md
│   ├── api/
│   │   ├── unified_api_contracts.md       # Human-readable REST/WebSocket catalog
│   │   ├── openapi.yaml                   # Generated/checked REST contract
│   │   └── asyncapi.yaml                  # WebSocket/event contract
│   ├── privacy/
│   │   ├── consent.md
│   │   ├── retention-and-deletion.md
│   │   └── professor-aggregation.md
│   ├── evaluation/
│   │   ├── signal-evaluation.md
│   │   ├── recovery-evaluation.md
│   │   └── token-cost-baseline.md
│   ├── decisions/
│   │   ├── README.md
│   │   └── adr_0001_contract_first_api.md
│   └── prompts/
│       ├── frontend-task-template.md
│       ├── backend-task-template.md
│       └── integration-task-template.md
│
├── infra/
│   ├── docker/
│   ├── mongodb/
│   ├── redis/
│   └── elasticsearch/                     # Optional for MVP
│
├── scripts/
│   ├── bootstrap.sh
│   ├── dev.sh
│   ├── test.sh
│   ├── generate-types.sh
│   └── seed-demo-data.sh
│
├── data/
│   ├── README.md
│   ├── demo/                              # Synthetic, non-sensitive demo inputs
│   └── local/                             # Gitignored local recordings/media
│
├── tests/
│   ├── contracts/
│   ├── integration/
│   └── e2e/
│
└── .github/
    ├── CODEOWNERS
    ├── pull_request_template.md
    └── workflows/
        ├── frontend-ci.yml
        ├── backend-ci.yml
        ├── contract-ci.yml
        └── integration-ci.yml
```

## Important simplification for the hackathon

Create the directories above, but do not build every module immediately. The first vertical slice only needs:

```text
frontend/src/main/systemAudio.ts
frontend/src/main/localMedia.ts
frontend/src/renderer/features/lecture-session/
frontend/src/renderer/features/recovery-cards/
frontend/src/renderer/features/professor-summary/
frontend/src/renderer/features/zoom/

backend/app/api/routes/sessions.py
backend/app/api/routes/events.py
backend/app/api/routes/recovery.py
backend/app/api/routes/professor_summary.py
backend/app/ml/signals/
backend/app/ml/transcription/
backend/app/integrations/openai/
backend/app/integrations/zoom/
backend/app/services/timeline_service.py
backend/app/services/aggregation_service.py

shared/contracts/event.schema.json
shared/contracts/recovery-card.schema.json
shared/contracts/professor-summary.schema.json
```

Build one complete path through those files before adding Elasticsearch, YOLO, V-JEPA, Dropbox export, or sponsor-specific dashboards.

## Branch structure

Keep the current four long-lived branches:

| Branch | Purpose | Direct pushes |
|---|---|---|
| `main` | Stable, demo-ready releases | No |
| `dev` | Integrated frontend/backend build | No |
| `frontend` | Frontend team's integration branch | Prefer pull requests from frontend feature branches |
| `backend` | Backend/ML team's integration branch | Prefer pull requests from backend feature branches |

### Merge direction

```text
frontend feature branches ──> frontend ──┐
                                         ├──> dev ──> main
backend feature branches  ──> backend ───┘
```

Nothing should merge directly from `frontend` or `backend` into `main`. All integration must pass through `dev`.

### Feature-branch naming

Branch from the appropriate team branch:

```text
feature/frontend-recovery-card
feature/frontend-professor-dashboard
feature/frontend-zoom-shell

feature/backend-session-api
feature/backend-rtms-receiver
feature/backend-signal-thresholds
feature/backend-openai-recovery

fix/frontend-audio-permissions
fix/backend-timestamp-alignment

docs/privacy-boundary
chore/contract-generation
```

Suggested flow:

1. Frontend work branches from `frontend` and returns to `frontend` through a pull request.
2. Backend/ML work branches from `backend` and returns to `backend` through a pull request.
3. `frontend` and `backend` each open pull requests into `dev` when a vertical slice is ready for integration.
4. Integration tests run on `dev`.
5. `dev` opens a pull request into `main` only when the build is demo-ready.
6. After an integration merge, merge `dev` back into both `frontend` and `backend` so the long-lived branches do not drift apart.

## Branch protection rules

### `main`

- Require pull requests.
- Only accept pull requests from `dev`.
- Require frontend, backend, contract, and end-to-end checks.
- Require at least one approval.
- Block force pushes and deletion.

### `dev`

- Require pull requests from `frontend`, `backend`, or a coordinated integration branch.
- Require contract checks and the relevant team tests.
- Require one reviewer from the other team for changes to `shared/`.
- Resolve merge conflicts before the integration window.

### `frontend` and `backend`

- Require pull requests from short-lived feature/fix branches when practical.
- Require the owning team's tests.
- Allow faster review than `dev`, but avoid unreviewed direct pushes to critical files.

## Ownership boundaries

| Path | Primary owner | Required reviewer |
|---|---|---|
| `frontend/**` | Frontend team | Frontend reviewer |
| `backend/app/ml/**` | ML/backend team | ML/backend reviewer |
| `backend/**` | Backend team | Backend reviewer |
| `shared/contracts/**` | Shared | At least one frontend and one backend reviewer |
| `docs/product/**` | Educators/product | Educator/product reviewer |
| `docs/privacy/**` | Shared | Product plus backend reviewer |
| `infra/**` | Backend/DevOps | Backend reviewer |
| `.github/**` | Shared | Team lead |

## Shared API-contract rule

The frontend and backend should not independently invent event shapes. Every cross-boundary payload must be represented in `shared/contracts/` first.

Use OpenAPI 3.1 for REST endpoints, AsyncAPI 3.1 for WebSocket events, and shared JSON Schema for reusable payloads. The complete endpoint and event catalog belongs in `docs/api/unified_api_contracts.md`. FastAPI's runtime `/docs` route is the interactive Swagger UI; the repository's `/docs` directory is the durable context library for humans and agents.

The three most important contracts are:

### Possible missed-content event

```json
{
  "lecture_id": "cs-os-lecture-04",
  "event_id": "evt_123",
  "event_type": "possible_missed_window",
  "start_ms": 931200,
  "end_ms": 978700,
  "signals": ["face_absent", "window_unfocused"],
  "confidence": 0.76,
  "user_confirmed": null
}
```

### Recovery card

```json
{
  "lecture_id": "cs-os-lecture-04",
  "event_id": "evt_123",
  "topic": "Virtual memory",
  "what_you_missed": "The professor introduced the relationship between virtual and physical addresses.",
  "key_facts": ["Each process receives its own virtual address space."],
  "source_timestamps": [{"start_ms": 920000, "end_ms": 990000}],
  "follow_up_question": "Why does each process need a separate address space?"
}
```

### Professor summary

```json
{
  "lecture_id": "cs-os-lecture-04",
  "participant_count": 42,
  "aggregation_window_ms": 15000,
  "highest_signal_intervals": [
    {
      "start_ms": 2040000,
      "end_ms": 2165000,
      "anonymous_signal_ratio": 0.43,
      "topic": "Page replacement algorithms"
    }
  ]
}
```

The backend should validate these contracts with Pydantic. The frontend should generate or mirror TypeScript types from the same schemas. Contract tests should fail when the two sides diverge.

## Local-media and privacy rules

- Raw webcam frames never leave the student's device.
- Required system audio is stored only in `data/local/` or the operating system's app-data directory.
- `data/local/` must be ignored by Git.
- Never place real recordings, credentials, access tokens, or student data in fixtures.
- Use synthetic lecture audio and synthetic event data for tests and demos committed to the repository.
- Only coarse timestamped events or anonymous time-bucket aggregates go to the backend.
- Zoom RTMS disclosures and host approval are part of the normal product flow.
- OpenAI receives only the selected transcript interval and required course context.
- Dropbox receives only user-selected derived artifacts.
- Logging must exclude raw transcript text, student identifiers, and media paths unless explicitly enabled for local development.

## Environment variables

The root `.env.example` should document names only, never real secrets:

```dotenv
APP_ENV=development
API_BASE_URL=http://localhost:8000
MONGODB_URI=mongodb://localhost:27017/lecture_recovery
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=
DROPBOX_APP_KEY=
DROPBOX_APP_SECRET=
ZOOM_CLIENT_ID=
ZOOM_CLIENT_SECRET=
ZOOM_SECRET_TOKEN=
ZOOM_RTMS_ENABLED=false
LOCAL_MEDIA_DIR=
LOG_LEVEL=INFO
```

## Pull-request checklist

Every pull request should answer:

- What user-visible behavior changed?
- Which branch should receive this change?
- Did any shared contract change?
- Were tests added or updated?
- Does the change move raw media or student data off-device?
- Does it introduce a new external API call or secret?
- Does it change system-audio, webcam, Zoom, or retention behavior?
- How can another team member verify it locally?

## `AGENTS.md` starter content

Place an `AGENTS.md` at the repository root with the following instructions for AI coding agents:

```markdown
# Project instructions

This repository contains a privacy-first lecture recovery assistant.

## Product principles

- Help students recover missed learning context; do not punish or label attention.
- Never claim that observable behavior proves whether a student is attentive.
- Keep raw webcam frames, raw system audio, screenshots, and recordings local.
- Send only minimum necessary derived data to external services.
- Professor analytics must be anonymous and aggregated.

## Architecture

- `frontend/`: Electron + React + TypeScript.
- `backend/`: FastAPI, local ML modules, integrations, workers, and persistence.
- `shared/contracts/`: source of truth for frontend/backend payloads.
- `docs/`: product, architecture, privacy, evaluation, and demo documentation.
- `data/local/`: private local media; never commit its contents.

## Development rules

- Read the relevant shared contract before changing an API payload.
- Update the contract, backend schema, frontend type, tests, and example together.
- Do not add cloud storage for raw student media.
- Do not log raw media, credentials, or student identifiers.
- Keep sponsor integrations behind narrow adapters in `backend/app/integrations/`.
- Add or update tests for every behavioral change.
- Do not edit unrelated areas of the repository.
- State assumptions and list changed files when finishing a task.
```

## Prompt template for frontend tasks

```text
You are working on the `frontend` branch of a privacy-first lecture recovery assistant.

Read AGENTS.md, the relevant files in shared/contracts/, and the relevant docs/ before editing.

Task:
[Describe one frontend task.]

Allowed scope:
- frontend/**
- shared/contracts/** only if the API contract must change
- related tests and documentation

Constraints:
- Electron + React + TypeScript
- Required system-audio capture
- Raw webcam/audio/media stays local
- Do not invent backend response shapes; use shared/contracts/
- Preserve timestamp fields in milliseconds
- Add tests for the changed behavior

Acceptance criteria:
[List observable acceptance criteria.]

Before finishing, run the relevant tests and report changed files, test results, and remaining blockers.
```

## Prompt template for backend/ML tasks

```text
You are working on the `backend` branch of a privacy-first lecture recovery assistant.

Read AGENTS.md, the relevant files in shared/contracts/, and the relevant docs/ before editing.

Task:
[Describe one backend or ML task.]

Allowed scope:
- backend/**
- shared/contracts/** only if the API contract must change
- related tests and documentation

Constraints:
- FastAPI + Python
- Raw webcam/audio/media stays local
- Local ML outputs coarse timestamped signals, not definitive attention labels
- Professor analytics are anonymous and aggregated
- Zoom RTMS supplies permitted meeting timeline/transcript data
- OpenAI receives only the minimum relevant transcript/course context
- Preserve timestamp fields in milliseconds
- Add unit and integration tests

Acceptance criteria:
[List observable acceptance criteria.]

Before finishing, run the relevant tests and report changed files, test results, and remaining blockers.
```

## Prompt template for integration tasks

```text
You are working on an integration task for the dev branch.

Read AGENTS.md, shared/contracts/, and the current frontend and backend implementations before editing.

Integration goal:
[Describe one end-to-end user flow.]

Required flow:
[List the exact frontend action, API/WebSocket event, backend behavior, and expected UI result.]

Rules:
- Treat shared/contracts/ as the source of truth.
- Make the smallest changes required to integrate the two sides.
- Do not redesign unrelated frontend or backend modules.
- Preserve local-media privacy boundaries.
- Add or update at least one contract test and one end-to-end test.
- Document environment variables and setup steps.

Before finishing, run frontend, backend, contract, and end-to-end tests. Report changed files, test results, assumptions, and blockers.
```

## Initial repository-scaffolding prompt

Use this prompt after creating the repository and checking out the appropriate setup branch:

```text
Scaffold a monorepo for a privacy-first lecture recovery assistant using the repository structure described in REPO_STRUCTURE_AND_BRANCH_WORKFLOW.md.

Create the directory structure, configuration files, minimal application entry points, shared JSON Schema contracts, synthetic fixtures, and test placeholders. Do not implement full product features yet.

Technical requirements:
- Electron + React + TypeScript frontend
- FastAPI + Python backend
- MongoDB for application metadata
- Redis for cache, temporary session state, and jobs
- Local device storage for raw webcam frames, system audio, screenshots, and recordings
- Required system-audio capture boundary in the Electron main process
- Zoom Meeting SDK Electron integration boundary
- Zoom RTMS receiver boundary in the backend
- OpenAI, Dropbox, and Meta integrations behind isolated adapters
- Millisecond-based shared lecture timestamps
- Pytest, React Testing Library, and Playwright test setup
- Docker Compose for backend development dependencies

Privacy requirements:
- Never add cloud storage for raw student media
- Gitignore all local media and secret files
- Use only synthetic data in committed fixtures
- Professor metrics must be anonymous and aggregated

Create a root AGENTS.md using the instructions in the structure document. Create a concise README with setup commands and an architecture overview.

Before finishing:
1. Run available formatters and tests.
2. List every created file.
3. Explain any dependency or platform limitation, especially system-audio capture and the Zoom Electron wrapper.
4. Do not commit or push changes.
```

## Recommended first integration milestone

The first pull request into `dev` should demonstrate one complete vertical slice:

1. Electron starts a lecture session and establishes the shared session clock.
2. The frontend submits a synthetic missed-content event.
3. FastAPI validates it against the shared contract.
4. The backend retrieves a synthetic transcript interval.
5. A mocked OpenAI adapter returns a structured recovery card.
6. The student UI displays the recovery card.
7. The backend includes the event in an anonymous professor-summary response.
8. An end-to-end test verifies the entire flow.

After this works, replace the synthetic components one at a time with system-audio capture, local signals, Zoom RTMS, real transcription, OpenAI, and Dropbox.
