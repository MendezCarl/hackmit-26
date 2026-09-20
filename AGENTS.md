# Repository Agent Instructions

These instructions apply to all coding agents working anywhere in this repository.

## Read before editing

1. Read this file completely.
2. Read `docs/README.md`.
3. Read the task-relevant product, architecture, privacy, and API documents.
4. Inspect the existing implementation and nearest tests before proposing changes.
5. If instructions conflict, follow the more specific instruction unless it violates the privacy rules in this file.

## Product principles

- Build a compassionate lecture recovery assistant, not an attention-policing system.
- Describe ML output as a possible missed-content signal, never proof of attention or comprehension.
- Keep raw webcam frames, system audio, screenshots, and recordings local to the user's device.
- Send external services only the minimum derived data required for a feature.
- Professor analytics must be anonymous and aggregated.
- Preserve user consent, retention, deletion, and correction controls.

## Repository boundaries

- `frontend/`: Electron, React, and TypeScript.
- `backend/`: FastAPI, Python services, local ML modules, integrations, and workers.
- `shared/contracts/`: reusable machine-readable payload schemas.
- `docs/`: product, architecture, privacy, API, evaluation, decision, and prompt context.
- `data/local/`: private local media; never commit its contents.
- `tests/`: contract, integration, and end-to-end tests.

The repository currently contains a minimal Electron JavaScript skeleton. React and TypeScript are the target architecture. Do not rewrite the existing skeleton merely to match the target; migrate it only through an explicit, reviewed task.

Backend implementation history and verified feature status are recorded in
[`docs/implementation/backend_status.md`](docs/implementation/backend_status.md).
It distinguishes the baseline app, pushed feature branches, the local combined
checkout, mocked providers, and planned recovery work. Use it as a navigation
and handoff reference; verify the current branch and code before relying on a
recorded status. It does not replace these rules or the API contract precedence.

## Naming standards

Names must describe behavior or domain purpose. Avoid vague names such as `helper`, `utils`, `data`, `thing`, `temp`, `manager`, `process_data`, or `handle_stuff` unless the surrounding type gives them a precise meaning.

### Python

- Modules, files, functions, methods, parameters, and variables use `snake_case`.
- Classes, Pydantic models, and exceptions use `PascalCase`.
- Constants use `UPPER_SNAKE_CASE`.
- Boolean names begin with `is_`, `has_`, `can_`, or `should_` when practical.
- Async functions should describe the operation; do not add an `async_` prefix only because they are asynchronous.
- Prefer verb-object helper names such as `map_rtms_timestamp`, `calculate_signal_window`, or `build_recovery_card`.

### TypeScript and React

- Functions, variables, and object members use `camelCase` because that is the language ecosystem convention.
- React components, classes, interfaces, and type aliases use `PascalCase`.
- React hooks start with `use`, such as `useLectureSession`.
- Constants use `UPPER_SNAKE_CASE` when truly constant across the module.
- JSON API properties remain `snake_case` and must be represented by generated contract types.
- Source filenames use `snake_case`; React component filenames may use `PascalCase` when the file exports one primary component.
- Prefer descriptive helpers such as `mapRtmsTimestamp`, `calculateSignalWindow`, or `buildRecoveryCard`.

### API and data

- REST paths use plural nouns and `/api/v1` versioning.
- JSON fields use `snake_case`.
- Event types use dotted past-tense or state-change names, such as `recovery_card.completed`.
- Lecture-relative time uses integer milliseconds with `_ms` suffixes.
- Wall-clock timestamps use UTC ISO 8601 strings.
- IDs use explicit names such as `session_id`, `event_id`, and `card_id`; never use a bare `id` when multiple entities are in scope.

## Function and module design

- Give every function one clear responsibility.
- Prefer small pure functions for parsing, mapping, scoring, and transformation logic.
- Separate I/O from domain logic.
- Use typed models at every process, API, and provider boundary.
- Do not pass unvalidated dictionaries across layers when a Pydantic model or TypeScript type exists.
- Avoid hidden global state and unexplained side effects.
- Replace magic numbers and strings with named constants or configuration.
- Keep provider-specific code inside `backend/app/integrations/<provider>/`.
- Keep route handlers thin; put domain behavior in services.
- Keep React components focused on rendering and interaction; put API and state behavior in services/hooks.

## Dependency policy

- First inspect the standard library, the current dependency manifests, and existing project code.
- Implement small, project-specific helpers and domain logic directly when the behavior is clear and testable.
- Prefer the fewest dependencies that keep the solution readable, reliable, and maintainable.
- Do not add a package merely to avoid writing a small amount of straightforward code.
- Use an established dependency when it is the recommended implementation, materially simpler, or safer than custom code.
- Do not reimplement cryptography, authentication standards, OAuth, protocol clients, media codecs, database drivers, or mature security-sensitive functionality.
- Before adding a dependency, document why existing code and standard-library functionality are insufficient.
- Add dependencies only to the appropriate manifest, use a maintained package, and include focused tests for the integration.
- Remove exploratory dependencies that are not used by the final implementation.

