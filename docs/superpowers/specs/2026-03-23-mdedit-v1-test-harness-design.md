# mdedit v1 — LLM Integration Test Harness Design

Pre-merge acceptance testing for the mdedit CLI tool. Verifies that an LLM can successfully use every mdedit command by dispatching Claude CLI instances that execute tests and report findings.

## Context

mdedit v1 is feature-complete on `feat/mdedit-v1`. A first round of LLM integration testing (10 Haiku agents, 132 tests) identified three issues:

- **ISSUE-1 (CRITICAL):** `_preamble` write operations not implemented — now fixed
- **ISSUE-2 (MINOR):** `frontmatter` bare invocation required `show` subcommand — now fixed
- **ISSUE-3 (COSMETIC):** Fuzzy suggestions only on close matches — deemed reasonable

All fixes have been committed with 24 new integration tests. This second round is a full regression test confirming the fixes and validating everything works before merging to main.

### Lessons from Round 1

The first test round used subagents dispatched from within Claude Code. Key findings that shape this design:

1. **CLAUDE.md contamination.** Subagents inherited the root CLAUDE.md and wasted tokens trying to connect to the memory system. Solution: launch agents via `claude -p` with `cwd` set to the test folder, which has no CLAUDE.md.
2. **Prompt advice that worked.** Binary path + test file paths up front; "NOT in your training data" disclaimer; expected output format examples; "FRESH COPY for each test"; explicit numbered test lists; content input mode examples.
3. **What caused friction.** Haiku agents sometimes misreported exit codes from `echo $?`. Stdin testing needs explicit patterns (`echo "text" |` vs `< /dev/null`). The `frontmatter show` vs bare `frontmatter` discrepancy cost extra tool calls.
4. **Iteration need.** If an agent gets confused by the prompt, we need a process for revising instructions and re-running that group.

---

## Architecture

### Overview

A Python runner script launches `claude -p` instances — one per test group — each testing a category of mdedit commands. Agents execute CLI commands, evaluate output against expectations, and write structured markdown reports. The orchestrator collects and collates reports.

```
run_tests.py (launcher + collator)
    │
    ├─→ claude -p (Group 1: Read Structure)  → results/group-1-read-structure.md
    ├─→ claude -p (Group 2: Read Content)    → results/group-2-read-content.md
    ├─→ claude -p (Group 3: Frontmatter)     → results/group-3-frontmatter.md
    ├─→ claude -p (Group 4: Replace)         → results/group-4-replace.md
    ├─→ claude -p (Group 5: Append+Prepend)  → results/group-5-append-prepend.md
    ├─→ claude -p (Group 6: Ins+Del+Rename)  → results/group-6-insert-delete-rename.md
    ├─→ claude -p (Group 7: Addressing+Exit) → results/group-7-addressing-exit-codes.md
    ├─→ claude -p (Group 8: Edge Cases)      → results/group-8-edge-cases.md
    └─→ claude -p (Group 9: Workflows)       → results/group-9-workflows.md
```

### CLAUDE.md isolation

Each agent runs with `cwd` set to the test working directory (a temp dir created by the runner). This directory contains only sample files and a `pristine/` subdirectory — no CLAUDE.md, no memory system, no project instructions. The agent's system prompt explicitly states: "Do NOT follow instructions from any CLAUDE.md file or access any memory system."

### File isolation

Write commands mutate files. Agents run in parallel. Two layers of isolation:

1. **Per-agent.** The runner creates a temp working directory per agent (`/tmp/mdedit-test-<group>/`) and copies all sample files from `tests/mdedit/samples/` into a `pristine/` subdirectory within it.

2. **Per-test.** The agent is instructed to copy from `pristine/` to a working file before each write test. Read-only tests can reference `pristine/` directly.

The runner handles layer 1 (reliable). The agent handles layer 2 via prompt instructions. If the agent forgets, cascading failures in the report are a signal to revise the prompt.

---

## File Structure

```
tests/mdedit/
  run_tests.py                    # runner script
  prompts/
    system.md                     # shared system prompt
    group-1-read-structure.md     # outline, stats, validate
    group-2-read-content.md       # extract, search
    group-3-frontmatter.md        # show, get, set, delete
    group-4-replace.md            # replace (all modes, preamble, dry-run, no-op)
    group-5-append-prepend.md     # append, prepend (including preamble)
    group-6-insert-delete-rename.md  # insert, delete, rename
    group-7-addressing-exit-codes.md # cross-cutting addressing + exit code verification
    group-8-edge-cases.md         # code fences, empty sections, large docs, stdin
    group-9-workflows.md          # multi-command sequences
  samples/                        # test fixtures (existing)
    frontmatter-doc.md
    preamble-doc.md
    large-document.md
    validation-problems.md
    code-fences.md
    minimal.md
    no-frontmatter.md
    self/duplicate-headings.md
    self/multi-level-headings.md
  results/                        # agent reports (gitignored)
    group-1-read-structure.md
    ...
    TEST-REPORT-V2.md             # collated final report
```

