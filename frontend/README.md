# Bloom frontend

The Electron app defaults to the hosted Render backend at
`https://bloom-backend-srdd.onrender.com`. To use a local FastAPI backend,
start it first:

**macOS/Linux**

```sh
cd backend
source .venv/bin/activate
APP_ENV=demo fastapi dev app/main.py
```

**Windows (PowerShell)**

```powershell
Set-Location backend
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:APP_ENV = "demo"
fastapi dev app/main.py
```

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

For macOS/Linux local development:

```sh
BLOOM_BACKEND_URL=http://127.0.0.1:8000 npm run dev
```

For PowerShell:

```powershell
$env:BLOOM_BACKEND_URL="http://127.0.0.1:8000"; npm run dev
```

Bloom's optional Zoom cue detects desktop process names locally; it does not
use the Zoom SDK or inject UI into the Zoom window. The always-on-top cue is a
separate Bloom window layered over Zoom and remains independent of Zoom's
meeting data; for students it also shows the drift recovery card in place so
they never have to leave the meeting.

Build a local installer for the current OS with `npm run package`, or target a
platform explicitly:

```sh
npm run package:mac    # unsigned universal dmg + zip
npm run package:win    # NSIS installer + zip
npm run package:linux  # AppImage + deb
```

On Windows, if `npm run package:win` prompts for or fails on code signing,
disable identity discovery before building:

```powershell
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
npm run package:win
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