## Comments and documentation

- Every exported/public function, class, endpoint, and non-obvious helper must document its inputs, outputs, raised errors, and relevant side effects.
- Python uses docstrings with `Args:`, `Returns:`, and `Raises:` sections when applicable.
- TypeScript uses TSDoc/JSDoc with `@param`, `@returns`, and `@throws` when applicable.
- API routes must describe request fields, response fields, error cases, authentication, and privacy behavior through Pydantic/OpenAPI metadata.
- Comments should explain why a decision or constraint exists. Do not narrate obvious syntax line by line.
- Document units in names and comments, especially milliseconds, seconds, ratios, and byte sizes.
- Update documentation in the same pull request as behavior or contract changes.

Python example:

```python
def calculate_signal_window(
    events: list[SignalEvent],
    window_size_ms: int,
) -> list[SignalWindow]:
    """Aggregate local signal events into fixed lecture-time windows.

    Args:
        events: Validated signal events ordered by lecture-relative timestamp.
        window_size_ms: Width of each aggregation window in milliseconds.

    Returns:
        Anonymous signal windows ordered by their start timestamp.

    Raises:
        ValueError: If window_size_ms is not positive.
    """
```

TypeScript example:

```typescript
/**
 * Maps a Zoom RTMS timestamp to the shared lecture-session clock.
 *
 * @param rtmsTimestampMs - Zoom timestamp in milliseconds.
 * @param sessionOriginMs - Zoom timestamp representing lecture time zero.
 * @returns Lecture-relative time in milliseconds.
 * @throws RangeError When the timestamp occurs before the session origin.
 */
export function mapRtmsTimestamp(
  rtmsTimestampMs: number,
  sessionOriginMs: number,
): number {
  // Keep all cross-service timing relative to one session origin.
  return rtmsTimestampMs - sessionOriginMs;
}
```

## API contract rules

- Read `docs/api/unified_api_contracts.md` before changing an API or WebSocket message.
- Treat `shared/contracts/` as the reusable payload source of truth.
- Use OpenAPI 3.1 for REST and AsyncAPI 3.1 for WebSocket messages.
- Keep FastAPI Swagger UI enabled at `/docs`, ReDoc at `/redoc`, and the raw schema at `/openapi.json`.
- Every endpoint must use typed parameters and an explicit response model so its request and response schemas appear in Swagger.
- Update the JSON Schema, Pydantic model, OpenAPI/AsyncAPI snapshot, generated frontend type, examples, and tests together.
- Run `python backend/scripts/generate_openapi_contract.py` after changing a FastAPI route or any Pydantic model referenced by a route.
- Run `python backend/scripts/generate_openapi_contract.py --check` before finishing; CI must fail when the checked-in OpenAPI contract is stale.
- Do not independently invent frontend and backend payload shapes.
- Do not accept raw webcam frames, raw audio, or recordings through the application API.
- Use one standard error response and stable machine-readable error codes.
- Preserve backward compatibility within `/api/v1`; version breaking changes.

## Privacy and security

- Never commit credentials, tokens, `.env` files, student data, raw media, or private transcripts.
- Use synthetic fixtures.
- Redact secrets, authorization headers, transcript text, student identifiers, and local media paths from logs.
- Verify Zoom webhook signatures and OAuth state.
- Store provider tokens using the project's approved encrypted mechanism.
- Validate all external inputs, including provider callbacks and WebSocket messages.
- Enforce authorization in the backend; hiding UI elements is not authorization.
- Aggregate professor metrics only after the approved minimum group-size threshold is met.

## Testing and quality

- Add or update tests for every behavioral change.
- Prefer mocks, fakes, and recorded synthetic fixtures at external API boundaries.
- The default test suite and CI must not call live provider APIs.
- Live provider tests must be explicit, opt-in integration tests that use provider sandboxes, repository secrets, and synthetic data; document how to run them.
- Keep test doubles aligned with documented provider contracts, and use focused sandbox contract tests when mocks cannot validate provider behavior adequately.
- Python must pass formatting, linting, type checking, and Pytest.
- TypeScript must pass formatting, linting, type checking, component tests, and relevant Playwright tests.
- Contract changes require contract tests.
- Route or API-model changes require a regenerated `docs/api/openapi.json` snapshot.
- Bug fixes require a regression test that fails before the fix when practical.
- Test error paths, privacy boundaries, time-range validation, and provider failure behavior.
- Do not weaken, skip, or delete tests merely to make CI pass.

## Git and scope discipline

- Work from the branch appropriate to the task: `frontend`, `backend`, or an approved short-lived feature branch.
- Do not commit directly to `main` or `dev`.
- Do not edit unrelated files.
- Do not overwrite user changes.
- Keep commits and pull requests focused on one coherent change.
- Changes to `shared/contracts/` or `docs/api/` require frontend and backend review.

## Completion report

Before finishing a task, report:

1. Outcome
2. Files changed
3. Contract or documentation changes
4. Tests and checks run
5. Privacy or security impact
6. Remaining assumptions or blockers
