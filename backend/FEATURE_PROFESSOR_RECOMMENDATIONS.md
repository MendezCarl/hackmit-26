# professor-recommendations: feature review

Status: Implemented; feature branch prepared for review

Base: `origin/backend` at `88d7bbb`

This branch owns only the feature files listed below, plus identical shared
contract/state scaffolding and isolated feature tests. The baseline application
still mounts the baseline routes. The `feature/backend-recovery-flow` integration
worktree mounts all new routers and verifies the complete API flow. Public API
snapshots for that full host are owned by the integration branch; this branch's
baseline snapshot remains accurate for its baseline `app.main`.

## Owned implementation

- `backend/app/professor/recommendations.py`
- `backend/app/professor/recommendation_routes.py`

## Interfaces and tests

See [ADR 0002](../docs/decisions/adr_0002_learning_plan_contracts.md) and the
[new feature runbook](NEW_PLAN_FEATURES.md). Shared schemas and state boundaries
are frozen copies, not other feature services. `MetricsReader`, SDK fakes, and
synthetic host fixtures keep this feature independent of other implementations.

Run `python -m pytest backend/tests -q` in an isolated environment installed with
`python -m pip install -e './backend[dev,ai,vision]'`. The local vision extra is
needed only for vision tests, and the AI extra only for SDK-boundary checks.
The focused checks are under `backend/tests/feature_professor_recommendations/`.

The shared scaffolding is a common ancestor commit. Review and merge feature
implementations before the integration wiring. The integration branch incorporates
feature histories; publication does not merge them into backend, dev or main.
