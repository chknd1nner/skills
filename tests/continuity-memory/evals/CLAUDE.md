# Continuity-Memory Prompt Evals

Behavioral compliance tests for the continuity-memory project instructions. Tests whether the AI correctly drafts, consolidates, routes, and stays silent about memory operations.

## How it works

`run_evals.py` sends prompts to the `claude` CLI with patched project instructions that swap the real memory system for `mock_memory_system.py`. It then checks the session JSONL for three assertion tiers:

1. **thinking_contains** — did the model *recognise* the signal?
2. **tool_called** — did the model *act* on it (Bash + `memory.commit`/`.consolidate`)?
3. **text_absent** — did the model *stay silent* about memory operations?

Divergence between tiers 1 and 2 (thought about it but didn't act) is the key failure mode.

## Running

```bash
# From outside Claude Code (unset CLAUDECODE first)
python3 run_evals.py                          # all evals, 5 parallel workers
python3 run_evals.py --ids 1,2,3 --verbose    # specific evals with detail
python3 run_evals.py --source claude-md        # test CLAUDE.md instead of project-instructions
python3 run_evals.py --dry-run                 # show what would run
```

## Adding evals

Add entries to `evals.json`. Each eval needs:
- `id` (int), `name`, `persona` (companion/fitness/creative/dev/any), `prompt`
- `assertions` array — each with `id`, `type`, `pattern` (regex), optional `path_contains`
- Section dividers use `{"_section": "=== HEADING ==="}` and are filtered out at load time
