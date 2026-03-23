# Group 7: Addressing + Exit Codes

Test section addressing modes (name, level-qualified, nested path, `_preamble`) and verify all exit codes (0–5) are returned correctly.

---

## Spec Reference

### Section Addressing

All commands that take a `<section>` argument resolve it using these rules:

| Input | Matches |
|---|---|
| `"Background"` | Any heading with text "Background", any level |
| `"## Background"` | Only H2 headings with text "Background" |
| `"Background/Prior Work"` | "Prior Work" that is a child of "Background" |

Matching is exact (case-sensitive) on the heading text.

`_preamble` addresses content before the first heading (after frontmatter). Frontmatter is NOT part of `_preamble`. If no frontmatter, `_preamble` starts at byte 0.

### Ambiguous Match

If multiple headings match, the operation fails:

```
ERROR: "Background" matches 2 sections in doc.md
  → ## Background (H2, line 20)
  → ### Background (H3, line 89, under "## Related Work")
Disambiguate with "## Background" or "Related Work/Background"
```

Exit code: `2`

### No Match

If no heading matches, fuzzy suggestions are provided:

```
ERROR: Section "Backgrond" not found in doc.md
Did you mean?
  → ## Background (H2, line 20)
  → ## Background and Motivation (H2, line 45)
```

Exit code: `1`

### Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success — operation completed |
| `1` | Section not found |
| `2` | Ambiguous section match |
| `3` | File error (not found, not readable, not writable) |
| `4` | Content error (no content provided, `--from-file` not found) |
| `5` | Validation failures (`validate` command) |
| `10` | No-op (content identical, nothing changed) |

### `extract` Command

```
mdedit extract <file> <section> [--no-children] [--to-file <path>]
```

TTY output shows `SECTION:` header + content. Pipe/`--to-file` gives raw markdown. `--no-children` excludes children. `--to-file` shows `EXTRACTED:` confirmation.

### `replace` Command

```
mdedit replace <file> <section> [--content|--from-file|stdin] [--preserve-children] [--dry-run]
```

Output: `REPLACED:` with before/after metrics. No-op: `NO CHANGE`, exit 10.

### `append` Command

```
mdedit append <file> <section> [--content|--from-file|stdin] [--dry-run]
```

Output: `APPENDED:` output, `+` prefix on new lines.

### `prepend` Command

```
mdedit prepend <file> <section> [--content|--from-file|stdin] [--dry-run]
```

Output: `PREPENDED:` output, `+` prefix on new lines.

### `delete` Command

```
mdedit delete <file> <section> [--dry-run]
```

Output: `DELETED:`, `✗` marker, `Was:` lines. Children cascade.

### `validate` Command

```
mdedit validate <file>
```

Checks skipped levels, empty sections, duplicate headings. Exit `5` for `⚠` warnings, `0` for clean/`ℹ` only.

### Content Input Modes

All write commands accept content via three mechanisms:

| Mode | Flag | Description |
|---|---|---|
| Inline | `--content <text>` | Content passed as argument string |
| File | `--from-file <path>` | Content read from a file on disk |
| Stdin | (no flag) | Content read from stdin when stdin is not a TTY |

If none provided: `ERROR: No content provided`. Exit code: `4`.

---

## Available Sample Files

- `pristine/frontmatter-doc.md` — 5 frontmatter fields (title, tags, date, draft, author), H1 title "Research Notes", 8 sections across 3 levels (H1, H2, H3). Sections include Introduction, Background (with children Prior Work, Limitations), Methods (with child Evaluation Criteria), Results (with children Performance Data, Edge Cases), Conclusion (with child Future Work, Acknowledgements). Clean structure.
- `pristine/preamble-doc.md` — Has preamble content between frontmatter and first heading. Used for `_preamble` addressing tests.
- `pristine/self/duplicate-headings.md` — Contains `## Summary` appearing twice at the same level. Used for ambiguous match (exit 2) tests.
- `pristine/self/multi-level-headings.md` — `Overview` and `Methods` appear at both H2 and H3 levels. Used for ambiguous match (exit 2) tests across different heading levels.
- `pristine/validation-problems.md` — Has intentional issues: skipped heading level (H4 under H2), empty section, duplicate headings. Used for validate exit code 5 test.

---

## Tests

### Test 1: Simple name addressing

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Introduction"
```

**Expected:** Matches `## Introduction` by heading text alone (no level prefix needed). Output shows `SECTION:` header followed by the Introduction section content. Exit code `0`.

### Test 2: Level-qualified addressing

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "## Introduction"
```

**Expected:** The `## Introduction` level-qualified form matches the same H2 heading as Test 1. Output is identical to Test 1 — same `SECTION:` header and content. Exit code `0`.

