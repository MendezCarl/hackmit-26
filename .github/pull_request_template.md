## Summary

<!-- Describe the user-visible and technical outcome. -->

## Testing

<!-- List commands and checks that were run. -->

- [ ] External APIs are mocked/faked in the default test suite; any live-provider test is opt-in and sandbox-only.

## Contract and documentation checklist

- [ ] No API or event contract changed.
- [ ] API/event changes include updated Pydantic models and shared contracts.
- [ ] `python backend/scripts/generate_openapi_contract.py` was run after route/model changes.
- [ ] `python backend/scripts/generate_openapi_contract.py --check` passes.
- [ ] Relevant `/docs` context was updated.

## Dependency checklist

- [ ] No new dependency was added.
- [ ] Any new dependency is justified as recommended, safer, or materially easier than direct implementation.
- [ ] Unused exploratory dependencies were removed.

## Privacy and security

<!-- Explain whether this changes local media, student data, logs, authentication, or external API calls. -->
