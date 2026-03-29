# mdedit Benchmark Suite v2 — Design Spec

## Purpose

Answer: "Does mdedit save tokens compared to standard Claude Code tools, and by how much?"

This is a decision-support tool for whether to continue developing mdedit. It must be re-runnable over time to track whether improvements to the baseline (model, harness, tools) erode mdedit's advantage.

## Design Principles

- **Lean**: 4 curated scenarios, not 9. Only include tasks where mdedit has a structural advantage.
- **Modular**: Adding a new scenario means dropping a folder into `scenarios/` — no code changes.
- **Re-runnable**: `--bare` mode ensures deterministic, config-free execution. Results are timestamped and never overwritten.
- **Two outputs**: A summary table (quick answer) and narrative diffs from captured transcripts (the intuition for why).

## Architecture

```
tests/mdedit/benchmarks-v2/
├── run.py                      # runner: discovers scenarios, dispatches agents, saves results
├── analyze.py                  # reads a results directory, produces summary.md + narrative.md
├── validate.py                 # correctness checks (file-diff, report-contains)
├── fixtures/                   # shared document fixtures
│   ├── small.md                #  ~50 lines
│   ├── medium.md               # ~190 lines
│   └── large.md                # ~500 lines
├── system-prompts/
│   ├── mdedit.md               # mdedit command reference + rules
│   └── baseline.md             # standard tools + rules
├── scenarios/                  # one directory per benchmark scenario
│   ├── replace-small/
│   │   ├── scenario.yaml
│   │   ├── prompt.md
│   │   └── expected/
│   │       ├── small.md
│   │       ├── medium.md
│   │       └── large.md
│   ├── replace-large/
│   │   ├── scenario.yaml
│   │   ├── prompt.md
│   │   └── expected/
│   │       ├── medium.md       # (no small — excluded in scenario.yaml)
│   │       └── large.md
│   ├── delete-section/
│   │   ├── scenario.yaml
│   │   ├── prompt.md
│   │   └── expected/
│   │       ├── small.md
│   │       ├── medium.md
│   │       └── large.md
│   └── edit-and-verify/
│       ├── scenario.yaml
│       └── prompt.md           # (no expected/ — uses report-contains validation)
└── results/                    # timestamped output directories
    └── run-YYYYMMDD-HHMMSS/
        ├── results.json        # all run data: tokens, pass/fail, timing
        ├── summary.md          # rendered comparison table
        ├── narrative.md        # before/after transcript analysis for showcase scenarios
        └── transcripts/        # full agent JSON responses (showcase scenarios only)
            ├── replace-large-mdedit-large-rep1.json
            ├── replace-large-baseline-large-rep1.json
            └── ...
```

## Scenario Definition (`scenario.yaml`)

```yaml
name: replace-small
description: Replace a small section (~5 lines) with new content
sizes: [small, medium, large]
validation: file-diff       # or: report-contains
showcase: false             # true = save full transcript for narrative analysis
```

Fields:
- `name`: Must match the directory name. Used as the task slug everywhere.
- `description`: Human-readable, appears in summary output.
- `sizes`: Which fixture sizes to run. The runner skips sizes not listed.
- `validation`: One of `file-diff` (compare modified fixture against `expected/<size>.md`) or `report-contains` (check agent response contains expected strings defined in prompt.md frontmatter).
- `showcase`: When true, the runner saves the full JSON response from the claude CLI for every rep/size/condition. The analyzer uses these to generate narrative diffs.

## Initial Scenarios

| Scenario | Validation | Showcase | v1 Savings | Why included |
|---|---|---|---|---|
| replace-small | file-diff | no | +13–55% | Baseline surgical edit; savings scale clearly with doc size |
| replace-large | file-diff | yes | +57–69% | Best single-operation win; large content swap |
| delete-section | file-diff | no | +39–45% | Strong, consistent savings across all sizes |
| edit-and-verify | report-contains | yes | +33–52% | Multi-step workflow; shows compound advantage |

Dropped from v1: insert-section (mdedit slower), rename-heading (negligible difference), multi-section-update (validation broken), targeted-read (validation broken), build-toc (inconsistent advantage).

## Runner (`run.py`)

### Discovery

The runner scans `scenarios/*/scenario.yaml` to build the task list. No hardcoded task definitions in the runner code.

### CLI Interface

```
python3 run.py [--scenarios replace-small,delete-section]
               [--sizes small,medium,large]
               [--conditions mdedit,baseline]
               [--reps 3]
               [--model haiku]
               [--workers 5]
               [--timeout 300]
               [--dry-run]
```

All flags are optional; defaults run the full matrix.

### Agent Invocation

Each run executes:

```bash
claude -p --output-format json \
  --bare \
  --system-prompt "<system prompt content>" \
  --model <model> \
  --dangerously-skip-permissions
```

With the task prompt piped via stdin.

Key changes from v1:
- `--bare` replaces the temp-directory workaround. Strips all local config, CLAUDE.md, hooks, MCP servers.
- No need to `cwd` to a temp folder — the working directory can be a purpose-built workdir under `/tmp`.
- No need to unset `CLAUDECODE` — `--bare` handles isolation.
- Fixture is still copied to a per-run `/tmp` workdir to prevent cross-contamination on write operations.

