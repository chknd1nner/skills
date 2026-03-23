# mdedit v1 — LLM Integration Test Report

**Date:** 2026-03-23
**Method:** 10 Haiku subagents dispatched in parallel, each testing a command group against realistic sample files.
**Total tests:** 132 across all agents (all functional tests passed)

---

## Part 1: CLI Issues

### ISSUE-1: `_preamble` write operations not implemented (CRITICAL)

**Spec says** (Section addressing > Preamble):
> Write operations on `_preamble`: `replace`, `append`, and `prepend` all work on `_preamble` — content is placed after frontmatter, before the first heading.

**Actual behavior:**
```
$ mdedit replace doc.md "_preamble" --content "test"
ERROR: replace does not support _preamble; use a section heading    # exit 4

$ mdedit append doc.md "_preamble" --content "test"
ERROR: append does not yet support _preamble                        # exit 4

$ mdedit prepend doc.md "_preamble" --content "test"
ERROR: prepend does not yet support _preamble                       # exit 4
```

Only `extract` and `delete` work on `_preamble`. The "does not yet" phrasing on append/prepend suggests this is known-incomplete. Replace says "does not support" which sounds more intentional.

**Impact:** LLM workflows that need to modify preamble content (e.g. adding a summary paragraph before the first heading) must use `delete` + `insert` as a workaround, which is lossy and awkward.

---

### ISSUE-2: `frontmatter` requires `show` subcommand (MINOR — spec/CLI mismatch)

**Spec says:**
```
mdedit frontmatter <file>
mdedit frontmatter get <file> <key>
```

**Actual CLI:**
```
$ mdedit frontmatter doc.md
error: unrecognized subcommand 'doc.md'

$ mdedit frontmatter show doc.md    # ← required
FRONTMATTER: doc.md — 5 fields
  ...
```

The `show` subcommand is required but not documented in the spec. The spec's help text section also shows `frontmatter <file> [get|set|delete]` without `show`.

**Impact:** Low — an LLM reading the spec will fail on first attempt but the error message makes the fix obvious. However, the spec should be updated to match, or the CLI should accept the bare form.

---

### ISSUE-3: No fuzzy suggestions on section-not-found (COSMETIC)

When a section is not found, fuzzy suggestions are only shown when there's a close match:
```
$ mdedit extract doc.md "Backgrond"
ERROR: Section "Backgrond" not found in doc.md
Did you mean?
  → Background (H2, line 16), under "Research Notes"
```

But for completely unrelated names, no suggestions appear:
```
$ mdedit extract doc.md "Nonexistent"
ERROR: Section "Nonexistent" not found in doc.md
```

This is actually reasonable behavior (not a bug), but worth noting that the spec's example always shows suggestions.

---

## Part 2: What Works Perfectly

### Read commands — all flawless

| Command | Tests | Notes |
|---------|-------|-------|
| `outline` | 12/12 | Hierarchy, word counts, line ranges, `--max-depth`, `⚠ empty` flags, code fence exclusion |
| `extract` | 20/20 | All addressing modes, `--no-children`, `--to-file`, preamble, empty sections, code fences |
| `search` | 13/13 | Case sensitivity, pipe-delimited highlights, section grouping, special characters, multi-word |
| `stats` | 4/4 | Percentages, `← largest`, `← empty` markers, deep nesting |
| `validate` | 6/6 | Skipped levels, empty sections, duplicate headings, correct exit codes (0 vs 5) |
| `frontmatter show` | 8/8 | All field types, error handling, exit codes |
| `frontmatter get` | 7/7 | Raw value output, arrays, booleans, key-not-found errors |

### Write commands — all functional

| Command | Tests | Notes |
|---------|-------|-------|
| `replace` | 14/14 | `--content`, `--from-file`, stdin, `--preserve-children`, `--dry-run`, no-op detection (exit 10) |
| `append` | 4/4 | `+` prefix on added lines, last-line continuity context, `[end of document]` |
| `prepend` | 4/4 | `+` prefix, first-line continuity context, heading-adjacent placement |
| `insert` | 5/5 | `--after`, `--before`, empty sections, heading level mismatch warnings, `--dry-run` |
| `delete` | 5/5 | `✗` marker, `Was:` prefix, child cascade warnings, `[end of document]` |
| `rename` | 4/4 | Level preservation, level-specific addressing, `--dry-run` |
| `frontmatter set` | 5/5 | String, boolean, JSON array, new field creation, `--dry-run` |
| `frontmatter delete` | 4/4 | Existing field, non-existent key error, `--dry-run` |

### Section addressing — rock solid

