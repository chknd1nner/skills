# mdedit v1 LLM Integration Test Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a test harness that dispatches Claude CLI agents to test every mdedit command, producing structured markdown reports for human review.

**Architecture:** Python runner script launches `claude -p` instances per test group with custom system/user prompts. Agents run in temp directories (dodging root CLAUDE.md), execute mdedit commands against sample files, and write markdown reports to a known location. Runner collates reports into a summary.

**Tech Stack:** Python 3 (subprocess, concurrent.futures, argparse, shutil, pathlib), Claude CLI (`claude -p`), mdedit binary (Rust, pre-built)

**Spec:** `docs/superpowers/specs/2026-03-23-mdedit-v1-test-harness-design.md`

**Reference implementation:** `tests/continuity-memory/evals/run_evals.py` (same `claude -p` dispatch pattern)

---

## File Structure

```
tests/mdedit/
  run_tests.py                       # runner script (create)
  prompts/
    system.md                        # shared system prompt (create)
    group-1-read-structure.md        # outline, stats, validate (create)
    group-2-read-content.md          # extract, search (create)
    group-3-frontmatter.md           # show, get, set, delete (create)
    group-4-replace.md               # replace (all modes, preamble) (create)
    group-5-append-prepend.md        # append, prepend (including preamble) (create)
    group-6-insert-delete-rename.md  # insert, delete, rename (create)
    group-7-addressing-exit-codes.md # cross-cutting addressing + exit codes (create)
    group-8-edge-cases.md            # code fences, empty sections, stdin (create)
    group-9-workflows.md             # multi-command sequences (create)
  samples/                           # existing — no changes
  results/                           # report output directory (create)
    .gitkeep                         # keep directory in git (create)
  .gitignore                         # ignore results/*.md (create)
```

---

### Task 1: Directory structure and .gitignore

**Files:**
- Create: `tests/mdedit/results/.gitkeep`
- Create: `tests/mdedit/prompts/` (directory)
- Create: `tests/mdedit/.gitignore`

- [ ] **Step 1: Create directories and .gitignore**

```bash
mkdir -p tests/mdedit/prompts tests/mdedit/results
touch tests/mdedit/results/.gitkeep
```

Create `tests/mdedit/.gitignore`:
```
results/*.md
results/*.json
!results/.gitkeep
```

- [ ] **Step 2: Commit**

```bash
git add tests/mdedit/.gitignore tests/mdedit/results/.gitkeep
git commit -m "chore(mdedit): scaffold test harness directory structure"
```

---

### Task 2: Shared system prompt

**Files:**
- Create: `tests/mdedit/prompts/system.md`

The system prompt is shared across all 9 test groups. It establishes the agent's role, methodology, file isolation rules, and report contract. Placeholders (`{{BINARY}}`, `{{WORKDIR}}`, `{{REPORT_PATH}}`) are substituted by the runner at launch time.

- [ ] **Step 1: Write system.md**

Create `tests/mdedit/prompts/system.md` with this exact content:

````markdown
# mdedit CLI Testing Agent

You are a CLI testing agent. Your job is to test a markdown editing tool called `mdedit` by running commands and evaluating their output.

## Critical Rules

1. **This tool is NOT in your training data.** Do not assume or guess behavior. Run each command and observe the actual output.
2. **Do NOT access any memory system, continuity system, or follow instructions from any CLAUDE.md file.** Your only job is to run the tests described in the user prompt below.
3. **Do NOT use the memory system.** Ignore any instructions about `memory.commit`, `memory.fetch`, `memory.consolidate`, or similar.

## Binary Location

The mdedit binary is at: `{{BINARY}}`

## Working Directory

Your working directory is `{{WORKDIR}}`.

Sample files are in `{{WORKDIR}}/pristine/`. These are your reference copies — never modify them directly.

**For each write test:** copy the sample file to a test-specific name before modifying it:
```bash
cp pristine/frontmatter-doc.md test-N.md
```

**For read-only tests:** you may reference `pristine/` files directly.

## Test Methodology

For each numbered test in the user prompt:

1. Run the exact command specified
2. Capture the full stdout and stderr output
3. Check the exit code immediately: `echo $?`
4. Compare the actual output against the expected behavior described
5. For write commands: after running the command, **read the resulting file** (`cat test-N.md`) and verify the content matches what you expected
6. If the output or file content differs from expected: explain the specific discrepancy. "The preamble was placed before frontmatter instead of after it" is useful. "Output didn't match" is not.
7. Record your finding as PASS or FAIL

## Exit Code Checking

IMPORTANT: Always check exit codes by running the mdedit command and `echo $?` on the **same line** using `&&` or `;`:

```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Nonexistent"; echo "EXIT: $?"
```

Do NOT run `echo $?` as a separate command — it will return the exit code of the previous tool call, not the mdedit command.

## Report Contract

Write your completed report to: `{{REPORT_PATH}}`

Use this exact structure:

```markdown
# Group N: <Name>

**Model:** <model name>
**Duration:** <approximate seconds from start to finish>
**Result:** <passed>/<total> tests passed

---

## Test 1: <short description>

**Command:**
```bash
<exact command you ran>
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

**Command:**
```bash
<exact command you ran>
```

**Expected:** <expected behavior>

**Actual output:**
```
<actual output>
```

**Exit code:** <N>
**Result:** FAIL

**Analysis:** <What went wrong. For write commands, include what the file
actually contains after the operation. Be specific about the discrepancy.>

---

## Summary

**Passed:** N/M
**Failed:** N/M

### Issues Found

