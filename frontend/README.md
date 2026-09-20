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

Use `APP_ENV=demo` (or `APP_ENV=test`) locally so educator reports use the
synthetic aggregation policy. In the default environment, the metrics endpoint
requires `LUMINA_METRICS_POLICY_JSON` with `is_approved: true`, and the summary
endpoint is disabled by design. When the local service is unavailable, the
renderer keeps its synthetic fixture pages available and labels them
`Demo mode · synthetic data`. Live OpenAI recovery requires
`PROVIDER_MODE=live` and `OPENAI_API_KEY` (plus the backend's configured model);
normal development and tests use deterministic synthetic behavior.
