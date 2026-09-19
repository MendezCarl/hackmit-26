# Backend

FastAPI backend targeting Python 3.14.

## Setup

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
fastapi dev app/main.py
```

## Endpoints

- `GET /health`
- `GET /api/status`
