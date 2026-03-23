# Group 9: Workflows

Test multi-command sequences that simulate real editing workflows: read-modify-write cycles, dry-run then commit, append-then-verify, insert-then-outline, delete-then-validate, frontmatter roundtrip, and preamble roundtrip.

---

## Spec Reference

### `extract` Command

```
mdedit extract <file> <section> [--no-children] [--to-file <path>]
```

TTY output shows `SECTION:` header + content. Pipe/`--to-file` gives raw markdown. `--to-file` shows `EXTRACTED:` confirmation with the output file path.

### `replace` Command

```
mdedit replace <file> <section> [--content|--from-file|stdin] [--preserve-children] [--dry-run]
```

Output: `REPLACED:` with before/after metrics. Dry-run: `WOULD REPLACE` (no file modification). No-op: `NO CHANGE`, exit 10.

### `append` Command

```
mdedit append <file> <section> [--content|--from-file|stdin] [--dry-run]
```

Output: `APPENDED:`, `+` prefix on new lines. Shows last existing line for continuity.

### `prepend` Command

```
mdedit prepend <file> <section> [--content|--from-file|stdin] [--dry-run]
```

Output: `PREPENDED:`, `+` prefix on new lines. Shows first existing line after prepended content.

### `insert` Command

```
mdedit insert <file> --after|--before <section> --heading <heading> [--content|--from-file|stdin] [--dry-run]
```

Output: `INSERTED:`. `--heading` must include `#` prefix (e.g., `"## Literature Review"`). Content is optional — you can insert a heading-only section. Warning for heading level mismatch with neighbors.

### `delete` Command

```
mdedit delete <file> <section> [--dry-run]
```

Output: `DELETED:`, `✗` marker, `Was:` lines showing deleted content. Children cascade (all child sections are deleted too). Warning for child sections deleted.

### `rename` Command

```
mdedit rename <file> <section> <new-name> [--dry-run]
```

Output: `RENAMED: "old" → "new"`. Level preserved.

### `validate` Command

```
mdedit validate <file>
```

Output when clean:
```
VALID: document.md — 7 sections, max depth 3, no issues
```

Checks performed: skipped heading levels, empty sections, duplicate heading text at same level.
Exit code: `5` for `⚠` warnings, `0` for clean/`ℹ` only.

### `outline` Command

```
mdedit outline <file> [--max-depth <N>]
```

Output shows heading hierarchy with word counts and line ranges. Empty sections flagged with `⚠ empty`.

### `frontmatter` Command

```
mdedit frontmatter <file>               # show all fields
mdedit frontmatter get <file> <key>      # get single field (raw value)
mdedit frontmatter set <file> <key> <value> [--dry-run]  # set field
mdedit frontmatter delete <file> <key> [--dry-run]       # delete field
```

Show: `FRONTMATTER:` header with all fields listed. Get: raw value only. Set: `FRONTMATTER SET:` with before/after. Delete: `FRONTMATTER DELETED:`.

### Content Input Modes

| Mode | Flag | Description |
|---|---|---|
| Inline | `--content <text>` | Content passed as argument string |
| File | `--from-file <path>` | Content read from a file on disk |
| Stdin | (no flag) | Content read from stdin when stdin is not a TTY |

### `_preamble` Addressing

`_preamble` addresses content before the first heading (after frontmatter). Frontmatter is NOT part of `_preamble`. Works with `extract`, `replace`, `append`, `prepend`, and `delete`.

### Whitespace Normalisation

After any write operation: exactly one blank line between sections, one trailing newline at EOF.

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

---

## Available Sample Files

- `pristine/frontmatter-doc.md` — 5 frontmatter fields (title, tags, date, draft, author), H1 "Research Notes", sections including Introduction, Background (with Prior Work, Limitations), Methods (with Evaluation Criteria), Results (with Performance Data, Edge Cases), Conclusion (with Future Work, Acknowledgements). Clean structure, no validation issues.
- `pristine/preamble-doc.md` — Has frontmatter and preamble content between frontmatter and the first heading. Used for `_preamble` roundtrip testing.

---

## Tests

### Test 1: Read-modify-write workflow

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-1.md
{{BINARY}} extract test-1.md "Introduction" --to-file /tmp/mdedit-wf1.md
cat /tmp/mdedit-wf1.md
echo "Modified introduction content." > /tmp/mdedit-wf1.md
{{BINARY}} replace test-1.md "Introduction" --from-file /tmp/mdedit-wf1.md
{{BINARY}} extract test-1.md "Introduction"
```

**Expected:**
1. `extract --to-file` outputs `EXTRACTED:` confirmation and writes raw markdown to `/tmp/mdedit-wf1.md`. Exit code `0`.
2. `cat /tmp/mdedit-wf1.md` shows the original Introduction content (raw markdown, no `SECTION:` header).
3. After overwriting the file with "Modified introduction content.", `replace --from-file` reads from the modified file and outputs `REPLACED:` with before/after metrics. Exit code `0`.
4. Final `extract` shows "Modified introduction content." as the Introduction — confirming the full read-modify-write cycle worked. The rest of the document (Background, Methods, etc.) must be unchanged.

### Test 2: Dry-run then commit

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-2.md
{{BINARY}} replace test-2.md "Introduction" --content "Staged change." --dry-run
{{BINARY}} extract test-2.md "Introduction"
{{BINARY}} replace test-2.md "Introduction" --content "Staged change."
{{BINARY}} extract test-2.md "Introduction"
```