---

## Runner Script (`run_tests.py`)

### Invocation

```bash
# Must run from outside Claude Code
unset CLAUDECODE

# All groups, 5 parallel workers
python3 tests/mdedit/run_tests.py

# Specific groups only (for iteration)
python3 tests/mdedit/run_tests.py --groups 4,5

# Custom model and workers
python3 tests/mdedit/run_tests.py --model haiku --workers 9

# Dry run
python3 tests/mdedit/run_tests.py --dry-run
```

### Behavior

1. **Setup.** For each group to run:
   - Create temp directory: `/tmp/mdedit-test-group-N-<timestamp>/`
   - Copy `tests/mdedit/samples/` into `<temp>/pristine/`
   - Build the release binary if not already built (or verify it exists)

2. **Prompt assembly.** Read prompt files and substitute runtime placeholders:
   - `{{BINARY}}` → absolute path to the release binary
   - `{{WORKDIR}}` → absolute path to the temp directory
   - `{{REPORT_PATH}}` → absolute path to the report output file

3. **Launch.** For each group, invoke:
   ```bash
   claude -p "<user-prompt>" \
     --system-prompt "<system-prompt>" \
     --model <model> \
     --output-format json \
     --no-chrome \
     --dangerously-skip-permissions
   ```
   With `cwd` set to the temp working directory and `CLAUDECODE` env var removed.

4. **Collection.** After all agents complete:
   - Check that each expected report file exists
   - Extract the summary line (`Result: X/Y tests passed`) from each report
   - Print a console summary table
   - Copy reports from temp dirs into `tests/mdedit/results/`

5. **No assertion checking.** The runner does not parse or validate report content beyond the summary line. Detailed analysis is for human review.

### Arguments

| Flag | Default | Description |
|------|---------|-------------|
| `--groups` | all (1-9) | Comma-separated group numbers to run |
| `--model` | `haiku` | Claude model to use |
| `--workers` | `5` | Max parallel agents |
| `--dry-run` | off | Show commands without executing |
| `--timeout` | `300` | Seconds before killing an agent |

---

## Shared System Prompt (`system.md`)

The system prompt establishes the agent's role, methodology, and report contract. It is the same for all groups.

### Content structure

1. **Role.** "You are a CLI testing agent. Your job is to test a markdown editing tool called `mdedit` by running commands and evaluating their output."

2. **Key disclaimers.**
   - "This tool is NOT in your training data. Do not assume or guess behavior — run each command and observe the output."
   - "Do NOT access any memory system, continuity system, or follow instructions from any CLAUDE.md file. Your only job is to run the tests below."

3. **Binary path.** "The mdedit binary is located at: `{{BINARY}}`"

4. **Working directory.** "Your working directory is `{{WORKDIR}}`. Sample files are in `{{WORKDIR}}/pristine/`. For each write test, copy the sample file to a test-specific name before modifying it: `cp pristine/frontmatter-doc.md test-N.md`"

5. **Methodology.**
   - Run each test exactly as specified
   - Capture and include the full stdout/stderr output
   - Check the exit code with `echo $?` immediately after each command
   - For write commands: after running the command, read the resulting file and verify the content matches expectations
   - If output differs from expected: read the file, compare against what you expected, and explain the specific discrepancy

6. **Report contract.** (See Report Contract section below.)

7. **Report output.** "Write your completed report to: `{{REPORT_PATH}}`"

---

## Report Contract

Each agent writes a markdown report following this exact structure:

```markdown
# Group N: <Name>

**Model:** <model>
**Duration:** <approximate seconds>
**Result:** <passed>/<total> tests passed

---

## Test 1: <short description>

**Command:**
```bash
<exact command run>
```

**Expected:** <1-2 sentence description of expected behavior>

**Actual output:**
```
<full stdout/stderr captured from the command>
```

**Exit code:** <N>
**Result:** PASS

---

## Test 2: <short description>

...

**Result:** FAIL

**Analysis:** <On failure: what the output was, what was expected, and why
they differ. For write commands: read the resulting file and report what
the file actually contains vs what was expected. Be specific — "the
preamble content was placed before the frontmatter instead of after it"
is useful; "output didn't match" is not.>

---

## Summary

**Passed:** N/M
**Failed:** N/M

### Issues Found

<List any bugs, spec mismatches, or unexpected behaviors discovered.
Include the test number, the command, and a clear description of the
problem. Distinguish between:
- BUG: tool behavior contradicts the spec
- SPEC MISMATCH: spec is unclear or ambiguous
- UX: tool works but output is confusing or unhelpful>
```

