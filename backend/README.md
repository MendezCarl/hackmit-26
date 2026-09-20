# Backend

FastAPI backend targeting Python 3.14.

## Implementation status and feature apps

See [the implementation report](../docs/implementation/backend_status.md) for what
has been built, tested, pushed, and left for host integration. The three feature
branches cover signal/transcript ingestion and timeline, professor summaries,
and Dropbox operations. OpenAI recovery generation is still planned.

The setup below starts the baseline `app.main`, whose routes are listed at the
end of this file. It does not mount the new feature routes. Use the
[feature runbook](LECTURE_FEATURES.md) to choose the instructions for your checked-out
branch. Each feature checkout contains one of `FEATURE_2.md`, `FEATURE_4.md`, or
`FEATURE_6.md`. The combined demo is only available in the original local combined
checkout. Feature demo commands require explicit demo mode.

## Setup

Run these commands from the `backend/` directory:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
fastapi dev app/main.py
```

## API documentation

FastAPI generates the OpenAPI schema directly from typed routes and route-bound Pydantic models.

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Raw OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

After changing an endpoint or a Pydantic model used by an endpoint, regenerate the reviewable repository snapshot:

```sh
python scripts/generate_openapi_contract.py
```

Verify the snapshot without modifying files:

```sh
python scripts/generate_openapi_contract.py --check
pytest
```

CI runs both checks and fails when `docs/api/openapi.json` is stale.

## Endpoints

- `GET /health`
- `GET /api/status`