<List any bugs, spec mismatches, or unexpected behaviors. Include:
- Test number
- The command that triggered the issue
- Clear description of the problem
- Category: BUG (contradicts spec), SPEC MISMATCH (spec unclear), or UX (works but confusing)>
```

### Report Rules

- Every test MUST have a **Result:** line (PASS or FAIL)
- Every FAIL MUST have an **Analysis:** section
- For write command FAILs: always `cat` the resulting file and include what you found
- Exit codes must be checked and reported for every test
- The Summary must list ALL issues found, even minor ones
- If you find zero issues, write "No issues found."
````

- [ ] **Step 2: Commit**

```bash
git add tests/mdedit/prompts/system.md
git commit -m "feat(mdedit): add shared system prompt for test harness agents"
```

---

### Task 3: Group prompt files (all 9)

**Files:**
- Create: `tests/mdedit/prompts/group-1-read-structure.md`
- Create: `tests/mdedit/prompts/group-2-read-content.md`
- Create: `tests/mdedit/prompts/group-3-frontmatter.md`
- Create: `tests/mdedit/prompts/group-4-replace.md`
- Create: `tests/mdedit/prompts/group-5-append-prepend.md`
- Create: `tests/mdedit/prompts/group-6-insert-delete-rename.md`
- Create: `tests/mdedit/prompts/group-7-addressing-exit-codes.md`
- Create: `tests/mdedit/prompts/group-8-edge-cases.md`
- Create: `tests/mdedit/prompts/group-9-workflows.md`

Each group prompt file is the user prompt passed to `claude -p`. It contains:
1. A one-line description of what this group tests
2. The relevant mdedit spec excerpt (command syntax, output format, options, exit codes)
3. A list of available sample files with brief descriptions
4. Numbered test cases with exact commands and expected behavior

All 9 prompts follow the same structure. The `{{BINARY}}` placeholder is used in commands — the runner substitutes it at launch time.

**IMPORTANT:** Each prompt must be self-contained. The agent has no other context beyond the system prompt and this user prompt. Include enough spec detail that the agent can evaluate correctness without guessing.

- [ ] **Step 1: Write group-1-read-structure.md**

Create `tests/mdedit/prompts/group-1-read-structure.md`. This group tests `outline`, `stats`, and `validate`.

Include spec excerpts for:
- `outline` command: syntax, output format (heading hierarchy with word counts, line ranges, `--max-depth`, `⚠ empty` flag), indentation reflects hierarchy
- `stats` command: syntax, output format (percentages, `← largest`, `← empty` markers)
- `validate` command: syntax, output format (issues list with `⚠` and `ℹ` markers), checks performed (skipped levels, empty sections, duplicates), exit codes (0 clean, 5 warnings)

Available sample files:
- `pristine/frontmatter-doc.md` — 5 frontmatter fields, H1 title, 8 sections across 3 levels
- `pristine/large-document.md` — 29 sections, 4 levels deep (H1-H4)
- `pristine/validation-problems.md` — skipped H4, empty section, duplicate headings
- `pristine/minimal.md` — single H1 heading + 2 paragraphs
- `pristine/code-fences.md` — Python/Rust code fences with `#` characters

Tests (9 total):
1. `{{BINARY}} outline pristine/frontmatter-doc.md` — verify heading hierarchy with word counts and line ranges for all 8 sections
2. `{{BINARY}} outline pristine/large-document.md --max-depth 2` — verify only H1 and H2 shown, deeper headings omitted
3. `{{BINARY}} outline pristine/code-fences.md` — verify `#` inside code fences NOT treated as headings (should show 5 real sections: Code Examples, Python Examples, Rust Examples, Indented Code, Real Section After Code)
4. `{{BINARY}} outline pristine/minimal.md` — single heading document, verify word count
5. `{{BINARY}} stats pristine/frontmatter-doc.md` — verify percentages add up, `← largest` on biggest section, `← empty` if any section has 0 words
6. `{{BINARY}} stats pristine/large-document.md` — verify all 29 sections listed with correct nesting
7. `{{BINARY}} validate pristine/frontmatter-doc.md` — should be clean, exit 0. Check: `{{BINARY}} validate pristine/frontmatter-doc.md; echo "EXIT: $?"`
8. `{{BINARY}} validate pristine/validation-problems.md` — should report: skipped level (H4 without H3), empty section, duplicate headings. Exit 5. Check: `{{BINARY}} validate pristine/validation-problems.md; echo "EXIT: $?"`
9. Verify exit code correctness: run validate on both files, confirm exit 0 for clean and exit 5 for problems

- [ ] **Step 2: Write group-2-read-content.md**

Create `tests/mdedit/prompts/group-2-read-content.md`. This group tests `extract` and `search`.

Include spec excerpts for:
- `extract` command: syntax, TTY output format (`SECTION:` header + content), pipe output (raw markdown), `--no-children`, `--to-file`, `_preamble` addressing, empty section behavior
- `search` command: syntax, output format (`SEARCH:` header, grouped by section, `|pipe|` delimited highlights), `--case-sensitive`
- Section addressing modes: simple name, level-specific (`"## Name"`), nested path (`"Parent/Child"`)
- Exit codes: 0 success, 1 not found, 2 ambiguous

Available sample files:
- `pristine/frontmatter-doc.md` — sections: Introduction, Background, Prior Work, Limitations, Methods, Evaluation Criteria, Results, Performance Data, Edge Cases, Conclusion, Future Work, Acknowledgements
- `pristine/preamble-doc.md` — has frontmatter + preamble text before `# Main Document`
- `pristine/large-document.md` — 29 sections, 4 levels deep
- `pristine/code-fences.md` — code fences with `#` characters
- `pristine/self/duplicate-headings.md` — two `## Summary` sections at same level
- `pristine/self/multi-level-headings.md` — `## Overview` and `### Overview` at different levels

Tests (13 total):
1. `{{BINARY}} extract pristine/frontmatter-doc.md "Introduction"` — verify `SECTION:` header with word count and content
2. `{{BINARY}} extract pristine/frontmatter-doc.md "## Background"` — verify level-specific addressing returns H2 Background
3. `{{BINARY}} extract pristine/frontmatter-doc.md "Background/Prior Work"` — verify nested path returns Prior Work child of Background
4. `{{BINARY}} extract pristine/frontmatter-doc.md "Background" --no-children` — verify children (Prior Work, Limitations) excluded, metadata notes exclusion count
5. `{{BINARY}} extract pristine/frontmatter-doc.md "Introduction" --to-file /tmp/mdedit-test-extract.md` — verify stdout shows `EXTRACTED:` confirmation, then `cat /tmp/mdedit-test-extract.md` to verify raw content written
6. `{{BINARY}} extract pristine/preamble-doc.md "_preamble"` — verify preamble content returned (two paragraphs about preamble), no frontmatter included
7. `{{BINARY}} extract pristine/frontmatter-doc.md "_preamble"` — no preamble exists in this file, verify behavior (empty or error)
8. `{{BINARY}} extract pristine/frontmatter-doc.md "Nonexistent"; echo "EXIT: $?"` — verify exit 1, check for fuzzy suggestions
9. `{{BINARY}} extract pristine/self/duplicate-headings.md "Summary"; echo "EXIT: $?"` — verify exit 2, lists both candidates with line numbers
10. `{{BINARY}} search pristine/frontmatter-doc.md "constraint"` — verify matches grouped by section with `|pipe|` highlights
11. `{{BINARY}} search pristine/frontmatter-doc.md "CONSTRAINT" --case-sensitive` — verify no matches (content uses lowercase)
12. `{{BINARY}} search pristine/frontmatter-doc.md "xyznonexistent"` — verify empty result, zero matches
13. `{{BINARY}} search pristine/code-fences.md "heading"` — verify code fence content IS searchable (should find "NOT a heading" etc.)