**Expected:**
1. `replace --dry-run` outputs `WOULD REPLACE` with before/after metrics. Exit code `0`. The file is NOT modified.
2. First `extract` after dry-run shows the ORIGINAL Introduction content — proving dry-run did not modify the file.
3. `replace` without `--dry-run` outputs `REPLACED:` with before/after metrics. Exit code `0`. The file IS modified.
4. Second `extract` shows "Staged change." — proving the real replace worked.

### Test 3: Append then extract

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-3.md
{{BINARY}} append test-3.md "Introduction" --content "Additional context added."
{{BINARY}} extract test-3.md "Introduction"
```

**Expected:**
1. `append` outputs `APPENDED:` with `+` prefix on the new line(s). Shows last existing line for continuity. Exit code `0`.
2. `extract` shows the Introduction content with the original text FOLLOWED BY "Additional context added." at the end. The original content is preserved — append adds to it, does not replace.

### Test 4: Insert then outline

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-4.md
{{BINARY}} insert test-4.md --after "Introduction" --heading "## Literature Review" --content "Survey of existing work."
{{BINARY}} outline test-4.md
```

**Expected:**
1. `insert --after "Introduction"` outputs `INSERTED:`. A new `## Literature Review` section is created immediately after `## Introduction` with content "Survey of existing work." Exit code `0`.
2. `outline` shows the document structure with "Literature Review" appearing between "Introduction" and "Background". The heading level is H2 (matching `## Literature Review` from the `--heading` flag). All other sections remain in their original positions.

### Test 5: Delete then validate

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-5.md
{{BINARY}} delete test-5.md "Conclusion"
{{BINARY}} validate test-5.md; echo "EXIT: $?"
```

**Expected:**
1. `delete` outputs `DELETED:` with `✗` marker and `Was:` lines showing the deleted content. If Conclusion has child sections (Future Work, Acknowledgements), they are also deleted (cascade), and a warning about child sections deleted is shown. Exit code `0`.
2. `validate` should show `VALID:` — the document structure is still clean after removing Conclusion and its children. No skipped levels, no empty sections, no duplicate headings should result from this deletion. Exit code `0`.

### Test 6: Frontmatter roundtrip

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-6.md
{{BINARY}} frontmatter show test-6.md
{{BINARY}} frontmatter set test-6.md status "published"
{{BINARY}} frontmatter get test-6.md status
{{BINARY}} frontmatter delete test-6.md status
{{BINARY}} frontmatter show test-6.md
```

**Expected:**
1. `frontmatter show` outputs `FRONTMATTER:` header with all existing fields (title, tags, date, draft, author). Exit code `0`.
2. `frontmatter set` outputs `FRONTMATTER SET:` showing the before/after for the status field (before: not present, after: "published"). Exit code `0`.
3. `frontmatter get status` outputs the raw value `published` (no header, no formatting). Exit code `0`.
4. `frontmatter delete status` outputs `FRONTMATTER DELETED:` confirming the status field was removed. Exit code `0`.
5. Final `frontmatter show` outputs the same fields as step 1 — the status field is gone, but title, tags, date, draft, and author remain intact. The roundtrip (add → verify → remove → verify) is clean.

### Test 7: Preamble roundtrip

**Commands:**
```bash
cp pristine/preamble-doc.md test-7.md
{{BINARY}} extract test-7.md "_preamble"
{{BINARY}} replace test-7.md "_preamble" --content "Completely new preamble."
{{BINARY}} extract test-7.md "_preamble"
cat test-7.md
```

**Expected:**
1. First `extract _preamble` shows the original preamble content (text between frontmatter closing `---` and first heading). Exit code `0`.
2. `replace _preamble` outputs `REPLACED:` with before/after metrics. Exit code `0`.
3. Second `extract _preamble` shows "Completely new preamble." — confirming the preamble was replaced.
4. `cat test-7.md` shows the full file. Verify:
   - Frontmatter is still intact at the top (between `---` delimiters)
   - "Completely new preamble." appears after the frontmatter closing `---` and before the first heading
   - The first heading and all subsequent sections are unchanged
   - Whitespace normalisation is correct: one blank line between preamble and first heading, one trailing newline at EOF
