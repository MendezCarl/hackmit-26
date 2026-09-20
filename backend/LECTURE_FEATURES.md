# Lecture feature runbook

Status: Implemented feature package; host/live-provider integration pending

Owner: Backend team

Last updated: 2026-09-19

Scope: signal/transcript ingestion and timeline (including simulated Zoom),
anonymous professor summaries, and Dropbox materials/derived-artifact export.
The baseline `app.main` entry point and frontend were not changed. Authentication,
recovery generation, and host integration remain separate work. The shared
`pyproject.toml` was updated to fix package discovery during fresh installation.
A feature registration function and standalone demo application provide an
independently runnable handoff.

See [implementation status and verification evidence](../docs/implementation/backend_status.md)
for the completed work and remaining dependencies. This document is shared across
the three feature branches. Choose the instructions matching your checked-out
branch; the combined-demo commands below require the original uncommitted local
checkout and do not work in an isolated feature checkout.

## Choose the runnable feature

| Branch | Runbook included in that checkout | Published instructions |
|---|---|---|
| `feature/backend-signal-timeline` | `backend/FEATURE_2.md` | [Feature 2](https://github.com/MendezCarl/hackmit-26/blob/138cff9/backend/FEATURE_2.md) |
| `feature/backend-professor-aggregation` | `backend/FEATURE_4.md` | [Feature 4](https://github.com/MendezCarl/hackmit-26/blob/c772618/backend/FEATURE_4.md) |
| `feature/backend-dropbox-integration` | `backend/FEATURE_6.md` | [Feature 6](https://github.com/MendezCarl/hackmit-26/blob/5c58361/backend/FEATURE_6.md) |

The feature runbook installs the matching requirements file and starts only its
installed routes. See the [branch guide](FEATURE_BRANCHES.md) for workspace details.

## Dependencies

Install everything into `backend/venv`. The existing FastAPI/Pydantic dependencies
remain authoritative in `pyproject.toml`. The feature-specific requirements file
adds the official Dropbox SDK and Motor adapter, because protocol clients should
not be reimplemented. HTTPX, JSON Schema, Pytest, Ruff and Mypy support isolated
tests and validation. Redis jobs, JWT issuance, OpenAI and local audio transcription
are outside these implemented features and remain work for the host/local client.

Setuptools is explicitly declared as the build backend, and package discovery
includes only `app` and its subpackages. This fixes the initial CI installation
failure caused by discovering both `app` and `feature_tests` as top-level packages.
Feature tests remain in the checkout and run in CI; they are not application packages.

Provider references:
- https://dropbox-sdk-python.readthedocs.io/en/latest/api/dropbox.html
- https://motor.readthedocs.io/en/stable/api-asyncio/asyncio_motor_collection.html

No provider credentials or real lecture material belong in fixtures.

## Local-only combined synthetic demo

This section records the original `feature/backend-lecture-features` checkout.
Its combined scripts, fixtures, and requirements remain uncommitted and are not
included on any of the three published feature branches. Use the feature-specific
runbooks above for a fresh clone.

From the repository root of that combined local checkout:

```sh
python3.14 -m venv backend/venv
source backend/venv/bin/activate
python -m pip install -e './backend[dev]' -r backend/requirements-lecture-features.txt
LUMINA_DEMO=1 python -m uvicorn app.timeline.application:create_app \
  --factory --host 127.0.0.1 --port 8000 --ws-max-size 256000 --no-access-log
```

In a second terminal, from the repository root:

```sh
backend/venv/bin/python backend/scripts/demo_lecture_features.py
```

Restart the demo server before repeating: the script deliberately ends the fixture
lecture, and export collisions never overwrite previous artifacts. No Mongo,
Redis, OAuth credentials or API keys are needed for this synthetic flow.
Known `demo-*` tokens are fixtures, never production authentication. Without
`LUMINA_DEMO=1`, the standalone factory refuses startup. Bind the demo to loopback.

Swagger is at `http://127.0.0.1:8000/docs`, ReDoc at `/redoc`, and the live contract
at `/openapi.json`. The synthetic session is `demo-session`. For manual requests,
use `Authorization: Bearer demo-student-1`, `demo-professor`, or `demo-transcriber`
as appropriate. There are five synthetic student tokens, numbered 1 through 5.

## Local-only combined demonstration

1. Open Swagger and show the typed ingestion/summary/Dropbox feature routes.
2. Run the demo script: it ingests a synthetic transcript and two participants'
   possible missed-content events, then verifies duplicate retries are no-ops.
3. Show the bounded context result and the `mock` Dropbox export receipt.
4. Show the ended-session summary: five opted-in participants, two with a coarse
   signal in the first bucket, and a compassionate recap suggestion.
5. Run the small-group privacy test below to demonstrate null counts/ratios when
   fewer than five participants consent. State that the card is a fixture from
   the host artifact-reader boundary, not an OpenAI generation result.

```sh
backend/venv/bin/python -m pytest backend/feature_tests/lecture_features/test_professor.py -q
```

## Local-only combined checks

The commands below use the combined scripts; isolated branches use
`generate_feature_contracts.py` and their own test directory as documented in
the matching feature runbook.

```sh
backend/venv/bin/python -m pytest backend/tests backend/feature_tests
backend/venv/bin/python backend/scripts/generate_lecture_features_contracts.py --check
backend/venv/bin/python backend/scripts/generate_openapi_contract.py --check
backend/venv/bin/ruff check backend/app/{signals,transcript,timeline,professor,dropbox,zoom,integrations} backend/feature_tests/lecture_features backend/scripts/{generate_lecture_features_contracts,demo_lecture_features}.py
backend/venv/bin/ruff format --check backend/app/{signals,transcript,timeline,professor,dropbox,zoom,integrations} backend/feature_tests/lecture_features backend/scripts/{generate_lecture_features_contracts,demo_lecture_features}.py
backend/venv/bin/mypy --config-file backend/lecture_features_mypy.ini backend/app/{signals,transcript,timeline,professor,dropbox,zoom,integrations}
```

Regenerate the local combined feature contracts with
`backend/venv/bin/python backend/scripts/generate_lecture_features_contracts.py`.
The existing generator continues to validate the unchanged baseline app.

The local Mongo contract test is explicit and uses a fresh synthetic database:

```sh
LUMINA_TEST_MONGO_URI=mongodb://127.0.0.1:27017 \
  backend/venv/bin/python -m pytest backend/feature_tests/lecture_features/test_mongo_integration.py -q
```

It deletes only the random `lumina_lecture_features_test_*` database it creates. Default
tests skip it and never connect to Mongo or external providers.

## Host application handoff

See [feature contracts and integration requirements](../docs/api/lecture_features.md).
Call `register_features(app, services)` once with host authorization, consent,
repositories, an approved aggregation policy, and authorized artifact/Dropbox
adapters. It excludes all demo-only routes. The host application still needs its main entry point,
JWT/OAuth, encrypted provider-token storage, recovery generation, Redis jobs,
retention orchestration and root deployment configuration.

New files under `app/signals/`, `app/transcript/`, `app/timeline/`, `app/professor/`,
`app/dropbox/`, `app/zoom/`, and the Zoom/Dropbox provider subdirectories are owned by
their corresponding features. Feature tests, scripts, and `lecture_features.*`
contract snapshots are isolated from the baseline app. Separate branches contain
identical shared support, so shared edits must stay synchronized. Cross-team
contract review is still required before host integration.

## Optional phone observations

See [phone signal behavior and privacy](PHONE_SIGNALS.md) for the new local
observation types, corroboration thresholds, and professor aggregation exclusions.