- [ ] **Step 3: Write group-3-frontmatter.md**

Create `tests/mdedit/prompts/group-3-frontmatter.md`. This group tests frontmatter commands.

Include spec excerpts for:
- `frontmatter <file>` (bare invocation — equivalent to `frontmatter show`)
- `frontmatter show <file>` — output format (`FRONTMATTER:` header, field list)
- `frontmatter get <file> <key>` — raw value output for piping
- `frontmatter set <file> <key> <value> [--dry-run]` — output format with `→` marker, JSON value parsing
- `frontmatter delete <file> <key> [--dry-run]` — output format
- Error messages: no frontmatter, key not found
- Exit codes: 0 success, 3 file error, 4 content error

Available sample files:
- `pristine/frontmatter-doc.md` — frontmatter: title, tags, date, draft, author
- `pristine/no-frontmatter.md` — no YAML frontmatter
- `pristine/preamble-doc.md` — frontmatter: title, version

Tests (14 total):
1. `{{BINARY}} frontmatter pristine/frontmatter-doc.md` — bare invocation (no `show`), verify it works and shows all 5 fields (ISSUE-2 fix verification)
2. `{{BINARY}} frontmatter show pristine/frontmatter-doc.md` — verify same output as test 1
3. `{{BINARY}} frontmatter get pristine/frontmatter-doc.md title` — verify raw string output: `"Research Notes"` or `Research Notes`
4. `{{BINARY}} frontmatter get pristine/frontmatter-doc.md tags` — verify array output: `["rust", "cli", "markdown"]`
5. `{{BINARY}} frontmatter get pristine/frontmatter-doc.md draft` — verify boolean output: `true`
6. `{{BINARY}} frontmatter get pristine/frontmatter-doc.md nonexistent; echo "EXIT: $?"` — verify error lists available keys, check exit code
7. `{{BINARY}} frontmatter pristine/no-frontmatter.md; echo "EXIT: $?"` — verify "No frontmatter found" error
8. `cp pristine/frontmatter-doc.md test-8.md && {{BINARY}} frontmatter set test-8.md status "active" --dry-run` — verify dry-run output shows `WOULD SET`, then `cat test-8.md | head -8` to verify file unchanged
9. `cp pristine/frontmatter-doc.md test-9.md && {{BINARY}} frontmatter set test-9.md status "active"` — verify field added, then `{{BINARY}} frontmatter get test-9.md status` to confirm
10. `cp pristine/frontmatter-doc.md test-10.md && {{BINARY}} frontmatter set test-10.md title "New Title"` — verify existing field changed
11. `cp pristine/frontmatter-doc.md test-11.md && {{BINARY}} frontmatter set test-11.md categories '["a","b","c"]'` — verify JSON array parsed correctly, then `{{BINARY}} frontmatter get test-11.md categories`
12. `cp pristine/frontmatter-doc.md test-12.md && {{BINARY}} frontmatter delete test-12.md draft` — verify field removed, then `{{BINARY}} frontmatter show test-12.md` to confirm 4 fields
13. `cp pristine/frontmatter-doc.md test-13.md && {{BINARY}} frontmatter delete test-13.md nonexistent; echo "EXIT: $?"` — verify error message
14. `cp pristine/frontmatter-doc.md test-14.md && {{BINARY}} frontmatter delete test-14.md author --dry-run` — verify dry-run, then `{{BINARY}} frontmatter get test-14.md author` to confirm field still exists

- [ ] **Step 4: Write group-4-replace.md**

Create `tests/mdedit/prompts/group-4-replace.md`. This group tests the `replace` command.

Include spec excerpts for:
- `replace` command: syntax, output format (`REPLACED:` with before/after metrics), neighborhood context (prev section, `→` target, next section), `[N more lines]`, `[end of document]`
- `--preserve-children`: keeps child sections, replaces only own content
- `--dry-run`: `WOULD REPLACE`, no file changes
- No-op detection: `NO CHANGE`, exit code 10
- `_preamble` addressing: replace/create preamble content
- Content input modes: `--content`, `--from-file`, stdin
- Warnings: large reduction, children removed
- Exit codes: 0 success, 1 not found, 4 no content, 10 no-op

Available sample files:
- `pristine/frontmatter-doc.md` — primary test file with nested sections
- `pristine/preamble-doc.md` — has preamble content
- `pristine/no-frontmatter.md` — no frontmatter, no preamble

