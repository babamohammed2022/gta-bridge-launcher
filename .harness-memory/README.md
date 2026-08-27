# harness-memory Project Setup

This project is initialized for local harness-memory usage.

## Database

- SQLite path: `.harness-memory/memory.sqlite`

## Recommended next steps

1. Add a project memory with `npx harness-memory memory:add --db .harness-memory/memory.sqlite ...`.
2. Run `npx harness-memory dream:run --db .harness-memory/memory.sqlite --trigger manual` after meaningful work.
3. Use `npx harness-memory memory:why --db .harness-memory/memory.sqlite --scope src/file.ts --trigger before_model` to inspect retrieval decisions.