### Report rules

- Every test must have a Result line (PASS or FAIL)
- Every FAIL must have an Analysis section explaining the discrepancy
- For write command FAILs: always read the resulting file and include what you found
- Exit codes must be checked and reported for every test
- The Summary section must list all issues found, even minor ones

---

## Test Groups

Each group's prompt file contains: the relevant spec excerpt, the list of sample files available, and the numbered test cases.

### Group 1: Read — Structure (`outline`, `stats`, `validate`)

**Sample files:** `frontmatter-doc.md`, `large-document.md`, `validation-problems.md`, `minimal.md`, `code-fences.md`

**Tests:**

1. `outline` on `frontmatter-doc.md` — verify heading hierarchy, word counts, line ranges
2. `outline --max-depth 2` on `large-document.md` — verify truncation at depth 2
3. `outline` on `code-fences.md` — verify `#` inside code fences is NOT treated as headings
4. `outline` on `minimal.md` — single heading document
5. `stats` on `frontmatter-doc.md` — verify percentages, `largest` and `empty` markers
6. `stats` on `large-document.md` — verify deep nesting stats
7. `validate` on `frontmatter-doc.md` — should be clean (exit 0)
8. `validate` on `validation-problems.md` — should report skipped levels, empty sections, duplicates (exit 5)
9. `validate` exit code check — verify exit 0 for clean, exit 5 for problems

### Group 2: Read — Content (`extract`, `search`)

**Sample files:** `frontmatter-doc.md`, `preamble-doc.md`, `large-document.md`, `code-fences.md`

**Tests:**

1. `extract` simple section name from `frontmatter-doc.md`
2. `extract` with level-specific addressing (`"## Section"`)
3. `extract` with nested path (`"Parent/Child"`)
4. `extract --no-children` — verify children excluded, metadata notes exclusion
5. `extract --to-file /tmp/test-extract.md` — verify file written, stdout shows confirmation only
6. `extract "_preamble"` from `preamble-doc.md` — verify preamble content only, no frontmatter
7. `extract "_preamble"` from `frontmatter-doc.md` — no preamble exists, verify error or empty
8. `extract` non-existent section — verify exit 1 and fuzzy suggestions
9. `extract` ambiguous section from `self/duplicate-headings.md` — verify exit 2 and candidate list
10. `search` case-insensitive on `frontmatter-doc.md` — verify match grouping, pipe-delimited highlights
11. `search --case-sensitive` — verify case sensitivity works
12. `search` for text that doesn't exist — verify empty result
13. `search` in `code-fences.md` — verify code fence content is searchable

### Group 3: Frontmatter (`show`, `get`, `set`, `delete`)

**Sample files:** `frontmatter-doc.md`, `no-frontmatter.md`, `preamble-doc.md`

**Tests:**

1. `frontmatter frontmatter-doc.md` (bare invocation, no `show`) — verify this works (ISSUE-2 fix)
2. `frontmatter show frontmatter-doc.md` — verify same output as bare invocation
3. `frontmatter get frontmatter-doc.md title` — verify raw value output (no metadata wrapper)
4. `frontmatter get frontmatter-doc.md tags` — verify array output
5. `frontmatter get frontmatter-doc.md draft` — verify boolean output
6. `frontmatter get frontmatter-doc.md nonexistent` — verify error message lists available keys
7. `frontmatter no-frontmatter.md` — verify "No frontmatter found" error
8. `frontmatter set` new field — verify field added, `--dry-run` first then actual
9. `frontmatter set` existing field — verify value changed
10. `frontmatter set` JSON array value — verify parsed as array
11. `frontmatter delete` existing field — verify field removed
12. `frontmatter delete` non-existent key — verify error
13. `frontmatter set --dry-run` — verify file unchanged
14. `frontmatter delete --dry-run` — verify file unchanged

### Group 4: Replace

**Sample files:** `frontmatter-doc.md`, `preamble-doc.md`, `no-frontmatter.md`

**Tests:**