### Environment

For the baseline condition, the mdedit binary directory is removed from PATH so the agent cannot accidentally use it. For the mdedit condition, PATH includes the binary directory.

### Placeholder Substitution

Prompts (system and task) support these placeholders:
- `{{WORKDIR}}` — the per-run temp directory
- `{{FIXTURE}}` — the fixture filename (e.g., `large.md`)
- `{{BINARY}}` — resolved path to the mdedit binary
- `{{REPORT_PATH}}` — where the agent should write its report

### Result Capture

For every run, the runner captures:
- `task`, `condition`, `size`, `rep` — matrix coordinates
- `success` — whether the claude CLI exited 0
- `correct` — whether validation passed
- `validation_reason` — why validation failed (if it did)
- `input_tokens`, `output_tokens`, `total_tokens` — from the JSON response
- `duration_s` — wall clock time
- `num_tool_calls` — count of tool_use blocks in the response

For showcase scenarios, the full JSON response is saved to `transcripts/`.

### Output

All results go into `results/run-YYYYMMDD-HHMMSS/`. The runner writes `results.json` and then calls the analyzer to generate `summary.md` and `narrative.md`.

## Analyzer (`analyze.py`)

### Summary Table (`summary.md`)

```markdown
# mdedit Benchmark Results — YYYY-MM-DD

**Median token savings: +X.X%**

## Per-Scenario Comparison

| Scenario | Size | mdedit (min/med/max) | Baseline (min/med/max) | Savings |
|---|---|---|---|---|
| replace-small | small | 1473/1579/1772 | 1651/1821/2163 | +13.3% |
| ...
```

Only includes scenarios where both conditions have at least one valid+correct run.

### Narrative Diffs (`narrative.md`)

For showcase scenarios, the analyzer reads saved transcripts and produces a side-by-side comparison:

```markdown
## replace-large / large

### Baseline (median: 11,162 tokens, 4 tool calls)

1. Read — read entire large.md (500 lines)
2. Edit — replace Implementation section (full file rewrite)
3. Read — verify the change took effect

### mdedit (median: 3,422 tokens, 1 tool call)

1. Bash — `mdedit replace large.md "Implementation" --content "..."`

**Savings: 69.3% fewer tokens**
```

The analyzer extracts tool call sequences from the transcript JSON. It summarizes each tool call as one line (tool name + brief description). It does not reproduce full file contents — just the sequence and the numbers.

### Variance

IQR/median ratio per condition, same as v1. Flags if either condition has high variance (>0.6).

### Failures

Table of failed runs with reason, same as v1. Helps diagnose validation issues.

## Validation (`validate.py`)

Two functions:

### `validate_file_diff(result_path, expected_path) -> dict`

Compares the modified fixture against the expected output after whitespace normalization. Returns `{valid, reason, diff}`. Same logic as v1's `validate_isolated`.

### `validate_report_contains(agent_output, report_path, expected_strings) -> dict`

Checks that expected strings appear in either the agent's final text output (from the JSON response) or a report file the agent wrote to `report_path`. The function checks the report file first (if it exists), then falls back to the agent's stdout text. This handles both agents that write a file and agents that just respond with text.

For edit-and-verify, the expected strings are defined in the prompt's YAML frontmatter:

```yaml
---
validation_strings:
  - "This project addresses the growing need for efficient document processing"
  - "Previous approaches relied on batch processing"
---
```

Returns `{valid, reason}`.

## System Prompts

### `system-prompts/mdedit.md`

Carried forward from v1 with minor cleanup:
- Working context block (workdir, fixture path, binary path)
- "Use mdedit for all markdown edits — do NOT use Read/Edit/Write to modify the file"
- Full mdedit command reference (addressing, content input, read commands, write commands, exit codes, output format)
- Report format instructions

### `system-prompts/baseline.md`

Carried forward from v1:
- Working context block (workdir, fixture path)
- "Use standard tools: Read, Edit, Write, Bash"
- Report format instructions

Both prompts include: "Complete the task using the fewest tool calls possible. Do NOT access the memory system or CLAUDE.md."

## Fixtures

Reused from v1 without changes:
- `small.md` — ~50 lines, simple document structure
- `medium.md` — ~190 lines, moderate nesting
- `large.md` — ~500 lines, deep nesting (H1–H5)

## Run Matrix

Default configuration: 4 scenarios x 3 sizes x 2 conditions x 3 reps = 72 runs (minus replace-large/small = 66 runs).

At ~30s per agent and 5 parallel workers, a full run takes ~7 minutes. Estimated cost at Haiku rates: ~$0.50–1.00.

## Adding a New Scenario

1. Create `scenarios/<name>/scenario.yaml` with metadata
2. Create `scenarios/<name>/prompt.md` with the task prompt
3. If using `file-diff` validation, create `scenarios/<name>/expected/<size>.md` for each size
4. If using `report-contains` validation, add `validation_strings` to prompt.md frontmatter
5. Run `python3 run.py --scenarios <name>` to test

No changes to runner, analyzer, or validation code required.
