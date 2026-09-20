# Backend

FastAPI backend for the privacy-first lecture recovery assistant (Lumina).

## Feature layout

```text
backend/app/
├── main.py            # App composition and system endpoints
├── config.py          # Environment settings
├── contracts/         # Canonical shared Pydantic models
├── core/              # Shared clock, typed errors, error handlers
├── auth/              # JWT identity, SessionAccess, route dependencies
├── storage/           # In-memory connections (Mongo/Redis remain faked)
├── sessions/          # Lecture-session lifecycle
├── signals/           # Coarse signal events, participants, corrections
├── transcript/        # Chunk ingestion and the session timeline
├── recovery/          # Recovery jobs, grounded cards, cache
├── cost/              # Provider usage accounting with synthetic labels
├── professor/         # Anonymous, threshold-safe aggregates
├── ws/                # Authenticated WebSocket transport
└── demo/              # Gated synthetic demo orchestration
```

## Setup

```sh
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
python -m pip install -e ".[dev]"

docker compose up -d mongo redis   # optional until storage is faked no longer

APP_ENV=demo PROVIDER_MODE=mock \
  uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- `PROVIDER_MODE=mock` (default) generates deterministic synthetic recovery
  cards and labels all usage `synthetic`; `live` is not implemented yet.
- `APP_ENV=demo` unlocks `POST /api/v1/demo/runs` and demo token minting;
  both are unavailable in development and production.

## API documentation

FastAPI generates the OpenAPI schema directly from typed routes and
route-bound Pydantic models.

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Raw OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

After changing an endpoint or a Pydantic model used by an endpoint, regenerate
the reviewable repository snapshot:

```sh
python scripts/generate_openapi_contract.py
python scripts/generate_shared_contracts.py   # shared/contracts/*.schema.json
```

Verify the snapshot without modifying files:

```sh
python scripts/generate_openapi_contract.py --check
pytest
```

CI runs both checks and fails when `docs/api/openapi.json` is stale.

## Endpoints

System: `GET /health`, `GET /api/status`

Sessions (`/api/v1/sessions`):

- `POST /api/v1/sessions` — create one running occurrence of a lecture.
- `GET /api/v1/sessions/{session_id}` — read an authorized session.

Signals (`/api/v1/sessions/{session_id}`):

- `POST /events/batch` — ingest coarse, timestamped signal events.
- `POST /participants` — opt in as a participant for anonymous aggregation.
- `POST /events/{event_id}/confirmation` — student correction.

Transcript:

- `POST /transcript/batch` — ingest timestamped transcript chunks.
- `GET /transcript?start_ms=&end_ms=` — read final chunks in a window.

Recovery:

- `POST /recovery/jobs` — request a grounded recovery card for an interval.
  Optional `Idempotency-Key` header makes retries return the original job.
  Source events overlapping the request merge into one context window.
- `GET /recovery/jobs/{job_id}` — job status or typed failure.
- `GET /recovery/cards/{card_id}` — personal card retrieval.
- `GET /cost/metrics` — session-owner usage metrics; entries are labeled
  `measured` only for real provider calls and `synthetic` for mock output.

Providers:

- `PROVIDER_MODE=mock` (default) — deterministic synthetic cards.
- `PROVIDER_MODE=live` — the OpenAI adapter
  (`app/integrations/openai/`) requests strict JSON-schema output, rejects
  ungrounded citations, and records measured token usage. Requires
  `pip install -e "./backend[live]"` and `OPENAI_API_KEY`; startup fails
  fast otherwise.

Professor:

- `GET /professor/summary` — anonymous aggregates, suppressed below the
  configured minimum group size (clearly labeled synthetic demo threshold).

WebSocket:

- `GET /ws/v1/sessions/{session_id}?token=<jwt>` — typed session events.

Demo (gated on `APP_ENV=demo`):

- `POST /api/v1/demo/runs` — full synthetic end-to-end run.
- `POST /api/v1/demo/token` — mint a synthetic actor token.

## Privacy boundaries

- Raw webcam frames, continuous raw audio, screenshots, and recordings are
  never accepted; request models reject unexpected fields.
- Identity and roles come from verified JWTs, never request bodies.
- Recovery cards are personal: cache keys include the requesting user, and
  cards are readable only by their owner and the session owner.
- Professor summaries are anonymous, deduplicated per participating user,
  and suppressed below the minimum group size.

## Testing

The default suite never calls live providers; the recovery generator is a
deterministic mock whose usage is labeled `synthetic`.

```sh
pytest
```

