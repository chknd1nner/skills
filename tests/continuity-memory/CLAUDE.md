# Continuity-Memory Tests

Two test suites for the continuity-memory system:

- `unit/` — pytest tests for pure functions (section editing, config parsing). Run locally, no network.
- `evals/` — behavioral compliance tests for project instructions. Shells out to `claude` CLI, checks session JSONL.

Source code under test lives in `common/continuity-memory/scripts/`.
