# mdedit Token Efficiency Benchmark — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a benchmark harness that quantifies the token cost advantage of mdedit over standard Claude Code tools across document sizes and task types.

**Architecture:** Python runner dispatches `claude -p` agents (one per task × condition × repetition). Two system prompts: one with mdedit command reference, one without. Agents edit markdown fixture files in isolated temp directories. Runner captures JSON output with token usage, validates correctness, and writes structured results. Analysis script produces summary tables with median/min/max token counts and percentage savings.

**Tech Stack:** Python 3 (subprocess, concurrent.futures, json, statistics, argparse, shutil, pathlib, difflib), Claude CLI (`claude -p --output-format json`), mdedit binary (pre-built)

**Spec:** `docs/plans/2026-03-24-mdedit-benchmark-design.md`

**Reference implementation:** `tests/mdedit/run_tests.py` (same `claude -p` dispatch + parallel execution pattern)

---

## File Structure

```
tests/mdedit/benchmarks/
  run_benchmarks.py                    # orchestrator (create)
  analyze.py                           # results analysis + summary tables (create)
  validate.py                          # correctness validation helpers (create)
  fixtures/
    small.md                           # ~50 lines, 5-6 sections (create)
    medium.md                          # ~200 lines, 15-20 sections (create)
    large.md                           # ~500+ lines, 30+ sections (create)
  prompts/
    system-mdedit.md                   # system prompt with mdedit reference (create)
    system-baseline.md                 # system prompt without mdedit (create)
    isolated/
      replace-small.md                 # replace ~5 line section (create)
      replace-large.md                 # replace 40+ line section (create)
      insert-section.md                # insert new section between existing (create)
      delete-section.md                # delete a section entirely (create)
      rename-heading.md                # rename a heading (create)
      multi-section-update.md          # update 3 sections in one prompt (create)
    workflows/
      targeted-read.md                 # read a single section (create)
      build-toc.md                     # build + prepend table of contents (create)
      edit-and-verify.md               # replace content + confirm result (create)
  expected/
    small/                             # expected outputs per operation (create)
    medium/                            # expected outputs per operation (create)
    large/                             # expected outputs per operation (create)
  results/                             # timestamped run results (create)
    .gitkeep
  .gitignore                           # ignore results/*.json (create)
```

---

### Task 1: Scaffold directory structure

**Files:**
- Create: `tests/mdedit/benchmarks/.gitignore`
- Create: `tests/mdedit/benchmarks/results/.gitkeep`
- Create: directories for `fixtures/`, `prompts/isolated/`, `prompts/workflows/`, `expected/small/`, `expected/medium/`, `expected/large/`

- [ ] **Step 1: Create all directories**

```bash
mkdir -p tests/mdedit/benchmarks/{fixtures,prompts/{isolated,workflows},expected/{small,medium,large},results}
touch tests/mdedit/benchmarks/results/.gitkeep
```

- [ ] **Step 2: Create .gitignore**

Create `tests/mdedit/benchmarks/.gitignore`:
```
results/*.json
results/*.md
!results/.gitkeep
```

- [ ] **Step 3: Commit**

```bash
git add tests/mdedit/benchmarks/
git commit -m "chore(benchmark): scaffold directory structure"
```

---

### Task 2: Author fixture files

**Files:**
- Create: `tests/mdedit/benchmarks/fixtures/small.md`
- Create: `tests/mdedit/benchmarks/fixtures/medium.md`
- Create: `tests/mdedit/benchmarks/fixtures/large.md`

All three fixtures share consistent heading names so prompts work without per-fixture templating. The shared section names are:

| Section | small.md | medium.md | large.md |
|---------|----------|-----------|----------|
| Background | ~5 lines | ~10 lines | ~50 lines |
| Implementation | ~8 lines | ~25 lines | ~60 lines |
| Results | ~5 lines | ~15 lines | ~40 lines |
| Conclusion | ~5 lines | ~10 lines | ~20 lines |

medium.md and large.md add nested subsections under these parents (e.g., `Implementation/Architecture`, `Implementation/Testing`, `Results/Performance`, `Results/Limitations`). large.md goes three levels deep.

- [ ] **Step 1: Author small.md**

Write `tests/mdedit/benchmarks/fixtures/small.md` — a simple project README. ~50 lines total, 5-6 H2 sections (`## Background`, `## Implementation`, `## Results`, `## Conclusion`, `## References`). Each section 5-10 lines of plausible prose. Include YAML frontmatter (`title`, `date`, `status`).

Content should be plausible technical writing (not lorem ipsum) — a fictional project description. This makes it realistic for LLM interaction.

- [ ] **Step 2: Author medium.md**

Write `tests/mdedit/benchmarks/fixtures/medium.md` — a design document. ~200 lines total, 15-20 sections across 2 heading levels. Same top-level sections as small.md but with subsections. `## Implementation` should have 3-4 subsections (`### Architecture`, `### Data Model`, `### API Design`, `### Testing`). `## Results` should have 2-3 subsections. Include a code block in at least one section. Sections range 10-30 lines.

- [ ] **Step 3: Author large.md**

Write `tests/mdedit/benchmarks/fixtures/large.md` — a comprehensive reference document. ~500+ lines total, 30+ sections across 3 heading levels. Same top-level structure, deeply nested. `## Implementation` should have 6+ subsections, some with their own sub-subsections. At least two sections should exceed 50 lines (for the large-section replace benchmark). Include multiple code blocks, a table, and a frontmatter block with 5+ fields.

- [ ] **Step 4: Verify line counts**

```bash
wc -l tests/mdedit/benchmarks/fixtures/*.md
```

Expected: small ~50, medium ~200, large ~500+.

- [ ] **Step 5: Verify shared headings exist in all three**

