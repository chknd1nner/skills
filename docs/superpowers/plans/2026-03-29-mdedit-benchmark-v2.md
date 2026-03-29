# mdedit Benchmark Suite v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lean, modular benchmark suite that measures mdedit's token savings vs standard Claude Code tools, with captured transcripts for narrative comparison.

**Architecture:** Auto-discovering runner scans `scenarios/` directories, dispatches headless `claude -p --bare` agents in parallel, validates correctness, and produces both a summary table and narrative diffs from showcase transcripts. New scenarios are added by dropping a folder — no code changes.

**Tech Stack:** Python 3, PyYAML, claude CLI (`--bare` mode), ThreadPoolExecutor

**Spec:** `docs/superpowers/specs/2026-03-29-mdedit-benchmark-v2-design.md`

---

## File Structure

```
tests/mdedit/benchmarks-v2/
├── run.py                  # runner: discovery, matrix, agent dispatch, result capture
├── analyze.py              # reads results.json + transcripts, produces summary.md + narrative.md
├── validate.py             # two validation functions: file-diff, report-contains
├── fixtures/               # copied from v1 without changes
│   ├── small.md
│   ├── medium.md
│   └── large.md
├── system-prompts/
│   ├── mdedit.md           # mdedit command reference + agent rules
│   └── baseline.md         # standard tools + agent rules
├── scenarios/
│   ├── replace-small/
│   │   ├── scenario.yaml
│   │   ├── prompt.md
│   │   └── expected/       # small.md, medium.md, large.md
│   ├── replace-large/
│   │   ├── scenario.yaml
│   │   ├── prompt.md
│   │   └── expected/       # medium.md, large.md (no small)
│   ├── delete-section/
│   │   ├── scenario.yaml
│   │   ├── prompt.md
│   │   └── expected/       # small.md, medium.md, large.md
│   └── edit-and-verify/
│       ├── scenario.yaml
│       └── prompt.md       # has validation_strings in frontmatter
├── results/
│   └── .gitkeep
└── .gitignore
```

---

### Task 1: Scaffold directory structure and copy fixtures

