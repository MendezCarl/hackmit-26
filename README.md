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