```bash
for f in tests/mdedit/benchmarks/fixtures/*.md; do
    echo "=== $f ==="
    grep '^## ' "$f"
done
```

Confirm `## Background`, `## Implementation`, `## Results`, `## Conclusion` appear in all three.

- [ ] **Step 6: Commit**

```bash
git add tests/mdedit/benchmarks/fixtures/
git commit -m "feat(benchmark): add fixture files (small/medium/large)"
```

---

### Task 3: Write system prompts

**Files:**
- Create: `tests/mdedit/benchmarks/prompts/system-mdedit.md`
- Create: `tests/mdedit/benchmarks/prompts/system-baseline.md`

- [ ] **Step 1: Write system-mdedit.md**

This prompt defines the mdedit agent's contract. Structure:

```markdown
# Benchmark Agent (mdedit)

You are a benchmark agent. Complete the editing task described in the user prompt.
Work in the directory: {{WORKDIR}}
The file to edit is: {{WORKDIR}}/{{FIXTURE}}

## Rules

1. Complete the task using the fewest tool calls possible.
2. Do NOT access any memory system or CLAUDE.md files.
3. The mdedit binary is at: {{BINARY}}
4. When done, write a brief summary of what you did to {{REPORT_PATH}}.

## mdedit Command Reference

[Include a condensed command reference extracted from the mdedit v1 spec.
Cover: outline, extract, search, replace, append, prepend, insert, delete,
rename, frontmatter. Include addressing syntax (_preamble, ## Name,
Parent/Child). Include exit codes. Keep it minimal but complete enough
for an agent to use every command correctly.]

## Report Format

Write to {{REPORT_PATH}}:

    # Benchmark Report

    ## Task
    [one-line description of what was asked]

    ## Steps
    [numbered list: what tool you called, why]

    ## Verification
    [how you confirmed the task was done correctly]
```

Key: the mdedit reference must be self-contained. The agent cannot reference external docs. Extract the essentials from the v1 spec at `docs/plans/2026-03-22-mdedit-v1-spec.md` — command syntax, addressing, output format, exit codes. Omit design rationale, parser details, counting rules. Target ~150 lines for the reference section.

- [ ] **Step 2: Write system-baseline.md**

Identical to system-mdedit.md but with no mdedit reference, no binary path, and no mention of mdedit. The agent gets standard tools only.

```markdown
# Benchmark Agent

You are a benchmark agent. Complete the editing task described in the user prompt.
Work in the directory: {{WORKDIR}}
The file to edit is: {{WORKDIR}}/{{FIXTURE}}

## Rules

1. Complete the task using the fewest tool calls possible.
2. Do NOT access any memory system or CLAUDE.md files.
3. Use your standard tools (Read, Edit, Write, Bash) to complete the task.
4. When done, write a brief summary of what you did to {{REPORT_PATH}}.

## Report Format

Write to {{REPORT_PATH}}:

    # Benchmark Report

    ## Task
    [one-line description of what was asked]

    ## Steps
    [numbered list: what tool you called, why]

    ## Verification
    [how you confirmed the task was done correctly]
```

Key difference: no tool guidance beyond "use your standard tools." This is the naturalistic condition.

- [ ] **Step 3: Verify placeholder consistency**

```bash
grep -c '{{BINARY}}' tests/mdedit/benchmarks/prompts/system-mdedit.md
grep -c '{{BINARY}}' tests/mdedit/benchmarks/prompts/system-baseline.md
```

Expected: system-mdedit.md has 1+ occurrences, system-baseline.md has 0.

- [ ] **Step 4: Commit**

```bash
git add tests/mdedit/benchmarks/prompts/system-*.md
git commit -m "feat(benchmark): add system prompts (mdedit + baseline)"
```

---

### Task 4: Write isolated operation prompts

**Files:**
- Create: `tests/mdedit/benchmarks/prompts/isolated/replace-small.md`
- Create: `tests/mdedit/benchmarks/prompts/isolated/replace-large.md`
- Create: `tests/mdedit/benchmarks/prompts/isolated/insert-section.md`
- Create: `tests/mdedit/benchmarks/prompts/isolated/delete-section.md`
- Create: `tests/mdedit/benchmarks/prompts/isolated/rename-heading.md`
- Create: `tests/mdedit/benchmarks/prompts/isolated/multi-section-update.md`

Each prompt must be condition-agnostic (used with both system prompts). They describe WHAT to do, not HOW.

- [ ] **Step 1: Write replace-small.md**

```markdown
Replace the content of the "Conclusion" section with the following text:

This project demonstrated significant improvements in processing speed
and memory efficiency. Future work will focus on scaling to larger
datasets and improving the user interface.

Do not modify any other section. The heading "## Conclusion" must remain.
```

Target: the Conclusion section in all fixtures is 5-10 lines. This is the small-section replace.

- [ ] **Step 2: Write replace-large.md**

```markdown
Replace the content of the "Implementation" section (including all its
subsections) with the following text:

[Provide ~40 lines of replacement content — a rewritten implementation
section with enough prose to be realistic. This must be longer than the
original in medium.md and comparable to large.md to test the scaling
hypothesis.]

Do not modify any other section. The heading "## Implementation" must remain.
```

Note: this prompt is only used against medium.md and large.md (small.md has no section large enough).

- [ ] **Step 3: Write insert-section.md**

```markdown
Insert a new section called "## Future Work" immediately after the
"## Results" section. The content should be:

Several promising directions emerge from this work. First, the architecture
could be extended to support distributed processing across multiple nodes.
Second, the validation pipeline would benefit from property-based testing
to catch edge cases. Third, integration with existing CI/CD systems would
reduce deployment friction.

The new section must appear between "## Results" and "## Conclusion".
```

- [ ] **Step 4: Write delete-section.md**

