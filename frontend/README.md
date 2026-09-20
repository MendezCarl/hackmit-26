# Bloom frontend

The Electron renderer talks to the local FastAPI service through the
main-process IPC bridge. Start the backend first:

```sh
cd backend
source .venv/bin/activate
APP_ENV=demo fastapi dev app/main.py
```

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

Set `BLOOM_BACKEND_URL` when the backend does not run at
`http://127.0.0.1:8000`.

Bloom's optional Zoom cue detects desktop process names locally; it does not
use the Zoom SDK or inject UI into the Zoom window. The always-on-top cue is
only a reminder to open Bloom and remains independent of Zoom's meeting data.

Build a local installer with:

```sh
npm run package
```

The repository release workflow builds platform installers on version tags and
attaches them to a draft GitHub Release.

Use `APP_ENV=demo` (or `APP_ENV=test`) locally so educator reports use the
synthetic aggregation policy. In the default environment, the metrics endpoint
requires `LUMINA_METRICS_POLICY_JSON` with `is_approved: true`, and the summary
endpoint is disabled by design. When the local service is unavailable, the
renderer keeps its synthetic fixture pages available and labels them
`Demo mode · synthetic data`. Live OpenAI recovery requires
`PROVIDER_MODE=live` and `OPENAI_API_KEY` (plus the backend's configured model);
normal development and tests use deterministic synthetic behavior.