### Test 3: Nested path addressing

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Background/Prior Work"
```

**Expected:** Matches `### Prior Work` that is a child of `## Background`. Output shows the Prior Work section content. This verifies parent/child path resolution. Exit code `0`.

### Test 4: Ambiguous match across levels — exit 2

**Command:**
```bash
{{BINARY}} extract pristine/self/multi-level-headings.md "Overview"; echo "EXIT: $?"
```

**Expected:** "Overview" appears at both H2 and H3 levels. The command must fail with an `ERROR:` message listing both candidates (showing heading level and line number for each). The error message should suggest disambiguation using `"## Overview"` or a nested path form. Exit code must be `2`.

### Test 5: Ambiguous match at same level — exit 2

**Command:**
```bash
{{BINARY}} extract pristine/self/duplicate-headings.md "Summary"; echo "EXIT: $?"
```

**Expected:** `## Summary` appears twice at the same level. The command must fail with an `ERROR:` message listing both candidate sections with their line numbers. Exit code must be `2`.

### Test 6: Close typo — exit 1 with fuzzy suggestion

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Introductoin"; echo "EXIT: $?"
```

**Expected:** No heading matches "Introductoin" exactly. The command must fail with an `ERROR:` message like `Section "Introductoin" not found`. A "Did you mean?" section should appear suggesting `## Introduction` (fuzzy match). Exit code must be `1`.

### Test 7: No close match — exit 1

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Zzzznonexistent"; echo "EXIT: $?"
```

**Expected:** No heading matches and no close fuzzy match exists. The command must fail with an `ERROR:` message about the section not being found. It may or may not show fuzzy suggestions (if it does, they will be distant matches). Exit code must be `1`.

### Test 8: Preamble addressing with extract

**Command:**
```bash
{{BINARY}} extract pristine/preamble-doc.md "_preamble"
```

**Expected:** Extracts the content between the frontmatter closing `---` and the first heading. The output should contain the preamble text (not the frontmatter YAML, not the first heading). Exit code `0`.

### Test 9: Preamble addressing across all write commands

**Commands:**
```bash
cp pristine/preamble-doc.md test-9.md
{{BINARY}} replace test-9.md "_preamble" --content "Replaced preamble."
{{BINARY}} append test-9.md "_preamble" --content "Appended to preamble."
{{BINARY}} prepend test-9.md "_preamble" --content "Prepended to preamble."
{{BINARY}} delete test-9.md "_preamble"
```

**Expected:** Each command in sequence should succeed (exit `0`):
1. `replace` outputs `REPLACED:` — preamble content is now "Replaced preamble."
2. `append` outputs `APPENDED:` — preamble content is now "Replaced preamble." followed by "Appended to preamble."
3. `prepend` outputs `PREPENDED:` — "Prepended to preamble." is now before the other preamble content
4. `delete` outputs `DELETED:` — preamble content is removed

After each step, verify with `cat test-9.md` that the frontmatter remains intact and the first heading is unchanged. After delete, there should be no content between the frontmatter closing `---` and the first heading.

### Test 10: Exit code 0 — success

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Introduction"; echo "EXIT: $?"
```

**Expected:** Successful extraction. Exit code must be exactly `0`.

### Test 11: Exit code 1 — section not found

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Nonexistent"; echo "EXIT: $?"
```

**Expected:** Section "Nonexistent" does not exist in the file. Error message about section not found. Exit code must be exactly `1`.

### Test 12: Exit code 2 — ambiguous match

**Command:**
```bash
{{BINARY}} extract pristine/self/duplicate-headings.md "Summary"; echo "EXIT: $?"
```

**Expected:** "Summary" matches multiple headings. Error message listing candidates. Exit code must be exactly `2`.

### Test 13: Exit code 3 — file not found

**Command:**
```bash
{{BINARY}} extract nonexistent-file.md "Foo"; echo "EXIT: $?"
```

**Expected:** The file `nonexistent-file.md` does not exist. Error message about file not found / not readable. Exit code must be exactly `3`.

### Test 14: Exit code 4 — no content provided

**Command:**
```bash
cp pristine/frontmatter-doc.md test-14.md
< /dev/null {{BINARY}} replace test-14.md "Introduction"; echo "EXIT: $?"
```

**Expected:** The `replace` command requires content via `--content`, `--from-file`, or stdin. With stdin redirected from `/dev/null` and no flags, no content is provided. Error message about no content provided. Exit code must be exactly `4`.

### Test 15: Exit code 5 — validation failures

**Command:**
```bash
{{BINARY}} validate pristine/validation-problems.md; echo "EXIT: $?"
```

**Expected:** The file has validation issues (skipped heading level, empty section). Output shows `INVALID:` with `⚠` warnings. Exit code must be exactly `5`.
