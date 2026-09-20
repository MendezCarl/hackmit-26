# Feature 6: dropbox-integration

Status: Implemented on an isolated feature branch

Owner: Backend team

Last updated: 2026-09-19

Branch: `feature/backend-dropbox-integration`. Base: `backend`.

Explicit Dropbox folder selection, bounded selected text reads, authorized derived-artifact export, fake providers and an official SDK adapter.

Only this feature's service/router implementations are included. Shared DTOs,
authorization interfaces, bounded request/error handling, repository support and
composition infrastructure are identical across all three worktrees. Having a
sibling's shared payload model does not install its routes or implementation.
No frontend or Person A implementation files are changed.

## Run in this worktree

```sh
python3.14 -m venv backend/venv
backend/venv/bin/python -m pip install -e './backend[dev]' -r backend/requirements-dropbox_integration.txt
LUMINA_DEMO=1 backend/venv/bin/python -m uvicorn app.timeline.application:create_app --factory --host 127.0.0.1 --port 8000 --ws-max-size 256000 --no-access-log
```

Swagger: http://127.0.0.1:8000/docs. Synthetic session: `demo-session`.
Fixture bearer tokens: `demo-student-1` through `demo-student-5`,
`demo-professor`, and `demo-transcriber`. These are not production authentication.

```sh
backend/venv/bin/python -m pytest backend/tests backend/feature_tests/dropbox_integration
backend/venv/bin/python backend/scripts/generate_feature_contracts.py --check
backend/venv/bin/python backend/scripts/generate_openapi_contract.py --check
backend/venv/bin/ruff check backend/app/{signals,transcript,timeline,professor,dropbox,zoom,integrations} backend/feature_tests/dropbox_integration backend/scripts/generate_feature_contracts.py
backend/venv/bin/ruff format --check backend/app/{signals,transcript,timeline,professor,dropbox,zoom,integrations} backend/feature_tests/dropbox_integration backend/scripts/generate_feature_contracts.py
backend/venv/bin/mypy --config-file backend/lecture_features_mypy.ini backend/app/{signals,transcript,timeline,professor,dropbox,zoom,integrations}
```

Contracts: `shared/contracts/dropbox_integration.schema.json` and `docs/api/dropbox_integration.openapi.json`.
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

## Packaging and clean installation

`pyproject.toml` explicitly uses setuptools as the build backend and includes
only `app` and `app.*` packages. Automatic flat-layout discovery also detects
`feature_tests` and rejects editable builds, so package discovery must stay
explicit as new feature test folders are added. Setuptools is a build dependency,
not an application runtime dependency; no runtime packages were added.

The CI dependency-install step runs in a fresh virtual environment and is the
regression check for this failure. Feature tests remain in the checkout and run
through the documented Pytest command; they are not installed as application code.