1. `replace` with `--content` — verify content replaced, neighborhood output correct
2. `replace` with `--from-file` — write content to temp file, replace from it
3. `replace` with stdin pipe — `echo "new content" | mdedit replace ...`
4. `replace --preserve-children` — verify children intact, only own content replaced
5. `replace --dry-run` — verify file unchanged, output shows `WOULD REPLACE`
6. `replace` with identical content — verify no-op exit code 10, `NO CHANGE` message
7. `replace` non-existent section — verify exit 1
8. `replace "_preamble"` on `preamble-doc.md` — verify preamble content replaced (ISSUE-1 fix)
9. `replace "_preamble"` on `frontmatter-doc.md` (no existing preamble) — verify preamble created
10. `replace "_preamble"` on `no-frontmatter.md` — verify preamble at byte 0
11. `replace "_preamble" --dry-run` — verify file unchanged
12. `replace "_preamble"` no-op — verify exit code 10
13. `replace` without any content flag (no stdin) — verify exit 4, error message

### Group 5: Append + Prepend

**Sample files:** `frontmatter-doc.md`, `preamble-doc.md`, `no-frontmatter.md`

**Tests:**

1. `append` with `--content` — verify content added at end, `+` prefix in output
2. `append --dry-run` — verify file unchanged, `WOULD APPEND` output
3. `append` to last section — verify `[end of document]` context
4. `append "_preamble"` on `preamble-doc.md` — verify appended to existing preamble (ISSUE-1 fix)
5. `append "_preamble"` on `frontmatter-doc.md` — verify preamble created when absent (ISSUE-1 fix)
6. `append "_preamble"` on `no-frontmatter.md` — verify preamble at byte 0 (ISSUE-1 fix)
7. `append "_preamble" --dry-run` — verify file unchanged
8. `prepend` with `--content` — verify content added at start, `+` prefix in output
9. `prepend --dry-run` — verify file unchanged
10. `prepend "_preamble"` on `preamble-doc.md` — verify prepended to existing preamble (ISSUE-1 fix)
11. `prepend "_preamble"` on `frontmatter-doc.md` — verify preamble created when absent (ISSUE-1 fix)
12. `prepend "_preamble"` on `no-frontmatter.md` — verify preamble at byte 0 (ISSUE-1 fix)
13. `prepend "_preamble" --dry-run` — verify file unchanged

### Group 6: Insert + Delete + Rename

**Sample files:** `frontmatter-doc.md`, `preamble-doc.md`, `large-document.md`

**Tests:**

1. `insert --after` with content — verify section created at correct position
2. `insert --before` with content — verify section created before target
3. `insert` with heading level mismatch — verify warning emitted but operation succeeds
4. `insert --dry-run` — verify file unchanged
5. `insert` into empty section — verify correct placement
6. `delete` section — verify removed, `Was:` prefix, `[end of document]` if last
7. `delete` section with children — verify cascade warning, all children removed
8. `delete "_preamble"` on `preamble-doc.md` — verify preamble removed
9. `delete --dry-run` — verify file unchanged
10. `rename` section — verify heading text changed, level preserved
11. `rename` with level-specific addressing — verify correct section renamed
12. `rename --dry-run` — verify file unchanged

### Group 7: Addressing + Exit Codes

**Sample files:** `frontmatter-doc.md`, `preamble-doc.md`, `self/duplicate-headings.md`, `self/multi-level-headings.md`

**Tests:**

1. Simple name addressing — `extract "SectionName"` matches any level
2. Level-specific addressing — `extract "## SectionName"` matches only H2
3. Nested path addressing — `extract "Parent/Child"` matches correct child
4. Ambiguous match — section name exists at multiple levels, verify exit 2 and candidate list
5. Ambiguous match — same heading text at same level in `duplicate-headings.md`, verify exit 2
6. No match with close typo — verify exit 1 and fuzzy suggestions
7. No match with unrelated name — verify exit 1 (suggestions may or may not appear)
8. `_preamble` addressing — verify works with `extract`, `replace`, `append`, `prepend`, `delete`
9. Exit code 0 — successful operation
10. Exit code 1 — section not found
11. Exit code 2 — ambiguous match
12. Exit code 3 — file not found (`mdedit extract nonexistent.md "Foo"`)
13. Exit code 4 — no content provided for write command
14. Exit code 5 — `validate` on file with issues
15. Exit code 10 — no-op replace with identical content

### Group 8: Edge Cases

**Sample files:** `code-fences.md`, `frontmatter-doc.md`, `large-document.md`, `minimal.md`, `no-frontmatter.md`

**Tests:**