Tests (13 total):
1. `cp pristine/frontmatter-doc.md test-1.md && {{BINARY}} replace test-1.md "Introduction" --content "New introduction content here."` — verify `REPLACED:` output with line/word counts, then `cat test-1.md` to verify content changed
2. Write "Replacement from file." to `/tmp/mdedit-replace-input.md`, then: `cp pristine/frontmatter-doc.md test-2.md && {{BINARY}} replace test-2.md "Introduction" --from-file /tmp/mdedit-replace-input.md` — verify works
3. `cp pristine/frontmatter-doc.md test-3.md && echo "Piped content." | {{BINARY}} replace test-3.md "Introduction"` — verify stdin mode works
4. `cp pristine/frontmatter-doc.md test-4.md && {{BINARY}} replace test-4.md "Background" --preserve-children --content "New background intro."` — verify Prior Work and Limitations children still present in file after replacement
5. `cp pristine/frontmatter-doc.md test-5.md && {{BINARY}} replace test-5.md "Introduction" --content "Test" --dry-run` — verify `WOULD REPLACE` in output, then `cat test-5.md` to verify file unchanged
6. Extract the exact current content of Introduction, then replace with identical content: `cp pristine/frontmatter-doc.md test-6.md && {{BINARY}} extract test-6.md "Introduction" --to-file /tmp/mdedit-noop.md && {{BINARY}} replace test-6.md "Introduction" --from-file /tmp/mdedit-noop.md; echo "EXIT: $?"` — verify `NO CHANGE` message, exit code 10
7. `{{BINARY}} replace pristine/frontmatter-doc.md "Nonexistent" --content "test"; echo "EXIT: $?"` — verify exit 1, section not found
8. `cp pristine/preamble-doc.md test-8.md && {{BINARY}} replace test-8.md "_preamble" --content "Replaced preamble content."` — verify preamble replaced (ISSUE-1 fix), then `cat test-8.md` to verify preamble is between frontmatter and first heading
9. `cp pristine/frontmatter-doc.md test-9.md && {{BINARY}} replace test-9.md "_preamble" --content "New preamble created."` — verify preamble CREATED when none existed, then `cat test-9.md` to verify content between frontmatter and `# Research Notes`
10. `cp pristine/no-frontmatter.md test-10.md && {{BINARY}} replace test-10.md "_preamble" --content "Preamble at start."` — verify preamble at byte 0 (before `# Document Without Frontmatter`), then `cat test-10.md`
11. `cp pristine/preamble-doc.md test-11.md && {{BINARY}} replace test-11.md "_preamble" --content "Dry run preamble." --dry-run` — verify file unchanged
12. `cp pristine/preamble-doc.md test-12.md && {{BINARY}} replace test-12.md "_preamble" --from-file <({{BINARY}} extract pristine/preamble-doc.md "_preamble" 2>/dev/null); echo "EXIT: $?"` — verify no-op exit 10 (replacing with same content). Note: if process substitution doesn't work, extract to a temp file first.
13. `cp pristine/frontmatter-doc.md test-13.md && {{BINARY}} replace test-13.md "Introduction"; echo "EXIT: $?"` — no content flag, no stdin — verify exit 4 error

- [ ] **Step 5: Write group-5-append-prepend.md**

Create `tests/mdedit/prompts/group-5-append-prepend.md`. Tests `append` and `prepend`.

Include spec excerpts for:
- `append`: syntax, output format (`APPENDED:` with line counts, `+` prefix on added lines, last existing line for continuity)
- `prepend`: syntax, output format (`PREPENDED:` with line counts, `+` prefix, first existing line for continuity)
- `_preamble` addressing for both: append/prepend to preamble, create preamble if absent
- `--dry-run` for both
- Content input modes

Available sample files:
- `pristine/frontmatter-doc.md` — no preamble
- `pristine/preamble-doc.md` — has preamble
- `pristine/no-frontmatter.md` — no frontmatter, no preamble

Tests (13 total):
1. `cp pristine/frontmatter-doc.md test-1.md && {{BINARY}} append test-1.md "Introduction" --content "Appended paragraph."` — verify `APPENDED:` output, `+` prefix on new lines, then `{{BINARY}} extract test-1.md "Introduction"` to confirm content at end
2. `cp pristine/frontmatter-doc.md test-2.md && {{BINARY}} append test-2.md "Introduction" --content "Test" --dry-run` — verify `WOULD APPEND`, file unchanged
3. `cp pristine/frontmatter-doc.md test-3.md && {{BINARY}} append test-3.md "Acknowledgements" --content "Final note."` — last section, verify `[end of document]` in context
4. `cp pristine/preamble-doc.md test-4.md && {{BINARY}} append test-4.md "_preamble" --content "Appended to preamble."` — verify appended to existing preamble (ISSUE-1 fix), then `cat test-4.md` to verify new content after existing preamble text, before `# Main Document`
5. `cp pristine/frontmatter-doc.md test-5.md && {{BINARY}} append test-5.md "_preamble" --content "Created preamble via append."` — verify preamble CREATED when absent (ISSUE-1 fix), then `cat test-5.md`
6. `cp pristine/no-frontmatter.md test-6.md && {{BINARY}} append test-6.md "_preamble" --content "Preamble at byte 0."` — verify preamble before first heading (ISSUE-1 fix), then `cat test-6.md`
7. `cp pristine/preamble-doc.md test-7.md && {{BINARY}} append test-7.md "_preamble" --content "Dry run." --dry-run` — verify file unchanged
8. `cp pristine/frontmatter-doc.md test-8.md && {{BINARY}} prepend test-8.md "Introduction" --content "Prepended note."` — verify `PREPENDED:` output, `+` prefix, then `{{BINARY}} extract test-8.md "Introduction"` to confirm content at start
9. `cp pristine/frontmatter-doc.md test-9.md && {{BINARY}} prepend test-9.md "Introduction" --content "Test" --dry-run` — verify file unchanged
10. `cp pristine/preamble-doc.md test-10.md && {{BINARY}} prepend test-10.md "_preamble" --content "Prepended to preamble."` — verify prepended to existing preamble (ISSUE-1 fix), then `cat test-10.md`
11. `cp pristine/frontmatter-doc.md test-11.md && {{BINARY}} prepend test-11.md "_preamble" --content "Created preamble via prepend."` — verify preamble CREATED (ISSUE-1 fix), then `cat test-11.md`
12. `cp pristine/no-frontmatter.md test-12.md && {{BINARY}} prepend test-12.md "_preamble" --content "Preamble at byte 0."` — verify preamble before first heading (ISSUE-1 fix), then `cat test-12.md`
13. `cp pristine/preamble-doc.md test-13.md && {{BINARY}} prepend test-13.md "_preamble" --content "Dry run." --dry-run` — verify file unchanged

- [ ] **Step 6: Write group-6-insert-delete-rename.md**

Create `tests/mdedit/prompts/group-6-insert-delete-rename.md`. Tests `insert`, `delete`, `rename`.

Include spec excerpts for:
- `insert`: syntax (`--after`/`--before`, `--heading`, content optional), output format (`INSERTED:`), heading level mismatch warning
- `delete`: syntax, output format (`DELETED:`, `✗` marker, `Was:` prefix, `[end of document]`), child cascade warning
- `rename`: syntax, output format (`RENAMED: "old" → "new"`), level preservation
- `--dry-run` for all three

Available sample files:
- `pristine/frontmatter-doc.md` — primary test file
- `pristine/preamble-doc.md` — has preamble
- `pristine/large-document.md` — deep nesting