```markdown
Delete the "## References" section and all its content from the document.
No other sections should be modified.
```

Note: the "References" section should exist in all three fixtures (added in Task 2).

- [ ] **Step 5: Write rename-heading.md**

```markdown
Rename the heading "## Conclusion" to "## Summary and Next Steps".
Do not change the content of the section, only the heading text.
```

- [ ] **Step 6: Write multi-section-update.md**

```markdown
Make the following three changes to the document:

1. Append this paragraph to the "Background" section:
   "Recent advances in compiler optimization have made this approach
   more practical than previously thought."

2. Replace the content of the "Conclusion" section with:
   "The results exceeded initial expectations across all benchmarks."

3. Rename the heading "## Results" to "## Experimental Results".

Do not modify any sections other than the three listed above.
```

- [ ] **Step 7: Commit**

```bash
git add tests/mdedit/benchmarks/prompts/isolated/
git commit -m "feat(benchmark): add isolated operation prompts"
```

---

### Task 5: Write workflow prompts

**Files:**
- Create: `tests/mdedit/benchmarks/prompts/workflows/targeted-read.md`
- Create: `tests/mdedit/benchmarks/prompts/workflows/build-toc.md`
- Create: `tests/mdedit/benchmarks/prompts/workflows/edit-and-verify.md`

- [ ] **Step 1: Write targeted-read.md**

```markdown
Read me the "Implementation" section of the document at {{WORKDIR}}/{{FIXTURE}}.
Return only the content of that section (including any subsections).
Do not read or return any other part of the document.
```

- [ ] **Step 2: Write build-toc.md**

```markdown
Build a table of contents for the document at {{WORKDIR}}/{{FIXTURE}}.

1. Extract all headings from the document.
2. Format them as a nested markdown list (indented by heading level).
3. Prepend the table of contents to the very top of the document
   (before any existing content, but after frontmatter if present).

The TOC should look like:
- Background
- Implementation
  - Architecture
  - Data Model
  ...
- Results
  ...

(Adjusted to match the actual headings in the document.)
```

- [ ] **Step 3: Write edit-and-verify.md**

```markdown
Replace the content of the "Background" section with the following text:

This project addresses the growing need for efficient document processing
in large-scale systems. Previous approaches relied on batch processing,
which introduced unacceptable latency for real-time applications.

After making the replacement, confirm back to me exactly what the
"Background" section now contains. Show me the full section content.
```

- [ ] **Step 4: Commit**

```bash
git add tests/mdedit/benchmarks/prompts/workflows/
git commit -m "feat(benchmark): add workflow prompts"
```

---

### Task 6: Generate expected outputs for isolated operations

**Files:**
- Create: `tests/mdedit/benchmarks/expected/small/*.md` (5 files — no replace-large for small)
- Create: `tests/mdedit/benchmarks/expected/medium/*.md` (6 files)
- Create: `tests/mdedit/benchmarks/expected/large/*.md` (6 files)

Expected outputs are the fixture files after the operation has been correctly applied. They are hand-authored (not generated by mdedit) to avoid circular validation.

- [ ] **Step 1: Generate expected outputs for small.md**

For each isolated operation (except replace-large), manually apply the edit to small.md and save the result:

```
expected/small/replace-small.md      — small.md with Conclusion section replaced
expected/small/insert-section.md     — small.md with Future Work inserted after Results
expected/small/delete-section.md     — small.md with References section removed
expected/small/rename-heading.md     — small.md with Conclusion renamed
expected/small/multi-section-update.md — small.md with all three changes applied
```

Method: copy fixture, manually edit, save. Verify each by reading and confirming only the intended change was made.

- [ ] **Step 2: Generate expected outputs for medium.md**

Same as step 1 but for medium.md, plus `expected/medium/replace-large.md`.

- [ ] **Step 3: Generate expected outputs for large.md**

Same as step 1 but for large.md, plus `expected/large/replace-large.md`.

- [ ] **Step 4: Verify expected outputs differ from fixtures only in intended ways**

```bash
for size in small medium large; do
    echo "=== $size ==="
    for expected in tests/mdedit/benchmarks/expected/$size/*.md; do
        op=$(basename "$expected" .md)
        echo "  $op: $(diff tests/mdedit/benchmarks/fixtures/$size.md "$expected" | head -5)"
    done
done
```

- [ ] **Step 5: Commit**

```bash
git add tests/mdedit/benchmarks/expected/
git commit -m "feat(benchmark): add hand-authored expected outputs"
```

---

### Task 7: Write correctness validation module

**Files:**
- Create: `tests/mdedit/benchmarks/validate.py`

- [ ] **Step 1: Write validate.py**