**Files:**
- Create: `tests/mdedit/benchmarks-v2/fixtures/small.md`
- Create: `tests/mdedit/benchmarks-v2/fixtures/medium.md`
- Create: `tests/mdedit/benchmarks-v2/fixtures/large.md`
- Create: `tests/mdedit/benchmarks-v2/results/.gitkeep`
- Create: `tests/mdedit/benchmarks-v2/.gitignore`

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p tests/mdedit/benchmarks-v2/{fixtures,system-prompts,scenarios,results}
```

- [ ] **Step 2: Copy fixtures from v1**

```bash
cp tests/mdedit/benchmarks/fixtures/small.md tests/mdedit/benchmarks-v2/fixtures/
cp tests/mdedit/benchmarks/fixtures/medium.md tests/mdedit/benchmarks-v2/fixtures/
cp tests/mdedit/benchmarks/fixtures/large.md tests/mdedit/benchmarks-v2/fixtures/
```

- [ ] **Step 3: Create .gitignore**

Create `tests/mdedit/benchmarks-v2/.gitignore`:

```
results/*/
!results/.gitkeep
__pycache__/
```

- [ ] **Step 4: Create results/.gitkeep**

```bash
touch tests/mdedit/benchmarks-v2/results/.gitkeep
```

- [ ] **Step 5: Commit**

```bash
git add tests/mdedit/benchmarks-v2/
git commit -m "chore(benchmark-v2): scaffold directory structure and copy fixtures"
```

---

### Task 2: Create system prompts

**Files:**
- Create: `tests/mdedit/benchmarks-v2/system-prompts/mdedit.md`
- Create: `tests/mdedit/benchmarks-v2/system-prompts/baseline.md`

- [ ] **Step 1: Create the mdedit system prompt**

Create `tests/mdedit/benchmarks-v2/system-prompts/mdedit.md`. Port from v1 (`tests/mdedit/benchmarks/prompts/system-mdedit.md`) with these changes:
- Keep the full mdedit command reference (section addressing, content input, read commands, write commands, exit codes, write output format)
- Keep the working context block with `{{WORKDIR}}`, `{{FIXTURE}}`, `{{BINARY}}` placeholders
- Keep "Complete the task using the fewest tool calls possible"
- Keep "Use mdedit for all markdown edits — do NOT use Read/Edit/Write tools to modify the file directly"
- Add "Do NOT access the memory system or CLAUDE.md" (already present)
- Keep the report format section with `{{REPORT_PATH}}`

The content is identical to v1's `system-mdedit.md` — no structural changes needed.

````markdown
You are a benchmark agent. Complete the editing task described in the user prompt.

## Working Context

- Working directory: {{WORKDIR}}
- File to edit: {{WORKDIR}}/{{FIXTURE}}
- mdedit binary: {{BINARY}}

## Rules

- Complete the task using the fewest tool calls possible.
- Use mdedit for all markdown edits — do NOT use Read/Edit/Write tools to modify the file directly.
- Do NOT access the memory system or CLAUDE.md.

---

## mdedit Command Reference

### Section Addressing

Sections are identified by heading text. Addressing syntax:

| Pattern | Meaning |
|---|---|
| `Background` | Any heading whose text is "Background" (case-sensitive, exact match) |
| `## Background` | H2 heading with text "Background" (level-qualified) |
| `Background/Prior Work` | Child section "Prior Work" inside "Background" |
| `_preamble` | Content before the first heading (after frontmatter) |

- **Ambiguous match** (multiple headings match): exit code 2
- **No match**: exit code 1; fuzzy suggestions printed to stderr

### Content Input

Write commands accept content via:

- `--content <text>` — inline string
- `--from-file <path>` — read from file
- stdin — when stdin is not a TTY (e.g. piped input)

---

### Read Commands

```
mdedit outline <file> [--max-depth N]
```
Print heading structure with word counts and line ranges.

```
mdedit extract <file> <section> [--no-children] [--to-file <path>]
```
Print section content. `--no-children` omits child sections. `--to-file` writes output to a file instead of stdout.

```
mdedit search <file> <query> [--case-sensitive]
```
Find all sections whose content contains the query string.

```
mdedit stats <file>
```
Print word and line counts per section.

```
mdedit validate <file>
```
Report heading structure problems (skipped levels, duplicate headings, etc.).

```
mdedit frontmatter <file>
```
Print all frontmatter fields.

```
mdedit frontmatter get <file> <key>
```
Print the value of a single frontmatter field.

---

### Write Commands

All write commands support `--dry-run` to preview changes without modifying the file.

```
mdedit replace <file> <section> [--content <text>] [--from-file <path>] [--preserve-children]
```
Replace the body of a section. `--preserve-children` keeps child sections intact while replacing only the section's own content.

Output:
```
REPLACED: "## Name" (was N lines → now M lines)
```
Followed by neighborhood context (see Output Format below).

```
mdedit append <file> <section> [--content <text>] [--from-file <path>]
```
Add content to the end of a section, before any child headings.

Output:
```
APPENDED: N lines to "## Name"
```

```
mdedit prepend <file> <section> [--content <text>] [--from-file <path>]
```
Add content to the start of a section, immediately after the heading line.

Output:
```
PREPENDED: N lines to "## Name"
```

```
mdedit insert <file> --after|--before <section> --heading <heading> [--content <text>] [--from-file <path>]
```
Insert a new section at the specified position relative to an existing section.

Output:
```
INSERTED: "## Name" (N lines) after "## Other"
INSERTED: "## Name" (N lines) before "## Other"
```

```
mdedit delete <file> <section>
```
Remove a section and all its children.

Output:
```
DELETED: "## Name" (N lines removed)
```

```
mdedit rename <file> <section> <new-name>
```
Change a heading's text. Heading level is preserved.

Output:
```
RENAMED: "## Old" → "## New"
```

```
mdedit frontmatter set <file> <key> <value>
```
Set a frontmatter field (creates field if absent).

```
mdedit frontmatter delete <file> <key>
```
Remove a frontmatter field.

---

### Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Section not found |
| 2 | Ambiguous section match |
| 3 | File error (not found, unreadable, etc.) |
| 4 | No content provided for a write command |
| 5 | Validation issues detected |
| 10 | No-op (command succeeded but made no change) |

---

### Write Output Format

After every successful write, mdedit prints a summary line followed by neighborhood context:

```
REPLACED: "## Name" (was 4 lines → now 6 lines)

  ## Previous Section
  [content]

→ ## Name
  [first line of new content]
  [N more lines]
  [last line of new content]

  ## Next Section
  [content]
```

- The changed section is marked with `→`.
- For long sections, middle lines are abbreviated as `[N more lines]`.
- First and last lines of the section are always shown.

---

## Report Format

After completing the task, write a report to `{{REPORT_PATH}}` with the following sections:

```markdown
## Task

[One sentence describing what was asked.]

## Steps

[Numbered list of each mdedit command run, including the full command and a one-line note on what it did.]

## Verification

[How you confirmed the edit was correct — e.g., the mdedit extract output or exit code observed.]
```
```

- [ ] **Step 2: Create the baseline system prompt**

Create `tests/mdedit/benchmarks-v2/system-prompts/baseline.md`:

```markdown
You are a benchmark agent. Complete the editing task described in the user prompt.

## Working Context

- Working directory: {{WORKDIR}}
- File to edit: {{WORKDIR}}/{{FIXTURE}}

## Rules

- Complete the task using the fewest tool calls possible.
- Use standard tools: Read, Edit, Write, Bash.
- Do NOT access the memory system or CLAUDE.md.

---

## Report Format

After completing the task, write a report to `{{REPORT_PATH}}` with the following sections:

```markdown
## Task

[One sentence describing what was asked.]

## Steps

[Numbered list of each action taken, including the tool used and a one-line note on what it did.]

## Verification

[How you confirmed the edit was correct — e.g., the file content observed after editing.]
```
````

- [ ] **Step 3: Commit**

```bash
git add tests/mdedit/benchmarks-v2/system-prompts/
git commit -m "feat(benchmark-v2): add system prompts for mdedit and baseline conditions"
```

---

### Task 3: Create scenario definitions and prompts

**Files:**
- Create: `tests/mdedit/benchmarks-v2/scenarios/replace-small/scenario.yaml`
- Create: `tests/mdedit/benchmarks-v2/scenarios/replace-small/prompt.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/replace-large/scenario.yaml`
- Create: `tests/mdedit/benchmarks-v2/scenarios/replace-large/prompt.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/delete-section/scenario.yaml`
- Create: `tests/mdedit/benchmarks-v2/scenarios/delete-section/prompt.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/edit-and-verify/scenario.yaml`
- Create: `tests/mdedit/benchmarks-v2/scenarios/edit-and-verify/prompt.md`

- [ ] **Step 1: Create replace-small scenario**

Create `tests/mdedit/benchmarks-v2/scenarios/replace-small/scenario.yaml`:

```yaml
name: replace-small
description: Replace a small section (~5 lines) with new content
sizes: [small, medium, large]
validation: file-diff
showcase: false
```

Create `tests/mdedit/benchmarks-v2/scenarios/replace-small/prompt.md` (ported from v1):

```markdown
Replace the content of the "Conclusion" section with the following text:

This project demonstrated significant improvements in processing speed
and memory efficiency. Future work will focus on scaling to larger
datasets and improving the user interface.

Do not modify any other section. The heading "## Conclusion" must remain.
```

- [ ] **Step 2: Create replace-large scenario**

Create `tests/mdedit/benchmarks-v2/scenarios/replace-large/scenario.yaml`:

```yaml
name: replace-large
description: Replace a large section (40+ lines) with new content
sizes: [medium, large]
validation: file-diff
showcase: true
```

Create `tests/mdedit/benchmarks-v2/scenarios/replace-large/prompt.md` (ported from v1):

```markdown
Replace the entire content of the "Implementation" section (including all subsections) with the following text:

### Architecture Overview

The rewritten implementation adopts an event-driven architecture to decouple components and improve scalability. Core events flow through a central message broker, allowing services to subscribe selectively and process asynchronously. This design eliminates tight coupling and enables independent deployment of service modules.

### Configuration Management

Configuration is now declarative via YAML, allowing operators to tune behavior without code changes. The configuration schema validates at startup, catching errors early. Environment variable substitution enables environment-specific overrides while maintaining a single canonical configuration file.

### Event Processing Pipeline

Events arrive at the ingestion layer where they are validated against schemas. Valid events proceed through a series of transformation stages—enrichment, deduplication, and aggregation. Each stage is independently scalable; high-volume event types can be processed on dedicated worker pools while others share capacity.

### Error Handling and Resilience

The system employs circuit breakers to prevent cascade failures. When a downstream service becomes unavailable, the circuit opens and requests are rejected fast rather than timing out. Once the service recovers, the circuit gradually reopens through a half-open state, verifying health before resuming normal traffic flow.

Transient errors trigger exponential backoff with jitter, reducing thundering herd problems during recovery. Dead-letter queues capture messages that cannot be processed, enabling later investigation and replay without losing data.

### Observability

Comprehensive logging and metrics instrumentation provide visibility into system behavior. Structured logging enables easy filtering and correlation of related events. Metrics cover request latencies, error rates, queue depths, and circuit breaker state—all essential for production monitoring.

Distributed tracing follows request flows across service boundaries, critical for understanding performance characteristics in the multi-service architecture. All tracing and metrics integrate with standard monitoring platforms.

### Deployment and Operations

The service is containerized with clear resource requirements. Kubernetes manifests define pod specifications, service configuration, and horizontal scaling policies. Blue-green deployments enable zero-downtime updates. Readiness and liveness probes ensure only healthy instances receive traffic.

Database migrations run in a separate init container before application startup, ensuring schema consistency. Configuration is mounted from ConfigMaps and Secrets, keeping sensitive data separate from container images.

Do not modify any other section. The heading "## Implementation" must remain.
```

- [ ] **Step 3: Create delete-section scenario**

Create `tests/mdedit/benchmarks-v2/scenarios/delete-section/scenario.yaml`:

```yaml
name: delete-section
description: Delete a section and all its content
sizes: [small, medium, large]
validation: file-diff
showcase: false
```

Create `tests/mdedit/benchmarks-v2/scenarios/delete-section/prompt.md` (ported from v1):

```markdown
Delete the "## References" section and all its content from the document.
No other sections should be modified.
```

- [ ] **Step 4: Create edit-and-verify scenario**

Create `tests/mdedit/benchmarks-v2/scenarios/edit-and-verify/scenario.yaml`:

```yaml
name: edit-and-verify
description: Edit a section and verify the change by reading back
sizes: [small, medium, large]
validation: report-contains
showcase: true
```

Create `tests/mdedit/benchmarks-v2/scenarios/edit-and-verify/prompt.md` (ported from v1). Note the YAML frontmatter with `validation_strings`:

```markdown
---
validation_strings:
  - "This project addresses the growing need for efficient document processing"
  - "Previous approaches relied on batch processing"
---

Replace the content of the "Background" section with the following text:

This project addresses the growing need for efficient document processing
in large-scale systems. Previous approaches relied on batch processing,
which introduced unacceptable latency for real-time applications.

After making the replacement, confirm back to me exactly what the
"Background" section now contains. Show me the full section content.
```

- [ ] **Step 5: Commit**

```bash
git add tests/mdedit/benchmarks-v2/scenarios/
git commit -m "feat(benchmark-v2): add 4 scenario definitions and prompts"
```

---

### Task 4: Create expected output files

**Files:**
- Create: `tests/mdedit/benchmarks-v2/scenarios/replace-small/expected/small.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/replace-small/expected/medium.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/replace-small/expected/large.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/replace-large/expected/medium.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/replace-large/expected/large.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/delete-section/expected/small.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/delete-section/expected/medium.md`
- Create: `tests/mdedit/benchmarks-v2/scenarios/delete-section/expected/large.md`

These are hand-authored expected outputs — the fixture with the specified edit applied. They must be produced by actually running the edits against the fixtures manually (using mdedit or a text editor) and verifying the result.

- [ ] **Step 1: Generate expected outputs for replace-small**

For each size (small, medium, large), take the corresponding fixture file and replace the content of the "## Conclusion" section with:

```
This project demonstrated significant improvements in processing speed
and memory efficiency. Future work will focus on scaling to larger
datasets and improving the user interface.
```

Keep the heading `## Conclusion` and all other sections unchanged.

The most reliable way to generate these: use the mdedit binary itself.

```bash
MDEDIT=claude-code-only/mdedit/target/release/mdedit

mkdir -p tests/mdedit/benchmarks-v2/scenarios/replace-small/expected

for size in small medium large; do
  cp tests/mdedit/benchmarks-v2/fixtures/${size}.md /tmp/mdedit-gen-${size}.md
  $MDEDIT replace /tmp/mdedit-gen-${size}.md "Conclusion" --content "This project demonstrated significant improvements in processing speed
and memory efficiency. Future work will focus on scaling to larger
datasets and improving the user interface."
  cp /tmp/mdedit-gen-${size}.md tests/mdedit/benchmarks-v2/scenarios/replace-small/expected/${size}.md
done
```

Verify each file: the Conclusion section should contain exactly the replacement text, all other sections unchanged.

- [ ] **Step 2: Generate expected outputs for replace-large**

For medium and large (not small — excluded by scenario.yaml), replace the entire "## Implementation" section content with the long replacement text from the prompt.

```bash
mkdir -p tests/mdedit/benchmarks-v2/scenarios/replace-large/expected

for size in medium large; do
  cp tests/mdedit/benchmarks-v2/fixtures/${size}.md /tmp/mdedit-gen-${size}.md
  $MDEDIT replace /tmp/mdedit-gen-${size}.md "Implementation" --from-file tests/mdedit/benchmarks-v2/scenarios/replace-large/prompt-content.tmp
  cp /tmp/mdedit-gen-${size}.md tests/mdedit/benchmarks-v2/scenarios/replace-large/expected/${size}.md
done
```

Note: You'll need to extract the replacement content from `prompt.md` (everything between the first blank line after the first sentence and the "Do not modify" line) into a temp file first. Alternatively, use v1's existing expected files if they match:

```bash
cp tests/mdedit/benchmarks/expected/medium/replace-large.md tests/mdedit/benchmarks-v2/scenarios/replace-large/expected/medium.md
cp tests/mdedit/benchmarks/expected/large/replace-large.md tests/mdedit/benchmarks-v2/scenarios/replace-large/expected/large.md
```

Verify: diff against v1 expected files to confirm they match.

- [ ] **Step 3: Generate expected outputs for delete-section**

For each size, delete the "## References" section.

```bash
mkdir -p tests/mdedit/benchmarks-v2/scenarios/delete-section/expected

for size in small medium large; do
  cp tests/mdedit/benchmarks-v2/fixtures/${size}.md /tmp/mdedit-gen-${size}.md
  $MDEDIT delete /tmp/mdedit-gen-${size}.md "References"
  cp /tmp/mdedit-gen-${size}.md tests/mdedit/benchmarks-v2/scenarios/delete-section/expected/${size}.md
done
```

Alternatively, copy from v1:

```bash
for size in small medium large; do
  cp tests/mdedit/benchmarks/expected/${size}/delete-section.md tests/mdedit/benchmarks-v2/scenarios/delete-section/expected/${size}.md
done
```

- [ ] **Step 4: Verify all expected files exist and are non-empty**

```bash
find tests/mdedit/benchmarks-v2/scenarios/*/expected -name "*.md" -exec wc -l {} \;
```

Expected: 8 files, all with line counts close to their source fixture (minus/plus the edit delta).

- [ ] **Step 5: Commit**

```bash
git add tests/mdedit/benchmarks-v2/scenarios/*/expected/
git commit -m "feat(benchmark-v2): add expected output files for file-diff validation"
```

---

### Task 5: Write validate.py

**Files:**
- Create: `tests/mdedit/benchmarks-v2/validate.py`

- [ ] **Step 1: Write validate.py**

Create `tests/mdedit/benchmarks-v2/validate.py`:

```python
"""
Correctness validation for benchmark runs.

Two validation modes:
- file-diff: compare modified fixture against expected output
- report-contains: check agent response contains expected strings
"""

import difflib
import re
from pathlib import Path


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace for comparison.

    Strips trailing whitespace per line, collapses multiple blank lines
    to one, and ensures a single trailing newline.
    """
    lines = [line.rstrip() for line in text.split('\n')]
    normalized = []
    prev_blank = False
    for line in lines:
        is_blank = line == ''
        if is_blank and prev_blank:
            continue
        normalized.append(line)
        prev_blank = is_blank
    result = '\n'.join(normalized).rstrip('\n')
    return result + '\n' if result else '\n'


def validate_file_diff(result_path: Path, expected_path: Path) -> dict:
    """
    Compare modified fixture against expected output after whitespace
    normalization.

    Args:
        result_path: Path to the agent's modified file
        expected_path: Path to the hand-authored expected output

    Returns:
        dict with 'valid' (bool), 'reason' (str), 'diff' (str)
    """
    try:
        result_text = result_path.read_text()
        expected_text = expected_path.read_text()
    except FileNotFoundError as e:
        return {'valid': False, 'reason': f'File not found: {e}', 'diff': ''}

    norm_result = normalize_whitespace(result_text)
    norm_expected = normalize_whitespace(expected_text)

    if norm_result == norm_expected:
        return {
            'valid': True,
            'reason': 'Output matches expected',
            'diff': '',
        }

    diff = ''.join(difflib.unified_diff(
        norm_expected.splitlines(keepends=True),
        norm_result.splitlines(keepends=True),
        fromfile='expected',
        tofile='result',
    ))
    return {
        'valid': False,
        'reason': 'Output does not match expected',
        'diff': diff,
    }


def validate_report_contains(
    agent_output: str,
    report_path: Path,
    expected_strings: list[str],
) -> dict:
    """
    Check that expected strings appear in the agent's output.

    Checks the report file first (if it exists), then falls back to the
    agent's stdout text.

    Args:
        agent_output: The agent's final text response
        report_path: Path where the agent may have written a report file
        expected_strings: List of strings that must all appear

    Returns:
        dict with 'valid' (bool), 'reason' (str)
    """
    # Build the text to search: report file takes priority
    search_text = ''
    if report_path.exists():
        search_text = report_path.read_text()
    if not search_text.strip():
        search_text = agent_output

    normalized = normalize_whitespace(search_text)

    missing = []
    for s in expected_strings:
        norm_s = normalize_whitespace(s).strip()
        if norm_s not in normalized:
            missing.append(s[:80])

    if not missing:
        return {'valid': True, 'reason': 'All expected strings found'}

    return {
        'valid': False,
        'reason': f'Missing: {", ".join(missing)}',
    }
```

- [ ] **Step 2: Smoke test validate.py**

```bash
cd tests/mdedit/benchmarks-v2
python3 -c "
from validate import validate_file_diff, validate_report_contains
from pathlib import Path

# file-diff: identical files should pass
r = validate_file_diff(Path('fixtures/small.md'), Path('fixtures/small.md'))
assert r['valid'] is True, f'Expected valid, got: {r}'

# report-contains: present string should pass
r = validate_report_contains('hello world', Path('/nonexistent'), ['hello'])
assert r['valid'] is True, f'Expected valid, got: {r}'

# report-contains: missing string should fail
r = validate_report_contains('hello world', Path('/nonexistent'), ['goodbye'])
assert r['valid'] is False, f'Expected invalid, got: {r}'

print('All smoke tests passed')
"
```

Expected: `All smoke tests passed`

- [ ] **Step 3: Commit**

```bash
git add tests/mdedit/benchmarks-v2/validate.py
git commit -m "feat(benchmark-v2): add validation module (file-diff + report-contains)"
```

---

### Task 6: Write run.py

**Files:**
- Create: `tests/mdedit/benchmarks-v2/run.py`

This is the largest task. The runner has these responsibilities: discover scenarios, build the run matrix, set up per-run workdirs, invoke claude CLI agents, parse results, validate correctness, save transcripts for showcase scenarios, and write results.json.

- [ ] **Step 1: Write run.py**

Create `tests/mdedit/benchmarks-v2/run.py`:

```python
#!/usr/bin/env python3
"""
Benchmark runner for mdedit v2 — measures token efficiency vs baseline.

Auto-discovers scenarios from scenarios/*/scenario.yaml, dispatches
headless claude CLI agents with --bare mode, validates correctness,
and saves structured results.