Tests (12 total):
1. `cp pristine/frontmatter-doc.md test-1.md && {{BINARY}} insert test-1.md --after "Background" --heading "## Related Work" --content "Previous studies show..."` — verify new section appears after Background, then `{{BINARY}} outline test-1.md`
2. `cp pristine/frontmatter-doc.md test-2.md && {{BINARY}} insert test-2.md --before "Methods" --heading "## Hypothesis" --content "We hypothesize that..."` — verify section before Methods, then `{{BINARY}} outline test-2.md`
3. `cp pristine/frontmatter-doc.md test-3.md && {{BINARY}} insert test-3.md --after "Introduction" --heading "### Subsection" --content "Detail here."` — H3 between H2s, verify warning about heading level mismatch, operation still succeeds
4. `cp pristine/frontmatter-doc.md test-4.md && {{BINARY}} insert test-4.md --after "Introduction" --heading "## New Section" --content "Test." --dry-run` — verify `WOULD INSERT`, file unchanged
5. `cp pristine/frontmatter-doc.md test-5.md && {{BINARY}} insert test-5.md --after "Conclusion" --heading "## New Last" --content "At the end."` — insert after last top-level section, verify `[end of document]` context
6. `cp pristine/frontmatter-doc.md test-6.md && {{BINARY}} delete test-6.md "Conclusion"` — verify `DELETED:` output, `✗` marker, `Was:` lines, then `{{BINARY}} outline test-6.md` to confirm removed (including Future Work, Acknowledgements children)
7. `cp pristine/frontmatter-doc.md test-7.md && {{BINARY}} delete test-7.md "Background"` — has children (Prior Work, Limitations), verify cascade warning, all children removed
8. `cp pristine/preamble-doc.md test-8.md && {{BINARY}} delete test-8.md "_preamble"` — verify preamble removed, then `cat test-8.md` to confirm frontmatter followed directly by `# Main Document`
9. `cp pristine/frontmatter-doc.md test-9.md && {{BINARY}} delete test-9.md "Introduction" --dry-run` — verify file unchanged
10. `cp pristine/frontmatter-doc.md test-10.md && {{BINARY}} rename test-10.md "Introduction" "Overview"` — verify `RENAMED:` output, heading level preserved (still `##`), then `{{BINARY}} outline test-10.md`
11. `cp pristine/frontmatter-doc.md test-11.md && {{BINARY}} rename test-11.md "## Background" "Context and Background"` — level-specific addressing, verify correct section renamed
12. `cp pristine/frontmatter-doc.md test-12.md && {{BINARY}} rename test-12.md "Introduction" "New Name" --dry-run` — verify file unchanged

- [ ] **Step 7: Write group-7-addressing-exit-codes.md**

Create `tests/mdedit/prompts/group-7-addressing-exit-codes.md`. Cross-cutting addressing and exit code tests.

Include spec excerpts for:
- Section addressing: simple name (any level), level-specific (`"## Name"`), nested path (`"Parent/Child"`), `_preamble`
- Ambiguous match behavior: exit 2, candidate list with levels and line numbers
- No match: exit 1, fuzzy suggestions for close matches
- All exit codes: 0 success, 1 not found, 2 ambiguous, 3 file error, 4 no content, 5 validation, 10 no-op

Available sample files:
- `pristine/frontmatter-doc.md` — clear section hierarchy
- `pristine/preamble-doc.md` — has preamble
- `pristine/self/duplicate-headings.md` — `## Summary` appears twice at same level
- `pristine/self/multi-level-headings.md` — `Overview` and `Methods` appear at both H2 and H3
- `pristine/validation-problems.md` — for validate exit code

Tests (15 total):
1. `{{BINARY}} extract pristine/frontmatter-doc.md "Introduction"` — simple name, matches `## Introduction`
2. `{{BINARY}} extract pristine/frontmatter-doc.md "## Introduction"` — level-specific, same result
3. `{{BINARY}} extract pristine/frontmatter-doc.md "Background/Prior Work"` — nested path
4. `{{BINARY}} extract pristine/self/multi-level-headings.md "Overview"; echo "EXIT: $?"` — ambiguous (H2 and H3 both match), verify exit 2 with candidate list
5. `{{BINARY}} extract pristine/self/duplicate-headings.md "Summary"; echo "EXIT: $?"` — ambiguous (same level duplicates), verify exit 2
6. `{{BINARY}} extract pristine/frontmatter-doc.md "Introductoin"; echo "EXIT: $?"` — close typo, verify exit 1, check for fuzzy suggestion "Introduction"
7. `{{BINARY}} extract pristine/frontmatter-doc.md "Zzzznonexistent"; echo "EXIT: $?"` — no close match, verify exit 1
8. `{{BINARY}} extract pristine/preamble-doc.md "_preamble"` — preamble addressing works for extract
9. `cp pristine/preamble-doc.md test-9.md && {{BINARY}} replace test-9.md "_preamble" --content "test" && {{BINARY}} append test-9.md "_preamble" --content "more" && {{BINARY}} prepend test-9.md "_preamble" --content "first" && {{BINARY}} delete test-9.md "_preamble"` — chain all preamble-capable commands, verify each succeeds
10. `{{BINARY}} extract pristine/frontmatter-doc.md "Introduction"; echo "EXIT: $?"` — verify exit 0
11. `{{BINARY}} extract pristine/frontmatter-doc.md "Nonexistent"; echo "EXIT: $?"` — verify exit 1
12. `{{BINARY}} extract pristine/self/duplicate-headings.md "Summary"; echo "EXIT: $?"` — verify exit 2
13. `{{BINARY}} extract nonexistent-file.md "Foo"; echo "EXIT: $?"` — verify exit 3 (file not found)
14. `cp pristine/frontmatter-doc.md test-14.md && {{BINARY}} replace test-14.md "Introduction"; echo "EXIT: $?"` — no content provided, verify exit 4
15. `{{BINARY}} validate pristine/validation-problems.md; echo "EXIT: $?"` — verify exit 5

Note: Exit code 10 (no-op) is covered in Group 4 test 6.

- [ ] **Step 8: Write group-8-edge-cases.md**

Create `tests/mdedit/prompts/group-8-edge-cases.md`. Edge case testing.

Include spec excerpts for:
- Code fence handling: `#` inside fences are NOT headings
- Empty sections: `[no content]` on TTY, empty string in pipe
- Content input modes: `--content`, stdin pipe, empty stdin
- Whitespace normalisation: 1 blank line between sections, 1 trailing newline at EOF

