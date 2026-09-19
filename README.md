# hackmit-26

Electron TypeScript desktop app with a Python FastAPI backend.

## Branch Workflow

- `main`: protected release branch; changes should land through pull requests.
- `dev`: integration branch for ongoing work.
- `frontend`: frontend feature branch.
- `backend`: backend feature branch.

## Frontend

```sh
cd frontend
npm install
npm run dev
```

The Electron renderer expects the backend at `http://127.0.0.1:8000`.

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
