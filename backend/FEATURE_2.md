# Feature 2: signal-timeline

Status: Implemented on an isolated feature branch

Owner: Backend team

Last updated: 2026-09-19

Branch: `feature/backend-signal-timeline`. Base: `backend`.

Consent-aware signal and transcript ingestion, corrections, missed-window rules, bounded timeline/context reads, transcript WebSocket ingestion, and simulated Zoom timestamp mapping.

Only this feature's service/router implementations are included. Shared DTOs,
authorization interfaces, bounded request/error handling, repository support and
composition infrastructure are identical across all three worktrees. Having a
sibling's shared payload model does not install its routes or implementation.
No frontend or Person A implementation files are changed.

## Run in this worktree

```sh
python3.14 -m venv backend/venv
backend/venv/bin/python -m pip install -e './backend[dev]' -r backend/requirements-signal_timeline.txt
LUMINA_DEMO=1 backend/venv/bin/python -m uvicorn app.timeline.application:create_app --factory --host 127.0.0.1 --port 8000 --ws-max-size 256000 --no-access-log
```

Swagger: http://127.0.0.1:8000/docs. Synthetic session: `demo-session`.
Fixture bearer tokens: `demo-student-1` through `demo-student-5`,
`demo-professor`, and `demo-transcriber`. These are not production authentication.

```sh
backend/venv/bin/python -m pytest backend/tests backend/feature_tests/signal_timeline
backend/venv/bin/python backend/scripts/generate_feature_contracts.py --check
backend/venv/bin/python backend/scripts/generate_openapi_contract.py --check
backend/venv/bin/ruff check backend/app/{signals,transcript,timeline,professor,dropbox,zoom,integrations} backend/feature_tests/signal_timeline backend/scripts/generate_feature_contracts.py
backend/venv/bin/ruff format --check backend/app/{signals,transcript,timeline,professor,dropbox,zoom,integrations} backend/feature_tests/signal_timeline backend/scripts/generate_feature_contracts.py
backend/venv/bin/mypy --config-file backend/lecture_features_mypy.ini backend/app/{signals,transcript,timeline,professor,dropbox,zoom,integrations}
```

Contracts: `shared/contracts/signal_timeline.schema.json` and `docs/api/signal_timeline.openapi.json`.
Regenerate using `backend/scripts/generate_feature_contracts.py`.
The baseline `app.main` and its existing OpenAPI remain untouched. The new feature
app registers only installed fixed-catalog modules; host integration uses
`register_features(app, services)` with real authorization and configured services.

Real JWT/OAuth, retention orchestration, approved production aggregation policy and
authorized provider clients remain host dependencies. Zoom is simulated; Dropbox
live account behavior and Mongo persistence need explicit external verification.
Default tests are synthetic. The Mongo test is opt-in via `LUMINA_TEST_MONGO_URI`.

## Git status

This branch contains one feature plus the identical shared support needed to run
it independently. Keep shared-support edits synchronized across feature branches.
Review public contracts with frontend and backend owners before merging.
The combined integration checkout is maintained separately.

## Optional phone observations

See [phone signal behavior and privacy](PHONE_SIGNALS.md) for the optional local
observation contract, corroboration rules, professor exclusions, and test scope.