```python
"""
Correctness validation for benchmark runs.

Two modes:
- Isolated operations: semantic diff against expected output
- Workflows: structural property checks
"""
import difflib
import re
from pathlib import Path


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for comparison.

    - Strip trailing whitespace per line
    - Collapse multiple blank lines to single blank line
    - Strip trailing newlines at end of file
    """
    lines = [line.rstrip() for line in text.splitlines()]
    # Collapse runs of blank lines
    normalized = []
    prev_blank = False
    for line in lines:
        if line == '':
            if not prev_blank:
                normalized.append(line)
            prev_blank = True
        else:
            normalized.append(line)
            prev_blank = False
    return '\n'.join(normalized).strip() + '\n'


def validate_isolated(result_file: Path, expected_file: Path) -> dict:
    """Validate an isolated operation result against expected output.

    Returns dict with:
      - valid: bool
      - reason: str (empty if valid)
      - diff: str (unified diff if invalid)
    """
    result_text = normalize_whitespace(result_file.read_text())
    expected_text = normalize_whitespace(expected_file.read_text())

    if result_text == expected_text:
        return {'valid': True, 'reason': '', 'diff': ''}

    diff = '\n'.join(difflib.unified_diff(
        expected_text.splitlines(),
        result_text.splitlines(),
        fromfile='expected',
        tofile='actual',
        lineterm=''
    ))

    return {
        'valid': False,
        'reason': 'Content differs from expected output after whitespace normalization',
        'diff': diff
    }


def validate_targeted_read(report_text: str, fixture_file: Path,
                           section_name: str) -> dict:
    """Validate workflow 1: agent returned the correct section content."""
    # Extract section from fixture using simple heading parsing
    fixture = fixture_file.read_text()
    section_content = _extract_section(fixture, section_name)

    if section_content is None:
        return {'valid': False,
                'reason': f'Section "{section_name}" not found in fixture'}

    # Check if the section content appears in the report
    normalized_section = normalize_whitespace(section_content)
    normalized_report = normalize_whitespace(report_text)

    if normalized_section.strip() in normalized_report:
        return {'valid': True, 'reason': '', 'diff': ''}

    return {
        'valid': False,
        'reason': 'Agent response does not contain expected section content',
        'diff': ''
    }


def validate_build_toc(result_file: Path) -> dict:
    """Validate workflow 2: TOC was prepended to the document."""
    content = result_file.read_text()
    lines = content.splitlines()

    # Find where content starts (skip frontmatter)
    start = 0
    if lines and lines[0].strip() == '---':
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                start = i + 1
                break

    # After frontmatter, the next non-blank content should look like a TOC
    # (lines starting with - or containing nested list items)
    toc_found = False
    for i in range(start, min(start + 50, len(lines))):
        line = lines[i].strip()
        if line.startswith('- ') or line.startswith('  - '):
            toc_found = True
            break

    if not toc_found:
        return {'valid': False,
                'reason': 'No TOC found near top of document (after frontmatter)',
                'diff': ''}

    return {'valid': True, 'reason': '', 'diff': ''}


def validate_edit_and_verify(report_text: str,
                             expected_content: str) -> dict:
    """Validate workflow 3: agent confirmed correct section content."""
    normalized_expected = normalize_whitespace(expected_content).strip()
    normalized_report = normalize_whitespace(report_text)

    if normalized_expected in normalized_report:
        return {'valid': True, 'reason': '', 'diff': ''}

    return {
        'valid': False,
        'reason': 'Agent response does not contain expected replacement content',
        'diff': ''
    }


def _extract_section(markdown: str, section_name: str) -> str | None:
    """Extract a section's content from markdown by heading name.

    Returns content including the heading line through to the next
    same-or-higher-level heading.
    """
    lines = markdown.splitlines()
    section_start = None
    section_level = None

    for i, line in enumerate(lines):
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading_match:
            level = len(heading_match.group(1))
            name = heading_match.group(2).strip()
            if name == section_name and section_start is None:
                section_start = i
                section_level = level
            elif section_start is not None and level <= section_level:
                return '\n'.join(lines[section_start:i])

    if section_start is not None:
        return '\n'.join(lines[section_start:])
    return None
```

- [ ] **Step 2: Test normalize_whitespace manually**

```bash
cd tests/mdedit/benchmarks
python3 -c "
from validate import normalize_whitespace
# Trailing whitespace stripped
assert normalize_whitespace('hello  \nworld  \n') == 'hello\nworld\n'
# Multiple blank lines collapsed
assert normalize_whitespace('a\n\n\n\nb\n') == 'a\n\nb\n'
print('validate.py basic tests pass')
"
```

- [ ] **Step 3: Commit**

```bash
git add tests/mdedit/benchmarks/validate.py
git commit -m "feat(benchmark): add correctness validation module"
```

---

### Task 8: Write the benchmark runner

**Files:**
- Create: `tests/mdedit/benchmarks/run_benchmarks.py`

This is the core orchestrator. Pattern follows `tests/mdedit/run_tests.py` but adapted for the benchmark structure.

- [ ] **Step 1: Write run_benchmarks.py — imports and constants**

```python
#!/usr/bin/env python3
"""
Token efficiency benchmark runner for mdedit vs standard editing tools.

Dispatches Claude CLI agents to complete editing tasks under two conditions
(mdedit vs baseline), captures token usage, and validates correctness.

Usage:
    python3 run_benchmarks.py [--tasks replace-small,insert-section] \
                               [--sizes small,medium,large] \
                               [--conditions mdedit,baseline] \
                               [--reps 5] [--model haiku] \
                               [--workers 5] [--timeout 300] [--dry-run]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
FIXTURES_DIR = SCRIPT_DIR / 'fixtures'
PROMPTS_DIR = SCRIPT_DIR / 'prompts'
EXPECTED_DIR = SCRIPT_DIR / 'expected'
RESULTS_DIR = SCRIPT_DIR / 'results'
MDEDIT_BINARY = SCRIPT_DIR.parent.parent.parent / 'claude-code-only' / 'mdedit' / 'target' / 'release' / 'mdedit'

# Task definitions: (slug, description, is_workflow, excluded_sizes)
TASKS = [
    ('replace-small',        'Replace small section (~5 lines)',     False, []),
    ('replace-large',        'Replace large section (40+ lines)',    False, ['small']),
    ('insert-section',       'Insert new section',                   False, []),
    ('delete-section',       'Delete a section',                     False, []),
    ('rename-heading',       'Rename a heading',                     False, []),
    ('multi-section-update', 'Multi-section update (3 edits)',       False, []),
    ('targeted-read',        'Targeted read (single section)',       True,  []),
    ('build-toc',            'Build + prepend table of contents',    True,  []),
    ('edit-and-verify',      'Edit and verify (self-confirming)',    True,  []),
]

CONDITIONS = ['mdedit', 'baseline']
SIZES = ['small', 'medium', 'large']
```

