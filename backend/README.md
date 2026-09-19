# Backend

FastAPI backend targeting Python 3.14.

## Setup

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