Usage:
    python3 run.py [--scenarios replace-small,delete-section]
                   [--sizes small,medium,large]
                   [--conditions mdedit,baseline]
                   [--reps 3] [--model haiku]
                   [--workers 15] [--timeout 300] [--dry-run]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from validate import validate_file_diff, validate_report_contains

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
FIXTURES_DIR = SCRIPT_DIR / 'fixtures'
SYSTEM_PROMPTS_DIR = SCRIPT_DIR / 'system-prompts'
SCENARIOS_DIR = SCRIPT_DIR / 'scenarios'
RESULTS_DIR = SCRIPT_DIR / 'results'
# Candidate paths for mdedit binary, checked in order
MDEDIT_CANDIDATES = [
    SCRIPT_DIR.parent.parent.parent / 'claude-code-only' / 'mdedit' / 'target' / 'release' / 'mdedit',
    Path.home() / '.cargo' / 'bin' / 'mdedit',
]

ALL_SIZES = ['small', 'medium', 'large']
ALL_CONDITIONS = ['mdedit', 'baseline']


# ---------------------------------------------------------------------------
# Scenario discovery
# ---------------------------------------------------------------------------

def discover_scenarios(filter_names: list[str] | None = None) -> list[dict]:
    """
    Scan scenarios/*/scenario.yaml and return list of scenario dicts.

    Each dict has: name, description, sizes, validation, showcase, dir.
    """
    scenarios = []
    for yaml_path in sorted(SCENARIOS_DIR.glob('*/scenario.yaml')):
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
        config['dir'] = yaml_path.parent
        scenarios.append(config)

    if filter_names:
        scenarios = [s for s in scenarios if s['name'] in filter_names]

    return scenarios