- [ ] **Step 2: Write run_benchmarks.py — workspace setup and prompt loading**

```python
def verify_binary() -> Path:
    """Verify mdedit binary exists. Only needed for mdedit condition."""
    if not MDEDIT_BINARY.exists():
        print(f"WARNING: mdedit binary not found at {MDEDIT_BINARY}")
        print(f"         mdedit condition will fail. Build: cd claude-code-only/mdedit && cargo build --release")
        return None
    result = subprocess.run([str(MDEDIT_BINARY), '--help'],
                            capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        print(f"WARNING: mdedit binary failed smoke test")
        return None
    return MDEDIT_BINARY.resolve()


def setup_workdir(task_slug: str, condition: str, size: str, rep: int) -> Path:
    """Create isolated temp directory with fixture copy."""
    timestamp = int(time.time() * 1000)
    workdir = Path(f'/tmp/mdedit-bench-{task_slug}-{condition}-{size}-r{rep}-{timestamp}')
    workdir.mkdir(parents=True)

    fixture_src = FIXTURES_DIR / f'{size}.md'
    fixture_dst = workdir / f'{size}.md'
    shutil.copy2(fixture_src, fixture_dst)

    return workdir


def load_prompt(prompt_path: Path, binary: Path | None, workdir: Path,
                fixture_name: str, report_path: Path) -> str:
    """Load and substitute placeholders in a prompt file."""
    content = prompt_path.read_text()
    content = content.replace('{{WORKDIR}}', str(workdir))
    content = content.replace('{{FIXTURE}}', fixture_name)
    content = content.replace('{{REPORT_PATH}}', str(report_path))
    if binary:
        content = content.replace('{{BINARY}}', str(binary))
    return content
```

- [ ] **Step 3: Write run_benchmarks.py — single run execution**

```python
def run_single(task_slug: str, task_desc: str, is_workflow: bool,
               condition: str, size: str, rep: int,
               binary: Path | None, model: str, timeout: int) -> dict:
    """Execute a single benchmark run and return structured result."""
    workdir = setup_workdir(task_slug, condition, size, rep)
    fixture_name = f'{size}.md'
    report_path = workdir / 'report.md'

    # Load system prompt
    system_file = PROMPTS_DIR / f'system-{condition}.md'
    system_prompt = load_prompt(system_file, binary, workdir, fixture_name, report_path)

    # Load task prompt
    subdir = 'workflows' if is_workflow else 'isolated'
    task_file = PROMPTS_DIR / subdir / f'{task_slug}.md'
    user_prompt = load_prompt(task_file, binary, workdir, fixture_name, report_path)

    # Build command — baseline condition should not have mdedit on PATH
    cmd = [
        'claude', '-p',
        '--output-format', 'json',
        '--system-prompt', system_prompt,
        '--model', model,
        '--no-chrome',
        '--dangerously-skip-permissions',
    ]

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)

    # For baseline: ensure mdedit is not discoverable
    if condition == 'baseline' and binary:
        # Remove mdedit's directory from PATH
        binary_dir = str(binary.parent)
        paths = env.get('PATH', '').split(':')
        env['PATH'] = ':'.join(p for p in paths if p != binary_dir)

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd, input=user_prompt,
            capture_output=True, text=True,
            timeout=timeout, env=env, cwd=str(workdir),
        )
        duration = time.time() - start_time

        # Parse JSON output for token usage
        token_data = _parse_token_usage(result.stdout)

        # Validate correctness
        validation = _validate_run(
            task_slug, is_workflow, size, workdir, fixture_name, report_path
        )

        return {
            'task': task_slug,
            'task_desc': task_desc,
            'is_workflow': is_workflow,
            'condition': condition,
            'size': size,
            'rep': rep,
            'success': result.returncode == 0,
            'correct': validation['valid'],
            'validation_reason': validation.get('reason', ''),
            'input_tokens': token_data.get('input_tokens', 0),
            'output_tokens': token_data.get('output_tokens', 0),
            'total_tokens': token_data.get('input_tokens', 0) + token_data.get('output_tokens', 0),
            'duration_s': duration,
            'tool_calls': token_data.get('tool_calls', []),
            'num_tool_calls': token_data.get('num_tool_calls', 0),
            'error': '',
            'workdir': str(workdir),
        }

    except subprocess.TimeoutExpired:
        return _error_result(task_slug, task_desc, is_workflow, condition,
                             size, rep, f'Timeout ({timeout}s)',
                             time.time() - start_time, str(workdir))
    except Exception as e:
        return _error_result(task_slug, task_desc, is_workflow, condition,
                             size, rep, str(e),
                             time.time() - start_time, str(workdir))


def _parse_token_usage(stdout: str) -> dict:
    """Parse token usage from claude JSON output.

    Claude --output-format json returns a JSON object with usage info.
    Extract input_tokens, output_tokens, and tool call details.
    """
    try:
        data = json.loads(stdout)
        # The exact structure depends on claude CLI output format.
        # Adapt this based on actual output during initial testing.
        usage = data.get('usage', {})
        return {
            'input_tokens': usage.get('input_tokens', 0),
            'output_tokens': usage.get('output_tokens', 0),
            'tool_calls': data.get('tool_calls', []),
            'num_tool_calls': len(data.get('tool_calls', [])),
        }
    except (json.JSONDecodeError, TypeError):
        return {'input_tokens': 0, 'output_tokens': 0,
                'tool_calls': [], 'num_tool_calls': 0}


def _validate_run(task_slug: str, is_workflow: bool, size: str,
                   workdir: Path, fixture_name: str,
                   report_path: Path) -> dict:
    """Run correctness validation for a completed benchmark run."""
    from validate import (validate_isolated, validate_build_toc,
                          validate_targeted_read, validate_edit_and_verify)

    result_file = workdir / fixture_name

    if not is_workflow:
        expected_file = EXPECTED_DIR / size / f'{task_slug}.md'
        if not expected_file.exists():
            return {'valid': False, 'reason': f'Expected file not found: {expected_file}'}
        return validate_isolated(result_file, expected_file)

    # Workflows: use structural validation
    report_text = report_path.read_text() if report_path.exists() else ''

    if task_slug == 'targeted-read':
        fixture_file = FIXTURES_DIR / f'{size}.md'
        return validate_targeted_read(report_text, fixture_file, 'Implementation')
    elif task_slug == 'build-toc':
        return validate_build_toc(result_file)
    elif task_slug == 'edit-and-verify':
        expected_content = (
            "This project addresses the growing need for efficient document processing\n"
            "in large-scale systems. Previous approaches relied on batch processing,\n"
            "which introduced unacceptable latency for real-time applications."
        )
        return validate_edit_and_verify(report_text, expected_content)

    return {'valid': False, 'reason': f'Unknown workflow: {task_slug}'}


def _error_result(task_slug, task_desc, is_workflow, condition,
                  size, rep, error, duration, workdir) -> dict:
    """Construct an error result dict."""
    return {
        'task': task_slug, 'task_desc': task_desc,
        'is_workflow': is_workflow, 'condition': condition,
        'size': size, 'rep': rep,
        'success': False, 'correct': False,
        'validation_reason': '', 'error': error,
        'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
        'duration_s': duration, 'tool_calls': [], 'num_tool_calls': 0,
        'workdir': workdir,
    }
```

