# Claude Code Instructions

Read and follow `AGENTS.md` completely before beginning any task. `AGENTS.md` is the repository-wide source of truth; this file adds Claude-specific workflow expectations and does not replace it.

## Workflow

1. Read `docs/README.md` and only the documents relevant to the current task.
2. Inspect the implementation, shared contracts, and nearby tests before editing.
3. State a short implementation plan for work that spans multiple files or layers.
4. Make the smallest coherent change that satisfies the task.
5. Preserve existing architecture and naming conventions unless the task explicitly changes them.
6. Run the most targeted tests first, then the broader relevant checks.
7. Report the outcome using the completion format in `AGENTS.md`.

## Contract-first behavior

- For REST work, inspect `docs/api/unified_api_contracts.md`, Pydantic models, and the generated OpenAPI schema.
- For WebSocket work, inspect the AsyncAPI document and reusable event schemas.
- Never allow the frontend and backend to diverge on payload names, required fields, timestamps, or errors.
- If a task requires a contract change, change the contract and tests before or with the implementation.

## Code-generation behavior

- Use precise, domain-specific names.
- Follow language-specific naming rules from `AGENTS.md`; do not force Python naming conventions onto TypeScript.
- Add Python docstrings and TypeScript TSDoc for public and non-obvious functions, including inputs and outputs.
- Do not add comments that simply repeat the code.
- Do not create broad `helpers`, `utils`, or `common` modules when a domain-specific module name is possible.
- Do not introduce new dependencies without explaining why the existing stack cannot satisfy the requirement.

## Privacy guardrail

Stop and flag the issue if a requested implementation would upload raw webcam frames, system audio, screenshots, or recordings by default. Propose a local-processing or derived-data alternative.