def load_prompt_frontmatter(prompt_path: Path) -> dict:
    """
    Extract YAML frontmatter from a prompt file.

    Returns empty dict if no frontmatter present.
    """
    text = prompt_path.read_text()
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def load_prompt_body(prompt_path: Path) -> str:
    """
    Read prompt file, stripping YAML frontmatter if present.
    """
    text = prompt_path.read_text()
    match = re.match(r'^---\s*\n.*?\n---\s*\n', text, re.DOTALL)
    if match:
        return text[match.end():]
    return text


# ---------------------------------------------------------------------------
# Binary verification
# ---------------------------------------------------------------------------

def verify_binary() -> Path | None:
    """
    Find mdedit binary. Tries candidate paths, then falls back to
    `which mdedit`. Returns resolved absolute Path or None.
    """
    # Try candidate paths in order
    for candidate in MDEDIT_CANDIDATES:
        if candidate.exists():
            result = subprocess.run(
                [str(candidate), '--help'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                print(f'Found mdedit: {candidate.resolve()}')
                return candidate.resolve()

    # Fallback: check if mdedit is anywhere on PATH
    which = shutil.which('mdedit')
    if which:
        path = Path(which).resolve()
        print(f'Found mdedit on PATH: {path}')
        return path

    print('WARNING: mdedit binary not found')
    print('  Checked:', [str(c) for c in MDEDIT_CANDIDATES])
    print('  Also ran: which mdedit (not found)')
    return None


# ---------------------------------------------------------------------------
# Per-run execution
# ---------------------------------------------------------------------------

def setup_workdir(scenario_name: str, condition: str, size: str, rep: int) -> Path:
    """Create /tmp workdir with a copy of the fixture."""
    ts = int(time.time() * 1000)
    workdir = Path(f'/tmp/mdedit-v2-{scenario_name}-{condition}-{size}-r{rep}-{ts}')
    workdir.mkdir(parents=True, exist_ok=True)
    fixture_src = FIXTURES_DIR / f'{size}.md'
    if fixture_src.exists():
        shutil.copy2(fixture_src, workdir / f'{size}.md')
    return workdir


def substitute_placeholders(
    text: str, binary: Path | None, workdir: Path,
    fixture_name: str, report_path: Path,
) -> str:
    """Replace {{WORKDIR}}, {{FIXTURE}}, {{BINARY}}, {{REPORT_PATH}}."""
    text = text.replace('{{WORKDIR}}', str(workdir))
    text = text.replace('{{FIXTURE}}', fixture_name)
    text = text.replace('{{BINARY}}', str(binary) if binary else '')
    text = text.replace('{{REPORT_PATH}}', str(report_path))
    return text


def parse_token_usage(stdout: str) -> dict:
    """
    Parse token usage from claude CLI JSON output.

    Scans the JSON structure for input_tokens/output_tokens and counts
    tool_use blocks.
    """
    try:
        data = json.loads(stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return {
            'input_tokens': 0, 'output_tokens': 0,
            'total_tokens': 0, 'num_tool_calls': 0,
        }

    input_tokens = 0
    output_tokens = 0
    num_tool_calls = 0

    # Try known locations
    for path in [lambda d: d['result']['usage'], lambda d: d['usage']]:
        try:
            usage = path(data)
            if isinstance(usage, dict):
                input_tokens = usage.get('input_tokens', 0) or 0
                output_tokens = usage.get('output_tokens', 0) or 0
                break
        except (KeyError, TypeError):
            continue

    # Fallback: scan the whole structure
    if input_tokens == 0 and output_tokens == 0:
        def _scan(obj):
            nonlocal input_tokens, output_tokens
            if isinstance(obj, dict):
                if 'input_tokens' in obj and input_tokens == 0:
                    input_tokens = obj['input_tokens'] or 0
                if 'output_tokens' in obj and output_tokens == 0:
                    output_tokens = obj['output_tokens'] or 0
                for v in obj.values():
                    _scan(v)
            elif isinstance(obj, list):
                for item in obj:
                    _scan(item)
        _scan(data)

    # Count tool_use blocks
    try:
        messages = data.get('messages') or []
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get('content') or []
                if isinstance(content, list):
                    num_tool_calls += sum(
                        1 for b in content
                        if isinstance(b, dict) and b.get('type') == 'tool_use'
                    )
    except Exception:
        pass

    return {
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
        'num_tool_calls': num_tool_calls,
    }


def extract_agent_text(stdout: str) -> str:
    """Extract the agent's final text response from JSON output."""
    try:
        data = json.loads(stdout.strip())
        text = (
            data.get('result', '') or
            data.get('text', '') or
            data.get('content', '') or
            ''
        )
        if isinstance(text, list):
            text = ' '.join(
                b.get('text', '') for b in text if isinstance(b, dict)
            )
        return text
    except Exception:
        return stdout


def run_single(
    scenario: dict, condition: str, size: str, rep: int,
    binary: Path | None, model: str, timeout: int,
    run_dir: Path,
) -> dict:
    """Execute one benchmark run and return a structured result dict."""
    name = scenario['name']
    fixture_name = f'{size}.md'
    workdir = setup_workdir(name, condition, size, rep)
    report_path = workdir / f'report-{name}-{condition}.md'

    # Load system prompt
    system_prompt_path = SYSTEM_PROMPTS_DIR / f'{condition}.md'
    system_prompt = substitute_placeholders(
        system_prompt_path.read_text(), binary, workdir, fixture_name, report_path,
    )

    # Load task prompt (body only, no frontmatter)
    prompt_path = scenario['dir'] / 'prompt.md'
    user_prompt = substitute_placeholders(
        load_prompt_body(prompt_path), binary, workdir, fixture_name, report_path,
    )

    # Build command
    cmd = [
        'claude', '-p',
        '--output-format', 'json',
        '--bare',
        '--system-prompt', system_prompt,
        '--model', model,
        '--dangerously-skip-permissions',
    ]

    # Build environment
    env = os.environ.copy()
    if binary:
        binary_dir = str(binary.parent)
        if condition == 'mdedit':
            # Ensure mdedit is on PATH even in restricted terminal environments
            if binary_dir not in env.get('PATH', '').split(':'):
                env['PATH'] = binary_dir + ':' + env.get('PATH', '')
        elif condition == 'baseline':
            # Remove mdedit from PATH so baseline can't accidentally use it
            path_parts = [p for p in env.get('PATH', '').split(':') if p != binary_dir]
            env['PATH'] = ':'.join(path_parts)

    start = time.time()

    try:
        proc = subprocess.run(
            cmd, input=user_prompt,
            capture_output=True, text=True,
            timeout=timeout, env=env, cwd=str(workdir),
        )
        duration = time.time() - start

        if proc.returncode != 0:
            return _error_result(
                name, condition, size, rep, workdir,
                f'claude exited {proc.returncode}: {proc.stderr[:500]}',
                duration,
            )

        stdout = proc.stdout
        tokens = parse_token_usage(stdout)
        agent_text = extract_agent_text(stdout)

        # Save transcript for showcase scenarios
        if scenario.get('showcase'):
            transcripts_dir = run_dir / 'transcripts'
            transcripts_dir.mkdir(parents=True, exist_ok=True)
            transcript_file = transcripts_dir / f'{name}-{condition}-{size}-rep{rep}.json'
            transcript_file.write_text(stdout)

        # Validate
        validation = scenario.get('validation', 'file-diff')
        if validation == 'file-diff':
            result_file = workdir / fixture_name
            expected_file = scenario['dir'] / 'expected' / f'{size}.md'
            val = validate_file_diff(result_file, expected_file)
        elif validation == 'report-contains':
            frontmatter = load_prompt_frontmatter(scenario['dir'] / 'prompt.md')
            expected_strings = frontmatter.get('validation_strings', [])
            val = validate_report_contains(agent_text, report_path, expected_strings)
        else:
            val = {'valid': None, 'reason': f'Unknown validation: {validation}'}

        return {
            'task': name,
            'condition': condition,
            'size': size,
            'rep': rep,
            'success': True,
            'correct': val.get('valid') is True,
            'validation_reason': val.get('reason', ''),
            'error': '',
            'input_tokens': tokens['input_tokens'],
            'output_tokens': tokens['output_tokens'],
            'total_tokens': tokens['total_tokens'],
            'num_tool_calls': tokens['num_tool_calls'],
            'duration_s': duration,
            'workdir': str(workdir),
        }

    except subprocess.TimeoutExpired:
        return _error_result(
            name, condition, size, rep, workdir,
            f'Timeout ({timeout}s)', time.time() - start,
        )
    except Exception as exc:
        return _error_result(
            name, condition, size, rep, workdir,
            str(exc), time.time() - start,
        )


def _error_result(
    task: str, condition: str, size: str, rep: int,
    workdir: Path, error: str, duration: float = 0.0,
) -> dict:
    """Build a failed-run result dict."""
    return {
        'task': task,
        'condition': condition,
        'size': size,
        'rep': rep,
        'success': False,
        'correct': False,
        'validation_reason': '',
        'error': error,
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'num_tool_calls': 0,
        'duration_s': duration,
        'workdir': str(workdir),
    }


# ---------------------------------------------------------------------------
# Matrix + orchestration
# ---------------------------------------------------------------------------

def build_matrix(
    scenarios: list[dict], sizes: list[str],
    conditions: list[str], reps: int,
) -> list[tuple]:
    """Build list of (scenario, size, condition, rep) runs."""
    matrix = []
    for scenario in scenarios:
        for size in sizes:
            if size not in scenario.get('sizes', ALL_SIZES):
                continue
            for condition in conditions:
                for rep in range(1, reps + 1):
                    matrix.append((scenario, size, condition, rep))
    return matrix


def main():
    parser = argparse.ArgumentParser(
        description='Run mdedit v2 benchmarks: mdedit vs baseline token efficiency',
    )
    parser.add_argument('--scenarios', type=str, default=None,
                        help='Comma-separated scenario names (default: all)')
    parser.add_argument('--sizes', type=str, default=None,
                        help='Comma-separated sizes (default: small,medium,large)')
    parser.add_argument('--conditions', type=str, default=None,
                        help='Comma-separated conditions (default: mdedit,baseline)')
    parser.add_argument('--reps', type=int, default=3,
                        help='Repetitions per cell (default: 3)')
    parser.add_argument('--model', type=str, default='haiku',
                        help='Claude model (default: haiku)')
    parser.add_argument('--workers', type=int, default=15,
                        help='Parallel workers (default: 15)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='Timeout per agent in seconds (default: 300)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would run without executing')
    args = parser.parse_args()

    # Discover scenarios
    filter_names = [s.strip() for s in args.scenarios.split(',')] if args.scenarios else None
    scenarios = discover_scenarios(filter_names)
    if not scenarios:
        print('ERROR: No scenarios found')
        sys.exit(1)

    sizes = [s.strip() for s in args.sizes.split(',')] if args.sizes else ALL_SIZES
    conditions = [c.strip() for c in args.conditions.split(',')] if args.conditions else ALL_CONDITIONS

    # Verify binary
    binary = verify_binary()

    # Build matrix
    matrix = build_matrix(scenarios, sizes, conditions, args.reps)
    total = len(matrix)

    print(f'Scenarios: {[s["name"] for s in scenarios]}')
    print(f'Sizes: {sizes} | Conditions: {conditions} | Reps: {args.reps}')
    print(f'Total runs: {total} | Workers: {args.workers} | Model: {args.model}')
    print(f'Binary: {binary or "NOT FOUND"}')

    if args.dry_run:
        print(f'\n[DRY RUN] Would execute {total} runs:\n')
        for i, (scenario, size, condition, rep) in enumerate(matrix, 1):
            sc = '★' if scenario.get('showcase') else ' '
            print(f'  {i:3d}. {scenario["name"]:20s}  {size:8s}  {condition:10s}  rep={rep}  {sc}')
        return

    # Create results directory
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    run_dir = RESULTS_DIR / f'run-{timestamp}'
    run_dir.mkdir(parents=True, exist_ok=True)

    # Execute
    results = [None] * total
    completed = 0

    def _run_one(idx_and_item):
        idx, (scenario, size, condition, rep) = idx_and_item
        return idx, run_single(
            scenario, condition, size, rep,
            binary, args.model, args.timeout, run_dir,
        )

    print(f'\nRunning {total} runs (workers={args.workers})...\n')

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for i, item in enumerate(matrix):
            future = executor.submit(_run_one, (i, item))
            futures[future] = i

        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result
            completed += 1
            status = '+' if result['correct'] else ('!' if result['success'] else 'X')
            print(
                f'  [{status}] [{completed:3d}/{total}] '
                f'{result["task"]:20s}  {result["size"]:8s}  {result["condition"]:10s}  '
                f'rep={result["rep"]}  tokens={result["total_tokens"]}  '
                f'({result["duration_s"]:.0f}s)',
                flush=True,
            )

    # Save results
    results_path = run_dir / 'results.json'
    results_path.write_text(json.dumps(results, indent=2))
    print(f'\nResults saved to: {results_path}')

    # Run analyzer
    try:
        from analyze import generate_summary, generate_narrative
        summary_path = run_dir / 'summary.md'
        summary_path.write_text(generate_summary(results))
        print(f'Summary:   {summary_path}')

        narrative_path = run_dir / 'narrative.md'
        transcripts_dir = run_dir / 'transcripts'
        if transcripts_dir.exists():
            narrative_path.write_text(generate_narrative(results, transcripts_dir))
            print(f'Narrative: {narrative_path}')
    except ImportError:
        print('WARNING: analyze.py not found, skipping summary generation')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Smoke test run.py discovery and dry-run**

```bash
cd tests/mdedit/benchmarks-v2
python3 run.py --dry-run
```

Expected: prints all 66 runs in the matrix without executing anything. Verify replace-large does not list `small` size.

- [ ] **Step 3: Commit**

```bash
git add tests/mdedit/benchmarks-v2/run.py
git commit -m "feat(benchmark-v2): add runner with scenario discovery and --bare mode"
```

---

### Task 7: Write analyze.py

**Files:**
- Create: `tests/mdedit/benchmarks-v2/analyze.py`

- [ ] **Step 1: Write analyze.py**

Create `tests/mdedit/benchmarks-v2/analyze.py`:

```python
#!/usr/bin/env python3
"""
Benchmark analysis — produces summary.md and narrative.md from results.

Can be run standalone:
    python3 analyze.py results/run-YYYYMMDD-HHMMSS/

Or imported by run.py for automatic post-run analysis.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median


def _compute_stats(tokens: list[int]) -> dict:
    """Compute min/median/max for a list of token counts."""
    if not tokens:
        return {'min': None, 'median': None, 'max': None, 'n': 0}
    return {
        'min': min(tokens),
        'median': median(tokens),
        'max': max(tokens),
        'n': len(tokens),
    }


def _format_stats(stats: dict) -> str:
    """Format stats as 'min/med/max' or '—'."""
    if stats['n'] == 0:
        return '—'
    return f"{stats['min']}/{int(stats['median'])}/{stats['max']}"


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------

def generate_summary(results: list[dict]) -> str:
    """
    Generate summary.md content from results.

    Produces: headline savings %, per-scenario comparison table,
    variance stats, and failure report.
    """
    valid = [r for r in results if r.get('success') and r.get('correct')]

    # Group by (task, size, condition)
    grouped = defaultdict(list)
    for r in valid:
        key = (r['task'], r['size'], r['condition'])
        grouped[key].append(r['total_tokens'])

    # Build comparison rows
    task_size_pairs = defaultdict(dict)
    for (task, size, condition), tokens in grouped.items():
        task_size_pairs[(task, size)][condition] = _compute_stats(tokens)

    rows = []
    for (task, size), conditions in sorted(task_size_pairs.items()):
        mdedit = conditions.get('mdedit')
        baseline = conditions.get('baseline')
        savings = None
        if (mdedit and baseline and mdedit['median'] and baseline['median']):
            savings = ((baseline['median'] - mdedit['median']) / baseline['median']) * 100
        rows.append({
            'task': task, 'size': size,
            'mdedit': mdedit, 'baseline': baseline,
            'savings': savings,
        })

    size_order = {'small': 0, 'medium': 1, 'large': 2}
    rows.sort(key=lambda r: (r['task'], size_order.get(r['size'], 99)))

    # Headline
    savings_list = [r['savings'] for r in rows if r['savings'] is not None]
    overall = median(savings_list) if savings_list else None

    lines = []
    date_str = datetime.now().strftime('%Y-%m-%d')
    lines.append(f'# mdedit Benchmark Results — {date_str}\n')

    if overall is not None:
        lines.append(f'**Median token savings: {overall:+.1f}%**\n')
        if overall > 0:
            lines.append(f'mdedit reduces token consumption by {overall:.1f}% on average.\n')
        elif overall < 0:
            lines.append(f'mdedit increases token consumption by {abs(overall):.1f}% on average.\n')

    # Per-scenario table
    lines.append('## Per-Scenario Comparison\n')
    lines.append('| Scenario | Size | mdedit (min/med/max) | Baseline (min/med/max) | Savings |')
    lines.append('|---|---|---|---|---|')

    for row in rows:
        m = _format_stats(row['mdedit'] or {'n': 0})
        b = _format_stats(row['baseline'] or {'n': 0})
        s = f"{row['savings']:+.1f}%" if row['savings'] is not None else '—'
        lines.append(f"| {row['task']} | {row['size']} | {m} | {b} | {s} |")

    lines.append('')

    # Variance
    lines.append('## Consistency\n')
    lines.append('| Condition | IQR/Median | Interpretation |')
    lines.append('|---|---|---|')

    for condition in ['mdedit', 'baseline']:
        tokens = [r['total_tokens'] for r in valid if r['condition'] == condition]
        if len(tokens) < 4:
            lines.append(f'| {condition} | — | Insufficient data |')
            continue
        s = sorted(tokens)
        q1 = s[len(s) // 4]
        q3 = s[(3 * len(s)) // 4]
        med = median(tokens)
        ratio = (q3 - q1) / med if med else 0
        interp = (
            'Very consistent' if ratio < 0.2 else
            'Consistent' if ratio < 0.4 else
            'Moderate variance' if ratio < 0.6 else
            'High variance'
        )
        lines.append(f'| {condition} | {ratio:.3f} | {interp} |')

    lines.append('')

    # Failures
    failures = [r for r in results if not r.get('success') or not r.get('correct')]
    if failures:
        lines.append('## Failed Runs\n')
        lines.append('| Task | Size | Condition | Rep | Status | Reason |')
        lines.append('|---|---|---|---|---|---|')
        for f in sorted(failures, key=lambda x: (x['task'], x['size'], x['condition'])):
            status = 'error' if not f.get('success') else 'incorrect'
            reason = f.get('error') or f.get('validation_reason') or ''
            if len(reason) > 60:
                reason = reason[:57] + '...'
            lines.append(
                f"| {f['task']} | {f['size']} | {f['condition']} "
                f"| {f['rep']} | {status} | {reason} |"
            )
        lines.append('')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Narrative generation
# ---------------------------------------------------------------------------

def _extract_tool_calls(transcript_json: str) -> list[dict]:
    """
    Extract tool call sequence from a transcript JSON.

    Returns list of dicts: {'tool': name, 'summary': brief description}
    """
    try:
        data = json.loads(transcript_json)
    except (json.JSONDecodeError, ValueError):
        return []

    calls = []
    messages = data.get('messages') or []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get('content') or []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            tool_name = block.get('name', 'unknown')
            tool_input = block.get('input', {})

            # Build a brief summary based on tool type
            if tool_name == 'Bash' or tool_name == 'bash':
                cmd = tool_input.get('command', '')
                summary = cmd[:100] if cmd else 'bash command'
            elif tool_name == 'Read' or tool_name == 'read':
                path = tool_input.get('file_path', '')
                summary = f'read {Path(path).name}' if path else 'read file'
            elif tool_name == 'Edit' or tool_name == 'edit':
                path = tool_input.get('file_path', '')
                summary = f'edit {Path(path).name}' if path else 'edit file'
            elif tool_name == 'Write' or tool_name == 'write':
                path = tool_input.get('file_path', '')
                summary = f'write {Path(path).name}' if path else 'write file'
            else:
                summary = tool_name

            calls.append({'tool': tool_name, 'summary': summary})

    return calls


def generate_narrative(results: list[dict], transcripts_dir: Path) -> str:
    """
    Generate narrative.md from showcase transcripts.

    Produces side-by-side comparison of tool call sequences
    for each showcase scenario/size combination.
    """
    # Find showcase scenarios (those with transcripts)
    transcript_files = list(transcripts_dir.glob('*.json'))
    if not transcript_files:
        return '# Narrative\n\nNo showcase transcripts found.\n'

    # Group transcripts by (task, size)
    grouped = defaultdict(lambda: defaultdict(list))
    for tf in transcript_files:
        # filename: replace-large-mdedit-large-rep1.json
        parts = tf.stem.rsplit('-', 3)  # name-condition-size-repN
        if len(parts) < 4:
            continue
        # Handle scenario names with hyphens by parsing from the right
        rep_str = parts[-1]  # e.g. "rep1"
        size = parts[-2]
        condition = parts[-3]
        name = '-'.join(parts[:-3])
        grouped[(name, size)][condition].append(tf)

    lines = ['# Narrative Comparison\n']

    # Get token stats from results for context
    result_lookup = defaultdict(list)
    for r in results:
        if r.get('success') and r.get('correct'):
            result_lookup[(r['task'], r['size'], r['condition'])].append(r)

    for (name, size) in sorted(grouped.keys()):
        lines.append(f'## {name} / {size}\n')

        for condition in ['baseline', 'mdedit']:
            transcripts = grouped[(name, size)].get(condition, [])
            runs = result_lookup.get((name, size, condition), [])

            tokens_list = [r['total_tokens'] for r in runs]
            med_tokens = int(median(tokens_list)) if tokens_list else 0
            tool_counts = [r['num_tool_calls'] for r in runs]
            med_tools = int(median(tool_counts)) if tool_counts else 0

            lines.append(f'### {condition} (median: {med_tokens:,} tokens, {med_tools} tool calls)\n')

            # Show tool calls from first available transcript
            if transcripts:
                transcript_text = transcripts[0].read_text()
                calls = _extract_tool_calls(transcript_text)
                if calls:
                    for i, call in enumerate(calls, 1):
                        lines.append(f'{i}. **{call["tool"]}** — {call["summary"]}')
                    lines.append('')
                else:
                    lines.append('(no tool calls extracted)\n')
            else:
                lines.append('(no transcript available)\n')

        # Savings line
        mdedit_runs = result_lookup.get((name, size, 'mdedit'), [])
        baseline_runs = result_lookup.get((name, size, 'baseline'), [])
        if mdedit_runs and baseline_runs:
            m_med = median([r['total_tokens'] for r in mdedit_runs])
            b_med = median([r['total_tokens'] for r in baseline_runs])
            if b_med > 0:
                pct = ((b_med - m_med) / b_med) * 100
                lines.append(f'**Savings: {pct:.1f}% fewer tokens**\n')

        lines.append('---\n')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Standalone CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print('Usage: python3 analyze.py results/run-YYYYMMDD-HHMMSS/')
        sys.exit(1)

    run_dir = Path(sys.argv[1])
    results_path = run_dir / 'results.json'

    if not results_path.exists():
        print(f'ERROR: {results_path} not found')
        sys.exit(1)

    results = json.loads(results_path.read_text())

    # Generate summary
    summary_path = run_dir / 'summary.md'
    summary_path.write_text(generate_summary(results))
    print(f'Summary:   {summary_path}')

    # Generate narrative if transcripts exist
    transcripts_dir = run_dir / 'transcripts'
    if transcripts_dir.exists() and list(transcripts_dir.glob('*.json')):
        narrative_path = run_dir / 'narrative.md'
        narrative_path.write_text(generate_narrative(results, transcripts_dir))
        print(f'Narrative: {narrative_path}')
    else:
        print('No transcripts found, skipping narrative')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Smoke test analyze.py with synthetic data**

```bash
cd tests/mdedit/benchmarks-v2
python3 -c "
from analyze import generate_summary

# Minimal synthetic results
results = [
    {'task': 'test', 'condition': 'mdedit', 'size': 'small', 'rep': 1,
     'success': True, 'correct': True, 'total_tokens': 1000,
     'input_tokens': 600, 'output_tokens': 400, 'num_tool_calls': 1,
     'duration_s': 10, 'error': '', 'validation_reason': ''},
    {'task': 'test', 'condition': 'baseline', 'size': 'small', 'rep': 1,
     'success': True, 'correct': True, 'total_tokens': 2000,
     'input_tokens': 1200, 'output_tokens': 800, 'num_tool_calls': 3,
     'duration_s': 15, 'error': '', 'validation_reason': ''},
]

summary = generate_summary(results)
assert '+50.0%' in summary, f'Expected +50.0% savings in summary'
assert 'test' in summary
print('Summary smoke test passed')
print(summary)
"
```

Expected: prints summary with `+50.0%` savings.

- [ ] **Step 3: Commit**

```bash
git add tests/mdedit/benchmarks-v2/analyze.py
git commit -m "feat(benchmark-v2): add analyzer with summary table and narrative generation"
```

---

### Task 8: End-to-end dry run and first real run

**Files:** None (validation only)

- [ ] **Step 1: Verify dry-run shows complete matrix**

```bash
cd tests/mdedit/benchmarks-v2
python3 run.py --dry-run
```

Expected: 66 runs listed. replace-large should not show `small` size. edit-and-verify and replace-large should have `★` (showcase marker).

- [ ] **Step 2: Run a single scenario to verify the pipeline end-to-end**

```bash
cd tests/mdedit/benchmarks-v2
python3 run.py --scenarios delete-section --sizes small --reps 1
```

Expected: 2 runs (mdedit + baseline), both marked `+` (correct). A `results/run-*/` directory is created with `results.json` and `summary.md`.

- [ ] **Step 3: Inspect the results**

```bash
cat tests/mdedit/benchmarks-v2/results/run-*/summary.md
```

Expected: summary table with one row for delete-section/small showing both conditions and a savings percentage.

- [ ] **Step 4: Run a showcase scenario to verify transcript capture**

```bash
cd tests/mdedit/benchmarks-v2
python3 run.py --scenarios replace-large --sizes large --reps 1
```

Expected: `results/run-*/transcripts/` contains `replace-large-mdedit-large-rep1.json` and `replace-large-baseline-large-rep1.json`. A `narrative.md` file is generated.

- [ ] **Step 5: Full run (optional — costs ~$0.50-1.00)**

```bash
cd tests/mdedit/benchmarks-v2
python3 run.py
```

Expected: 66 runs, completes in ~2 minutes, summary.md and narrative.md generated.

- [ ] **Step 6: Commit any adjustments**

If steps 2-5 revealed issues that required fixes, commit them:

```bash
git add tests/mdedit/benchmarks-v2/
git commit -m "fix(benchmark-v2): adjustments from end-to-end validation"
```

---

## Self-Review

**Spec coverage check:**
- Scenario discovery from `scenarios/*/scenario.yaml` → Task 6 (run.py `discover_scenarios`)
- `--bare` mode → Task 6 (run.py command construction)
- Placeholder substitution → Task 6 (run.py `substitute_placeholders`)
- file-diff validation → Task 5 (validate.py `validate_file_diff`)
- report-contains validation → Task 5 (validate.py `validate_report_contains`)
- Transcript capture for showcase scenarios → Task 6 (run.py `run_single`)
- Summary table generation → Task 7 (analyze.py `generate_summary`)
- Narrative diff generation → Task 7 (analyze.py `generate_narrative`)
- 4 initial scenarios → Task 3 (scenario definitions)
- Expected output files → Task 4
- System prompts → Task 2
- Fixtures → Task 1 (copied from v1)
- Workers default 15 → Task 6 (run.py argparse)
- Variance reporting → Task 7 (analyze.py, in `generate_summary`)
- Failure reporting → Task 7 (analyze.py, in `generate_summary`)
- Modular "add a scenario" workflow → verified by directory structure

**Placeholder scan:** No TBDs, TODOs, or "implement later" anywhere.

**Type consistency:** `discover_scenarios` returns `list[dict]`, `run_single` takes `scenario: dict` — consistent. `validate_file_diff` and `validate_report_contains` both return `dict` with `valid` and `reason` keys — consistent with how `run_single` reads them. `generate_summary` and `generate_narrative` both return `str` — consistent with how `main()` writes them.