- [ ] **Step 4: Write run_benchmarks.py — orchestrator and main**

```python
def build_run_matrix(tasks, sizes, conditions, reps, excluded=None):
    """Build the full matrix of (task, size, condition, rep) tuples."""
    matrix = []
    for slug, desc, is_workflow, excluded_sizes in tasks:
        for size in sizes:
            if size in excluded_sizes:
                continue
            for condition in conditions:
                for rep in range(1, reps + 1):
                    matrix.append((slug, desc, is_workflow,
                                   condition, size, rep))
    return matrix


def save_results(results: list, results_dir: Path) -> Path:
    """Save results as timestamped JSON."""
    results_dir.mkdir(exist_ok=True)
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    path = results_dir / f'benchmark-{timestamp}.json'
    with open(path, 'w') as f:
        json.dump(results, f, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(
        description='mdedit token efficiency benchmark')
    parser.add_argument('--tasks', type=str, default=None,
                        help='Comma-separated task slugs (default: all)')
    parser.add_argument('--sizes', type=str, default='small,medium,large',
                        help='Comma-separated sizes (default: small,medium,large)')
    parser.add_argument('--conditions', type=str, default='mdedit,baseline',
                        help='Comma-separated conditions (default: mdedit,baseline)')
    parser.add_argument('--reps', type=int, default=5,
                        help='Repetitions per combination (default: 5)')
    parser.add_argument('--model', type=str, default='haiku',
                        help='Claude model (default: haiku)')
    parser.add_argument('--workers', type=int, default=5,
                        help='Parallel workers (default: 5)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='Timeout per run in seconds (default: 300)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show run matrix without executing')
    args = parser.parse_args()

    if os.environ.get('CLAUDECODE'):
        print("ERROR: Cannot run inside Claude Code session.")
        print("       unset CLAUDECODE && python3 run_benchmarks.py")
        sys.exit(1)

    # Filter tasks
    tasks = TASKS
    if args.tasks:
        slugs = [s.strip() for s in args.tasks.split(',')]
        tasks = [t for t in TASKS if t[0] in slugs]

    sizes = [s.strip() for s in args.sizes.split(',')]
    conditions = [c.strip() for c in args.conditions.split(',')]

    # Verify binary (only needed if mdedit condition is included)
    binary = None
    if 'mdedit' in conditions:
        binary = verify_binary()

    # Build run matrix
    matrix = build_run_matrix(tasks, sizes, conditions, args.reps)
    total = len(matrix)

    print(f"Benchmark: {total} runs | Model: {args.model} | "
          f"Workers: {args.workers} | Timeout: {args.timeout}s")

    if args.dry_run:
        for slug, desc, is_wf, cond, size, rep in matrix:
            wf = 'workflow' if is_wf else 'isolated'
            print(f"  [{wf}] {slug} | {cond} | {size} | rep {rep}")
        print(f"\nTotal: {total} runs")
        return

    # Execute
    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for slug, desc, is_wf, cond, size, rep in matrix:
            future = executor.submit(
                run_single, slug, desc, is_wf, cond, size, rep,
                binary, args.model, args.timeout
            )
            futures[future] = (slug, cond, size, rep)

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1

            status = '+' if (result['success'] and result['correct']) else 'X'
            tokens = result['total_tokens']
            print(f"  [{status}] [{completed:3d}/{total}] "
                  f"{result['task']:25s} | {result['condition']:8s} | "
                  f"{result['size']:6s} | rep {result['rep']} | "
                  f"{tokens:6d} tokens | {result['duration_s']:.0f}s",
                  flush=True)

    # Save results
    results_path = save_results(results, RESULTS_DIR)
    print(f"\nResults saved to: {results_path}")

    # Quick summary
    print_quick_summary(results)


def print_quick_summary(results):
    """Print a quick summary of results."""
    from statistics import median

    successful = [r for r in results if r['success'] and r['correct']]
    failed = [r for r in results if not (r['success'] and r['correct'])]

    print(f"\n{'='*60}")
    print(f"  BENCHMARK COMPLETE: {len(successful)}/{len(results)} runs valid")
    print(f"{'='*60}")

    if failed:
        print(f"\n  Failed/invalid runs:")
        for r in failed:
            reason = r['error'] or r['validation_reason']
            print(f"    {r['task']} | {r['condition']} | {r['size']} | "
                  f"rep {r['rep']}: {reason}")

    # Per-condition median tokens
    for condition in ['mdedit', 'baseline']:
        cond_results = [r for r in successful if r['condition'] == condition]
        if cond_results:
            tokens = [r['total_tokens'] for r in cond_results]
            print(f"\n  {condition}: median {median(tokens):.0f} tokens "
                  f"(min {min(tokens)}, max {max(tokens)}, n={len(cond_results)})")

    print(f"\n  Run analyze.py on the results file for detailed breakdown.")


if __name__ == '__main__':
    main()
```