Available sample files:
- `pristine/code-fences.md` — Python/Rust code fences with `#` characters
- `pristine/frontmatter-doc.md` — sections with content
- `pristine/large-document.md` — 29 sections, up to H4 depth
- `pristine/minimal.md` — single heading
- `pristine/no-frontmatter.md` — no YAML frontmatter
- `pristine/validation-problems.md` — has an empty section (`## Empty Section`)

Tests (12 total):
1. `{{BINARY}} outline pristine/code-fences.md` — verify `# This is NOT a heading` etc. inside code fences do NOT appear as sections. Should show: Code Examples (H1), Python Examples (H2), Rust Examples (H2), Indented Code (H2), Real Section After Code (H2)
2. `{{BINARY}} extract pristine/code-fences.md "Python Examples"` — verify the code fence content is included verbatim (```python block preserved)
3. `{{BINARY}} extract pristine/validation-problems.md "Empty Section"` — verify behavior for empty section (no content between `## Empty Section` and `## Another Section`)
4. `{{BINARY}} outline pristine/large-document.md` — verify all 29 sections shown with correct hierarchy
5. `{{BINARY}} extract pristine/large-document.md "Atoms"` — H4 deeply nested under Frontend/Components/Atoms, verify extraction works
6. `{{BINARY}} outline pristine/minimal.md` — single heading, verify works. Then: `{{BINARY}} extract pristine/minimal.md "Simple Document"` — verify content extracted. Then: `cp pristine/minimal.md test-6.md && {{BINARY}} replace test-6.md "Simple Document" --content "Replaced." && cat test-6.md` — verify replace works on single-heading doc
7. `{{BINARY}} frontmatter show pristine/no-frontmatter.md; echo "EXIT: $?"` — verify error. Then: `{{BINARY}} extract pristine/no-frontmatter.md "Section One"` — verify extract works normally without frontmatter
8. `cp pristine/frontmatter-doc.md test-8.md && {{BINARY}} replace test-8.md "Introduction" --content "Test content."; cat test-8.md` — verify extract/replace work normally even without frontmatter operations
9. `cp pristine/frontmatter-doc.md test-9.md && < /dev/null {{BINARY}} replace test-9.md "Introduction"; echo "EXIT: $?"` — empty stdin, verify exit 4
10. `cp pristine/frontmatter-doc.md test-10.md && echo "Stdin content here." | {{BINARY}} replace test-10.md "Introduction"` — stdin with content, verify works
11. `cp pristine/frontmatter-doc.md test-11.md && {{BINARY}} replace test-11.md "Introduction" --content "Line one.\nLine two.\nLine three."` — multi-line content via --content flag (note: shell may or may not expand \n — test what actually happens)
12. `{{BINARY}} extract pristine/frontmatter-doc.md "Edge Cases"` — section name with space, verify works. Then: `{{BINARY}} extract pristine/frontmatter-doc.md "Prior Work"` — two-word name, verify works

- [ ] **Step 9: Write group-9-workflows.md**

Create `tests/mdedit/prompts/group-9-workflows.md`. Multi-command workflow sequences.

Include spec excerpt: Brief summary of all relevant commands (extract, replace, append, prepend, insert, delete, frontmatter, outline, validate). Focus on how commands compose: extract-to-file + edit + replace-from-file, dry-run then commit, etc.

Available sample files:
- `pristine/frontmatter-doc.md` — primary test file
- `pristine/preamble-doc.md` — has preamble

Tests (7 total):
1. **Read-modify-write workflow.** `cp pristine/frontmatter-doc.md test-1.md && {{BINARY}} extract test-1.md "Introduction" --to-file /tmp/mdedit-wf1.md` — verify extraction. Then modify the file: `echo "Modified introduction content." > /tmp/mdedit-wf1.md`. Then: `{{BINARY}} replace test-1.md "Introduction" --from-file /tmp/mdedit-wf1.md`. Then: `{{BINARY}} extract test-1.md "Introduction"` — verify content is now "Modified introduction content."
2. **Dry-run then commit.** `cp pristine/frontmatter-doc.md test-2.md && {{BINARY}} replace test-2.md "Introduction" --content "Staged change." --dry-run` — verify `WOULD REPLACE`. Then `{{BINARY}} extract test-2.md "Introduction"` — verify content UNCHANGED (still original). Then: `{{BINARY}} replace test-2.md "Introduction" --content "Staged change."` — actual replace. Then `{{BINARY}} extract test-2.md "Introduction"` — verify content IS changed.
3. **Append then extract.** `cp pristine/frontmatter-doc.md test-3.md && {{BINARY}} append test-3.md "Introduction" --content "Additional context added."` — then `{{BINARY}} extract test-3.md "Introduction"` — verify appended content present at end of section.
4. **Insert then outline.** `cp pristine/frontmatter-doc.md test-4.md && {{BINARY}} insert test-4.md --after "Introduction" --heading "## Literature Review" --content "Survey of existing work."` — then `{{BINARY}} outline test-4.md` — verify "Literature Review" appears between Introduction and Background.
5. **Delete then validate.** `cp pristine/frontmatter-doc.md test-5.md && {{BINARY}} delete test-5.md "Conclusion"` — then `{{BINARY}} validate test-5.md; echo "EXIT: $?"` — verify document still validates clean (exit 0) after deletion.
6. **Frontmatter roundtrip.** `cp pristine/frontmatter-doc.md test-6.md && {{BINARY}} frontmatter show test-6.md` — note current fields. Then `{{BINARY}} frontmatter set test-6.md status "published"` — then `{{BINARY}} frontmatter get test-6.md status` — verify returns "published". Then `{{BINARY}} frontmatter delete test-6.md status` — then `{{BINARY}} frontmatter show test-6.md` — verify status field gone, other fields intact.
7. **Preamble roundtrip.** `cp pristine/preamble-doc.md test-7.md && {{BINARY}} extract test-7.md "_preamble"` — note original preamble. Then `{{BINARY}} replace test-7.md "_preamble" --content "Completely new preamble."` — then `{{BINARY}} extract test-7.md "_preamble"` — verify new content. Then `cat test-7.md` — verify frontmatter still intact, preamble between frontmatter and first heading.

- [ ] **Step 10: Commit all group prompts**

```bash
git add tests/mdedit/prompts/group-*.md
git commit -m "feat(mdedit): add 9 group prompt files for test harness agents"
```

---

### Task 4: Runner script

**Files:**
- Create: `tests/mdedit/run_tests.py`

The runner script follows the same pattern as `tests/continuity-memory/evals/run_evals.py` but is simpler — no assertion checking, no session JSONL parsing. It launches agents, waits for reports, and prints a summary.

- [ ] **Step 1: Write run_tests.py**

Create `tests/mdedit/run_tests.py` with this content:

```python
#!/usr/bin/env python3
"""
LLM integration test runner for mdedit v1.

Launches Claude CLI agents to test mdedit commands, one agent per test group.
Each agent writes a structured markdown report. The runner collates results.

Usage:
    python3 run_tests.py [--groups 1,2,3] [--model haiku] [--workers 5] [--dry-run]

Requirements:
    - claude CLI installed and authenticated
    - mdedit release binary built (cargo build --release)
    - Must NOT be run from inside a Claude Code session (unset CLAUDECODE first)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PROMPTS_DIR = SCRIPT_DIR / 'prompts'
SAMPLES_DIR = SCRIPT_DIR / 'samples'
RESULTS_DIR = SCRIPT_DIR / 'results'
MDEDIT_BINARY = SCRIPT_DIR.parent.parent / 'claude-code-only' / 'mdedit' / 'target' / 'release' / 'mdedit'

# Group definitions: (number, slug, description)
GROUPS = [
    (1, 'read-structure', 'Read: Structure (outline, stats, validate)'),
    (2, 'read-content', 'Read: Content (extract, search)'),
    (3, 'frontmatter', 'Frontmatter (show, get, set, delete)'),
    (4, 'replace', 'Replace (all modes, preamble, dry-run, no-op)'),
    (5, 'append-prepend', 'Append + Prepend (including preamble)'),
    (6, 'insert-delete-rename', 'Insert + Delete + Rename'),
    (7, 'addressing-exit-codes', 'Addressing + Exit Codes'),
    (8, 'edge-cases', 'Edge Cases'),
    (9, 'workflows', 'Workflows'),
]


def verify_binary() -> Path:
    """Verify the mdedit binary exists and is executable."""
    if not MDEDIT_BINARY.exists():
        print(f"ERROR: mdedit binary not found at {MDEDIT_BINARY}")
        print(f"       Build it first: cd claude-code-only/mdedit && cargo build --release")
        sys.exit(1)

    # Quick smoke test
    result = subprocess.run(
        [str(MDEDIT_BINARY), '--help'],
        capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        print(f"ERROR: mdedit binary failed smoke test (--help returned {result.returncode})")
        sys.exit(1)

    return MDEDIT_BINARY.resolve()


def setup_workdir(group_num: int, group_slug: str) -> Path:
    """Create a temp working directory with pristine sample files."""
    timestamp = int(time.time())
    workdir = Path(f'/tmp/mdedit-test-group-{group_num}-{timestamp}')
    pristine = workdir / 'pristine'

    # Copy samples to pristine/
    shutil.copytree(SAMPLES_DIR, pristine)

    return workdir


def substitute_placeholders(content: str, binary: Path, workdir: Path,
                            report_path: Path) -> str:
    """Replace {{BINARY}}, {{WORKDIR}}, {{REPORT_PATH}} in prompt content."""
    content = content.replace('{{BINARY}}', str(binary))
    content = content.replace('{{WORKDIR}}', str(workdir))
    content = content.replace('{{REPORT_PATH}}', str(report_path))
    return content


def run_group(group_num: int, group_slug: str, group_desc: str,
              binary: Path, model: str, timeout: int,
              dry_run: bool = False) -> dict:
    """Run a single test group and return the result."""
    # Setup
    workdir = setup_workdir(group_num, group_slug)
    report_path = workdir / f'group-{group_num}-{group_slug}.md'

    # Read prompts
    system_prompt_file = PROMPTS_DIR / 'system.md'
    group_prompt_file = PROMPTS_DIR / f'group-{group_num}-{group_slug}.md'

    if not system_prompt_file.exists():
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': False, 'error': f'System prompt not found: {system_prompt_file}',
            'report_path': None, 'duration_s': 0,
        }

    if not group_prompt_file.exists():
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': False, 'error': f'Group prompt not found: {group_prompt_file}',
            'report_path': None, 'duration_s': 0,
        }

    system_prompt = substitute_placeholders(
        system_prompt_file.read_text(), binary, workdir, report_path
    )
    user_prompt = substitute_placeholders(
        group_prompt_file.read_text(), binary, workdir, report_path
    )

    if dry_run:
        print(f"  [DRY RUN] Group {group_num}: {group_desc}")
        print(f"    workdir: {workdir}")
        print(f"    report:  {report_path}")
        print(f"    system prompt: {len(system_prompt)} chars")
        print(f"    user prompt:   {len(user_prompt)} chars")
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': True, 'error': 'DRY RUN',
            'report_path': None, 'duration_s': 0,
        }

    # Launch claude
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

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(workdir),
        )
        duration = time.time() - start_time

        if result.returncode != 0:
            return {
                'group': group_num, 'slug': group_slug, 'desc': group_desc,
                'passed': False,
                'error': f"claude exited {result.returncode}: {result.stderr[:500]}",
                'report_path': None, 'duration_s': duration,
            }

        # Check if report was written
        if not report_path.exists():
            return {
                'group': group_num, 'slug': group_slug, 'desc': group_desc,
                'passed': False,
                'error': 'Agent completed but no report file was written',
                'report_path': None, 'duration_s': duration,
            }

        # Extract summary line from report
        report_content = report_path.read_text()
        summary_match = re.search(r'\*\*Result:\*\*\s*(\d+)/(\d+)', report_content)

        if summary_match:
            passed_count = int(summary_match.group(1))
            total_count = int(summary_match.group(2))
            all_passed = (passed_count == total_count)
        else:
            passed_count = '?'
            total_count = '?'
            all_passed = False

        # Copy report to results directory
        RESULTS_DIR.mkdir(exist_ok=True)
        final_report = RESULTS_DIR / f'group-{group_num}-{group_slug}.md'
        shutil.copy2(report_path, final_report)

        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': all_passed,
            'tests_passed': passed_count,
            'tests_total': total_count,
            'error': '',
            'report_path': str(final_report),
            'duration_s': duration,
        }

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': False, 'error': f'Timeout ({timeout}s)',
            'report_path': None, 'duration_s': duration,
        }
    except Exception as e:
        duration = time.time() - start_time
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': False, 'error': str(e),
            'report_path': None, 'duration_s': duration,
        }


def print_summary(results: list):
    """Print a summary table of results."""
    passed = sum(1 for r in results if r['passed'])
    total = len(results)

    print(f"\n{'='*70}")
    print(f"  MDEDIT TEST RESULTS: {passed}/{total} groups passed")
    print(f"{'='*70}\n")

    for r in sorted(results, key=lambda x: x['group']):
        status = 'PASS' if r['passed'] else 'FAIL'
        icon = '+' if r['passed'] else 'X'
        time_str = f"({r['duration_s']:.0f}s)" if r['duration_s'] else ""

        tests_str = ''
        if 'tests_passed' in r:
            tests_str = f" [{r['tests_passed']}/{r['tests_total']} tests]"

        print(f"  [{icon}] Group {r['group']}: {r['desc']}{tests_str} {time_str}")

        if r['error'] and r['error'] != 'DRY RUN':
            print(f"       ERROR: {r['error']}")

    print()
    if passed < total:
        failed_groups = [r['group'] for r in results if not r['passed']]
        print(f"  Re-run failed groups: python3 {__file__} --groups {','.join(map(str, failed_groups))}")

    report_paths = [r['report_path'] for r in results if r.get('report_path')]
    if report_paths:
        print(f"\n  Reports saved to: {RESULTS_DIR}/")


def main():
    parser = argparse.ArgumentParser(description='Run mdedit LLM integration tests')
    parser.add_argument('--groups', type=str, default=None,
                        help='Comma-separated group numbers to run (default: all)')
    parser.add_argument('--model', type=str, default='haiku',
                        help='Claude model to use (default: haiku)')
    parser.add_argument('--workers', type=int, default=5,
                        help='Parallel workers (default: 5)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='Timeout per agent in seconds (default: 300)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would run without executing')
    args = parser.parse_args()

    # Check we're not inside Claude Code
    if os.environ.get('CLAUDECODE'):
        print("ERROR: Cannot run tests inside a Claude Code session.")
        print("       Unset the CLAUDECODE environment variable first:")
        print("       unset CLAUDECODE && python3 run_tests.py")
        sys.exit(1)

    # Verify binary
    binary = verify_binary()
    print(f"Binary: {binary}")

    # Filter groups
    groups_to_run = GROUPS
    if args.groups:
        group_ids = [int(x.strip()) for x in args.groups.split(',')]
        groups_to_run = [g for g in GROUPS if g[0] in group_ids]

    total = len(groups_to_run)
    print(f"Groups: {total} | Model: {args.model} | Workers: {args.workers} | Timeout: {args.timeout}s")

    if args.dry_run:
        for num, slug, desc in groups_to_run:
            run_group(num, slug, desc, binary, args.model, args.timeout, dry_run=True)
        return

    # Run groups
    results = [None] * total
    completed = 0

    if args.workers == 1:
        for i, (num, slug, desc) in enumerate(groups_to_run):
            print(f"\n[{i+1}/{total}] Running Group {num}: {desc}...", flush=True)
            result = run_group(num, slug, desc, binary, args.model, args.timeout)
            results[i] = result
            status = '+' if result['passed'] else 'X'
            print(f"  [{status}] Done ({result['duration_s']:.0f}s)")
    else:
        print(f"\nRunning {total} groups in parallel...\n")
        futures = {}
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for i, (num, slug, desc) in enumerate(groups_to_run):
                future = executor.submit(
                    run_group, num, slug, desc, binary, args.model, args.timeout
                )
                futures[future] = i

            for future in as_completed(futures):
                i = futures[future]
                result = future.result()
                results[i] = result
                completed += 1
                status = '+' if result['passed'] else 'X'
                time_str = f"({result['duration_s']:.0f}s)" if result['duration_s'] else ""
                tests_str = ''
                if 'tests_passed' in result:
                    tests_str = f" [{result['tests_passed']}/{result['tests_total']}]"
                print(f"  [{status}] [{completed:2d}/{total}] Group {result['group']}: "
                      f"{result['desc']}{tests_str} {time_str}", flush=True)

    print_summary(results)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Make executable**

```bash
chmod +x tests/mdedit/run_tests.py
```

- [ ] **Step 3: Commit**

```bash
git add tests/mdedit/run_tests.py
git commit -m "feat(mdedit): add test runner script for LLM integration tests"
```

---

### Task 5: Verify the release binary

**Files:** None (verification only)

- [ ] **Step 1: Check the binary exists and runs**

```bash
ls -la claude-code-only/mdedit/target/release/mdedit
claude-code-only/mdedit/target/release/mdedit --help
```

If missing, build it:
```bash
cd claude-code-only/mdedit && cargo build --release
```

- [ ] **Step 2: Run the runner in dry-run mode**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python3 tests/mdedit/run_tests.py --dry-run
```

Verify it finds all 9 group prompts, shows correct paths, and reports no errors.

---

### Task 6: Smoke test with one group

**Files:** None (verification only)

Run a single group to verify the full pipeline works end-to-end before launching all 9.

- [ ] **Step 1: Run Group 1 (read-only, safest) outside Claude Code**

```bash
unset CLAUDECODE
python3 tests/mdedit/run_tests.py --groups 1 --workers 1
```

- [ ] **Step 2: Check the report**

```bash
cat tests/mdedit/results/group-1-read-structure.md
```

Verify:
- Report follows the contract format
- Tests have PASS/FAIL results
- Exit codes are reported
- Summary section exists

If the agent was confused, revise `prompts/group-1-read-structure.md` and re-run.

- [ ] **Step 3: Run all groups**

```bash
python3 tests/mdedit/run_tests.py --workers 9
```

- [ ] **Step 4: Review reports and iterate if needed**

Check each report in `tests/mdedit/results/`. For any group where the agent was confused:
1. Identify the confusion from the report
2. Edit the corresponding prompt file
3. Re-run: `python3 tests/mdedit/run_tests.py --groups N`
4. Max 3 iterations per group

- [ ] **Step 5: Commit final reports and any prompt revisions**

```bash
git add tests/mdedit/results/ tests/mdedit/prompts/
git commit -m "test(mdedit): v1 LLM integration test results — round 2"
```