1. Code fences with `#` characters — `outline` should not count them as headings
2. Code fences with `#` characters — `extract` on a section containing code should preserve fence content
3. Empty section — `extract` should return `[no content]` or empty
4. Large document (29 sections) — `outline` should handle all sections correctly
5. Large document — `extract` deeply nested section (H4 or H5)
6. Minimal document (single heading) — all commands should work
7. No frontmatter — `frontmatter show` should error correctly
8. No frontmatter — `extract`, `replace` etc. should work normally on content
9. Stdin empty (`< /dev/null mdedit replace ...`) — verify exit 4 error
10. Stdin with content (`echo "text" | mdedit replace ...`) — verify works
11. Multi-line `--content` — verify content with newlines handled correctly
12. Special characters in section names — quotes, parentheses, etc.

### Group 9: Workflows

**Sample files:** `frontmatter-doc.md`, `preamble-doc.md`

**Tests:**

1. **Read-modify-write.** `extract --to-file` → modify the file → `replace --from-file` → `extract` again to verify
2. **Dry-run then commit.** `replace --dry-run` → verify output → `replace` (actual) → verify file changed
3. **Append then extract.** `append` content → `extract` section → verify appended content present
4. **Insert then outline.** `insert --after` → `outline` → verify new section appears in correct position
5. **Delete then validate.** Create a file with known structure → `delete` a section → `validate` → verify clean
6. **Frontmatter workflow.** `frontmatter show` → `frontmatter set` → `frontmatter get` → verify roundtrip
7. **Preamble workflow.** `extract _preamble` → `replace _preamble` with new content → `extract _preamble` → verify new content

---

## Iteration Loop

The methodology accounts for agents getting confused by their prompts.

### Process

**Round 1:** Launch all 9 groups in parallel. Collect reports.

**Triage:** The orchestrator reviews each report for confusion signals:

| Signal | Meaning |
|--------|---------|
| Agent tried wrong command syntax | Spec excerpt is unclear or incomplete |
| Agent skipped tests | Instructions ambiguous about what to do |
| Report doesn't follow contract format | Contract description needs examples |
| Agent reported errors that are prompt misunderstandings | Wording needs clarification |
| Cascading write test failures | Agent forgot to copy from `pristine/` |
| Agent tried to access memory system | Isolation disclaimer needs strengthening |

**Round 2 (if needed):** For confused groups only:
1. Diagnose the confusion from the report
2. Edit the specific prompt file (e.g. `prompts/group-4-replace.md`)
3. Re-run just that group: `python3 run_tests.py --groups 4`
4. Check the new report

**Round 3 (max):** If an agent is still confused after two prompt revisions, that itself is a finding — the spec or CLI is unclear enough that a model can't use it after instruction, which is a valuable signal for documentation quality.

### Prompt revision guidelines

When revising a prompt after a confused report:
- Add an explicit example of the exact command and expected output for the test that failed
- If the agent used wrong syntax, add a "Common mistakes" section listing what NOT to do
- If the agent forgot to copy from `pristine/`, bold the instruction and add a per-test reminder
- If the report format was wrong, add a filled-in example entry to the system prompt

---

## Collation

After all groups pass (or after max iterations), the orchestrator produces `TEST-REPORT-V2.md`:

1. **Run metadata.** Date, model, number of groups, total tests, iteration count
2. **Summary table.** Pass/fail per group with test counts
3. **Regression check.** Confirm the three Round 1 issues are resolved
4. **New issues.** Any bugs, spec mismatches, or UX problems discovered
5. **Prompt iteration notes.** Which groups needed prompt revision and what was changed (useful for the mdedit instruction template)
6. **Comparison with Round 1.** What improved, what regressed, what's new

---

## Implementation Notes

### Binary path

The release binary is at `claude-code-only/mdedit/target/release/mdedit`. The runner should verify it exists and is recent (check mtime or run `mdedit --help` to validate). If not found, print instructions to build: `cd claude-code-only/mdedit && cargo build --release`.

### Model selection

Default to Haiku for cost efficiency. The runner accepts `--model` to override. Round 1 used Haiku successfully — the model is capable enough for executing CLI commands and evaluating output. If specific groups show Haiku-level reliability issues (e.g. misreporting exit codes), those groups can be re-run with Sonnet.

### Timeout

Default 300 seconds per agent. Agents that exceed this are killed and reported as failures. Round 1 averaged ~80 seconds per agent, so 300 seconds provides generous headroom.

### Parallelism

Default 5 workers. With 9 groups, this means two waves. All groups are independent — no ordering constraints. Use `--workers 9` to run all in parallel if desired.

### Environment

The runner must be invoked outside Claude Code (`unset CLAUDECODE`). It uses `subprocess.run` to launch `claude -p` processes, same pattern as the continuity-memory eval runner.