- [ ] **Step 5: Verify runner loads and shows help**

```bash
cd tests/mdedit/benchmarks
python3 run_benchmarks.py --help
```

- [ ] **Step 6: Verify dry-run shows correct matrix**

```bash
cd tests/mdedit/benchmarks
python3 run_benchmarks.py --dry-run --reps 1
```

Expected: 52 runs (17 isolated + 9 workflow = 26 task variants × 2 conditions = 52). Verify replace-large × small is excluded.

- [ ] **Step 7: Commit**

```bash
git add tests/mdedit/benchmarks/run_benchmarks.py
git commit -m "feat(benchmark): add benchmark runner (run_benchmarks.py)"
```

---

### Task 9: Write the analysis script

**Files:**
- Create: `tests/mdedit/benchmarks/analyze.py`

- [ ] **Step 1: Write analyze.py**

```python
#!/usr/bin/env python3
"""
Analyze benchmark results and produce summary tables.

Usage:
    python3 analyze.py results/benchmark-TIMESTAMP.json
    python3 analyze.py results/benchmark-TIMESTAMP.json --format markdown
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median


def load_results(path: Path) -> list:
    """Load results from JSON file."""
    with open(path) as f:
        return json.load(f)


def filter_valid(results: list) -> list:
    """Return only successful, correct runs."""
    return [r for r in results if r['success'] and r['correct']]


def compute_stats(tokens: list) -> dict:
    """Compute min, median, max for a list of token counts."""
    if not tokens:
        return {'min': 0, 'median': 0, 'max': 0, 'n': 0}
    return {
        'min': min(tokens),
        'median': median(tokens),
        'max': max(tokens),
        'n': len(tokens),
    }


def per_task_comparison(results: list) -> list:
    """Build per-task × per-size comparison table."""
    valid = filter_valid(results)

    # Group by (task, size, condition)
    groups = defaultdict(list)
    for r in valid:
        key = (r['task'], r['size'], r['condition'])
        groups[key].append(r['total_tokens'])

    # Build comparison rows
    rows = []
    tasks_seen = set()
    for r in valid:
        key = (r['task'], r['size'])
        if key in tasks_seen:
            continue
        tasks_seen.add(key)

        mdedit_tokens = groups.get((r['task'], r['size'], 'mdedit'), [])
        baseline_tokens = groups.get((r['task'], r['size'], 'baseline'), [])

        mdedit_stats = compute_stats(mdedit_tokens)
        baseline_stats = compute_stats(baseline_tokens)

        delta = baseline_stats['median'] - mdedit_stats['median']
        pct = (delta / baseline_stats['median'] * 100) if baseline_stats['median'] > 0 else 0

        rows.append({
            'task': r['task'],
            'size': r['size'],
            'is_workflow': r['is_workflow'],
            'mdedit': mdedit_stats,
            'baseline': baseline_stats,
            'delta': delta,
            'savings_pct': pct,
        })

    return sorted(rows, key=lambda x: (x['is_workflow'], x['task'], x['size']))


def tool_usage_summary(results: list) -> dict:
    """Summarize tool usage frequency per condition."""
    valid = filter_valid(results)
    usage = defaultdict(lambda: defaultdict(int))

    for r in valid:
        condition = r['condition']
        for tool_call in r.get('tool_calls', []):
            tool_name = tool_call.get('tool', 'unknown')
            usage[condition][tool_name] += 1

    return dict(usage)


def variance_comparison(results: list) -> dict:
    """Compare coefficient of variation between conditions."""
    valid = filter_valid(results)
    groups = defaultdict(list)

    for r in valid:
        key = (r['task'], r['size'], r['condition'])
        groups[key].append(r['total_tokens'])

    cv_by_condition = defaultdict(list)
    for (task, size, condition), tokens in groups.items():
        if len(tokens) > 1:
            m = median(tokens)
            if m > 0:
                # Use IQR-based spread instead of std for robustness
                sorted_t = sorted(tokens)
                q1 = sorted_t[len(sorted_t) // 4]
                q3 = sorted_t[3 * len(sorted_t) // 4]
                spread = (q3 - q1) / m
                cv_by_condition[condition].append(spread)

    return {cond: median(cvs) if cvs else 0
            for cond, cvs in cv_by_condition.items()}


def failure_report(results: list) -> list:
    """List all failed/invalid runs."""
    return [
        {
            'task': r['task'],
            'condition': r['condition'],
            'size': r['size'],
            'rep': r['rep'],
            'error': r.get('error', ''),
            'validation_reason': r.get('validation_reason', ''),
        }
        for r in results
        if not (r['success'] and r['correct'])
    ]


def print_markdown(rows, tool_usage, variance, failures):
    """Print results as markdown tables."""
    print("# mdedit Benchmark Results\n")

    # Headline
    all_mdedit = [r['mdedit']['median'] for r in rows if r['mdedit']['n'] > 0]
    all_baseline = [r['baseline']['median'] for r in rows if r['baseline']['n'] > 0]
    if all_mdedit and all_baseline:
        overall_mdedit = median(all_mdedit)
        overall_baseline = median(all_baseline)
        overall_savings = (overall_baseline - overall_mdedit) / overall_baseline * 100
        print(f"**Overall median savings: {overall_savings:.0f}%** "
              f"(mdedit median: {overall_mdedit:.0f}, "
              f"baseline median: {overall_baseline:.0f})\n")

    # Per-task table
    print("## Per-Task Comparison\n")
    print("| Task | Size | mdedit (min/med/max) | baseline (min/med/max) | Savings |")
    print("|------|------|---------------------|----------------------|---------|")
    for r in rows:
        m = r['mdedit']
        b = r['baseline']
        mstr = f"{m['min']}/{m['median']:.0f}/{m['max']}" if m['n'] > 0 else "—"
        bstr = f"{b['min']}/{b['median']:.0f}/{b['max']}" if b['n'] > 0 else "—"
        pct = f"{r['savings_pct']:.0f}%" if b['n'] > 0 else "—"
        wf = " *" if r['is_workflow'] else ""
        print(f"| {r['task']}{wf} | {r['size']} | {mstr} | {bstr} | {pct} |")

    # Tool usage
    print("\n## Tool Usage Frequency\n")
    print("| Condition | Tool | Count |")
    print("|-----------|------|-------|")
    for cond in sorted(tool_usage.keys()):
        for tool, count in sorted(tool_usage[cond].items(),
                                   key=lambda x: -x[1]):
            print(f"| {cond} | {tool} | {count} |")

    # Variance
    print("\n## Variance Comparison\n")
    print("| Condition | Median IQR/Median Ratio |")
    print("|-----------|------------------------|")
    for cond, cv in variance.items():
        print(f"| {cond} | {cv:.3f} |")

    # Failures
    if failures:
        print(f"\n## Failed Runs ({len(failures)})\n")
        for f in failures:
            reason = f['error'] or f['validation_reason']
            print(f"- {f['task']} | {f['condition']} | {f['size']} | "
                  f"rep {f['rep']}: {reason}")

    print("\n---\n*Workflows marked with **")


def main():
    parser = argparse.ArgumentParser(description='Analyze benchmark results')
    parser.add_argument('results_file', type=Path,
                        help='Path to benchmark results JSON')
    parser.add_argument('--format', choices=['text', 'markdown'],
                        default='markdown', help='Output format')
    args = parser.parse_args()

    results = load_results(args.results_file)
    rows = per_task_comparison(results)
    tool_usage = tool_usage_summary(results)
    variance = variance_comparison(results)
    failures = failure_report(results)

    if args.format == 'markdown':
        print_markdown(rows, tool_usage, variance, failures)
    else:
        # Text mode — same content, less formatting
        print_markdown(rows, tool_usage, variance, failures)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Verify analyze.py loads**

```bash
cd tests/mdedit/benchmarks
python3 -c "import analyze; print('analyze.py imports OK')"
```

- [ ] **Step 3: Commit**

```bash
git add tests/mdedit/benchmarks/analyze.py
git commit -m "feat(benchmark): add analysis script (analyze.py)"
```

---

### Task 10: Smoke test — single run per condition

Before running the full 260-run benchmark, validate the harness works end-to-end with a minimal run.

**Files:** No new files — this tests the existing harness.

- [ ] **Step 1: Run a single isolated task, mdedit condition**

```bash
cd tests/mdedit/benchmarks
unset CLAUDECODE
python3 run_benchmarks.py --tasks replace-small --sizes small --conditions mdedit --reps 1 --workers 1
```

Expected: 1 run completes, shows token count, marked valid.

- [ ] **Step 2: Run a single isolated task, baseline condition**

```bash
python3 run_benchmarks.py --tasks replace-small --sizes small --conditions baseline --reps 1 --workers 1
```

Expected: 1 run completes. Note the tool(s) the baseline agent chose.

- [ ] **Step 3: Run a single workflow, both conditions**

```bash
python3 run_benchmarks.py --tasks targeted-read --sizes small --reps 1 --workers 1
```

Expected: 2 runs (mdedit + baseline), both complete.

- [ ] **Step 4: Run analyze.py on the smoke test results**

```bash
python3 analyze.py results/benchmark-*.json
```

Expected: summary table renders with data from the smoke runs.

- [ ] **Step 5: Fix any issues found in smoke testing**

Iterate on prompts, validation, or JSON parsing as needed. Common issues:
- `claude -p --output-format json` may structure token usage differently than expected — adapt `_parse_token_usage`
- System prompt may need adjustment if agents ignore rules or access CLAUDE.md
- Validation may be too strict or too lenient

- [ ] **Step 6: Commit any smoke test fixes**

```bash
git add tests/mdedit/benchmarks/
git commit -m "fix(benchmark): adjustments from smoke testing"
```

---

### Task 11: Full benchmark run

- [ ] **Step 1: Run the full benchmark**

```bash
cd tests/mdedit/benchmarks
unset CLAUDECODE
python3 run_benchmarks.py --reps 5 --model haiku --workers 5
```

Expected: ~260 runs. Monitor for failures.

- [ ] **Step 2: Analyze results**

```bash
python3 analyze.py results/benchmark-<timestamp>.json --format markdown > results/summary.md
```

- [ ] **Step 3: Re-run failures on Sonnet (if any)**

For any task that failed on Haiku, re-run both conditions on Sonnet:

```bash
python3 run_benchmarks.py --tasks <failed-task> --sizes <failed-size> --conditions mdedit,baseline --reps 5 --model sonnet --workers 3
```

- [ ] **Step 4: Review results and commit**

```bash
git add tests/mdedit/benchmarks/results/summary.md
git commit -m "feat(benchmark): initial benchmark results"
```
