# Documentation Index

This directory is the context hub for developers and coding agents. Repository-level agent instructions live in `AGENTS.md`; task-specific product and technical context lives here.

The repository currently contains a minimal Electron JavaScript frontend and FastAPI skeleton. The documents in this directory describe the target architecture; agents must distinguish planned structure from already implemented code.

## Required reading order

Every developer or agent should read context in this order:

1. `/AGENTS.md`
2. `/docs/README.md`
3. The task-relevant product document
4. The task-relevant architecture document
5. `/docs/api/unified_api_contracts.md` when changing any API, WebSocket message, schema, or frontend service
6. The nearest tests for the area being modified

`CLAUDE.md` contains Claude-specific workflow instructions but does not override `AGENTS.md`.

## Documentation structure

```text
docs/
├── README.md
├── ai_provider_tool_calling_plan.md
├── professor_metrics_dashboard.md
├── product/
│   ├── product_overview.md
│   ├── student_user_story.md
│   ├── professor_user_story.md
│   └── demo_script.md
├── architecture/
│   ├── system_overview.md
│   ├── timestamp_model.md
│   ├── local_media_boundary.md
│   └── zoom_integration.md
├── api/
│   ├── unified_api_contracts.md
│   ├── openapi.json
│   └── asyncapi.yaml
├── privacy/
│   ├── consent.md
│   ├── retention_and_deletion.md
│   └── professor_aggregation.md
├── evaluation/
│   ├── signal_evaluation.md
│   ├── recovery_evaluation.md
│   └── token_cost_baseline.md
├── decisions/
│   ├── README.md
│   └── adr_0001_contract_first_api.md
└── prompts/
    ├── frontend_task_template.md
    ├── backend_task_template.md
    └── integration_task_template.md
```

## Context by task type

| Task | Required context |
|---|---|
| Frontend UI | Product story, relevant feature folder, API contract, privacy boundary |
| Electron capture | System overview, local-media boundary, consent, retention policy |
| Backend REST endpoint | Unified API contracts, Pydantic schemas, API tests |
| WebSocket event | Unified API contracts, AsyncAPI file, event schema, contract tests |
| ML signal rule | Student story, signal evaluation, timestamp model, privacy boundary |
| Zoom integration | Zoom integration, timestamp model, API contract, consent flow |
| OpenAI or Muse integration | AI provider tool-calling plan, recovery evaluation, token-cost baseline, privacy boundary |
| Professor metrics | Professor metrics dashboard plan, professor story, aggregation privacy rules, summary contract |
| Dropbox integration | Product overview, privacy boundary, API contract |

## Documentation rules

- Treat documentation as part of the implementation, not a later cleanup task.
- Update the relevant document in the same pull request as a behavioral or contract change.
- Do not duplicate an API payload definition in several Markdown files. Link to the canonical contract instead.
- FastAPI serves live Swagger UI at `/docs`, ReDoc at `/redoc`, and OpenAPI at `/openapi.json`.
- Put the generated, machine-readable REST snapshot in `docs/api/openapi.json`.
- Put machine-readable WebSocket contracts in `docs/api/asyncapi.yaml`.
- Put reusable payload schemas in `shared/contracts/`.
- Record architecture decisions in `docs/decisions/` using numbered ADR files.
- Never place credentials, real student information, raw recordings, or private transcripts in documentation.
- Use synthetic examples with explicit units and realistic field names.
- Every design document should include `Status`, `Owner`, and `Last updated` metadata.

## Contract source-of-truth order

If documentation and implementation disagree, resolve the conflict in this order:

1. Approved decision record in `docs/decisions/`
2. Shared JSON Schema in `shared/contracts/`
3. Pydantic request/response model
4. Generated OpenAPI document
5. Frontend generated type
6. Markdown explanation or example

The team should fix all mismatches in the same pull request.