| Feature | Status |
|---------|--------|
| Simple name matching (`"Background"`) | Works |
| Level-prefixed (`"## Background"`) | Works |
| Nested path (`"Background/Prior Work"`) | Works |
| Ambiguous match detection (exit 2) | Works — lists all candidates with levels and line numbers |
| Fuzzy suggestions on typo (exit 1) | Works — "Backgrond" → "Background" |
| `_preamble` extract/delete | Works |

### Exit codes — all correct (Haiku agent was wrong)

The replace agent reported exit codes returning 0 for errors. Manual verification shows they are correct:

| Condition | Spec | Actual |
|-----------|------|--------|
| Section not found | 1 | 1 |
| Ambiguous match | 2 | 2 |
| File error | 3 | 3 |
| No content / invalid op | 4 | 4 |
| Validation failures | 5 | 5 |
| No-op (identical content) | 10 | 10 |

---

## Part 3: Instructional Findings

### What worked well for guiding Haiku agents

1. **Binary path + test file paths up front.** Every agent needed this immediately. Putting it at the top of the prompt prevented confusion.

2. **"This is NOT in your training data" disclaimer.** Critical. Without this, models might hallucinate flags or assume familiar tool behavior.

3. **Expected output format with examples.** Showing the exact output format (e.g. `REPLACED: "## Background" (was 12 lines → now 8 lines)`) let agents verify correctness without needing to understand the spec deeply.

4. **"Make a FRESH COPY for each test" instruction.** Essential for write command agents. Without this, tests would corrupt shared files and cascade failures.

5. **Explicit test list with numbered items.** Agents followed the list methodically. Free-form "test everything" instructions would have been less thorough.

6. **Content input mode examples.** Showing all three modes (`--content`, `--from-file`, stdin pipe) prevented agents from guessing syntax.

### What caused friction

1. **Haiku agents invoked the memory system.** Despite being subagents with a focused task, they tried to connect to the continuity-memory system from the parent CLAUDE.md. This wasted tokens but didn't break anything. Subagent prompts should explicitly say "Do not access the memory system."

2. **One agent hallucinated exit code values.** The replace agent reported exit codes as 0 when they were actually 1 and 4. This appears to be a Haiku-level reliability issue with interpreting `echo $?` output. Always verify Haiku-reported exit codes independently.

3. **Stdin testing ambiguity.** `echo "" | mdedit replace ...` sends a newline (content exists), while `< /dev/null mdedit replace ...` sends nothing (triggers no-content error). Agents didn't always distinguish these. Instructions should specify which stdin pattern to use.

4. **The `frontmatter show` vs `frontmatter` discrepancy.** The Haiku agent figured out the correct syntax on its own by trying `--help`, but this cost extra tool calls. If the spec matched the CLI, agents would succeed on the first attempt.

### Recommended LLM instruction template

For teaching an LLM to use mdedit, include:

```
mdedit is a CLI tool for structured markdown editing. Key patterns:

READ:    mdedit outline doc.md
         mdedit extract doc.md "Section Name"
         mdedit search doc.md "query"
         mdedit stats doc.md
         mdedit validate doc.md
         mdedit frontmatter show doc.md
         mdedit frontmatter get doc.md key

WRITE:   mdedit replace doc.md "Section" --content "new content"
         mdedit append doc.md "Section" --content "added content"
         mdedit prepend doc.md "Section" --content "prefix content"
         mdedit insert doc.md --after "Section" --heading "## New" --content "body"
         mdedit delete doc.md "Section"
         mdedit rename doc.md "Section" "New Name"
         mdedit frontmatter set doc.md key value
         mdedit frontmatter delete doc.md key

ADDRESSING: "Name" (any level), "## Name" (H2 only), "Parent/Child" (nested)
CONTENT:    --content "text", --from-file path, or pipe to stdin
SAFETY:     --dry-run on all write commands, --preserve-children on replace
```

---

## Part 4: Test Infrastructure

### Sample files created

| File | Purpose |
|------|---------|
| `frontmatter-doc.md` | Primary test file — 5 frontmatter fields, 8 sections, 3 levels deep |
| `preamble-doc.md` | Content before first heading + frontmatter |
| `large-document.md` | 29 sections, 4 levels deep (H1–H5) |
| `validation-problems.md` | Skipped heading levels, empty sections, duplicate headings |
| `code-fences.md` | Python/Rust code fences with `#` characters inside |
| `minimal.md` | Single heading + content |
| `no-frontmatter.md` | No YAML frontmatter at all |
| `self/multi-level-headings.md` | Same heading text at different levels (ambiguity testing) |
| `self/duplicate-headings.md` | Same heading text at same level (ambiguity testing) |

### Agent configuration

- **Model:** Haiku (claude-haiku-4-5-20251001)
- **Agents:** 10, all running in background in parallel
- **Average completion time:** ~80s per agent
- **Total tokens across all agents:** ~390k
- **Total tool calls across all agents:** ~220
