# Group 3: Frontmatter

Test the frontmatter subcommands: `show`, `get`, `set`, and `delete`, including dry-run behavior and error handling.

---

## Spec Reference

### Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Section not found |
| `2` | Ambiguous section match |
| `3` | File error |
| `4` | Content error (no content provided) |
| `5` | Validation failures |
| `10` | No-op |

### `frontmatter` Commands

```
mdedit frontmatter <file>              # same as frontmatter show
mdedit frontmatter show <file>         # show all fields
mdedit frontmatter get <file> <key>    # raw value output
mdedit frontmatter set <file> <key> <value> [--dry-run]
mdedit frontmatter delete <file> <key> [--dry-run]
```

**Show output** (also the default when no subcommand is given):
```
FRONTMATTER: document.md — 4 fields

  title: "My Document"
  tags: ["rust", "cli", "markdown"]
  date: "2026-03-17"
  draft: true
```

**Get output:** Pure value only. No metadata, no field name prefix. Examples:
- String field: `"My Document"` or `My Document`
- Array field: `["rust", "cli", "markdown"]`
- Boolean field: `true`

**Set output:**
```
FRONTMATTER SET: tags (was ["rust", "cli"] → now ["rust", "cli", "llm"])

---
title: "My Document"
→ tags: ["rust", "cli", "llm"]
date: "2026-03-17"
---
```
The changed field is marked with `→` prefix. The full frontmatter block is shown after the change summary.

**Delete output:**
```
FRONTMATTER DELETED: draft

---
title: "My Document"
tags: ["rust", "cli"]
date: "2026-03-17"
---
```
The deleted field is removed from the displayed frontmatter block.

**Dry-run behavior:**
- `--dry-run` flag on `set`: output prefix changes to `WOULD SET` instead of `FRONTMATTER SET`. No file changes are made.
- `--dry-run` flag on `delete`: output prefix changes to `WOULD DELETE` instead of `FRONTMATTER DELETED`. No file changes are made.

**Error cases:**
- No frontmatter in file: error message "No frontmatter found" (or similar).
- Key not found on `get`: error message listing available keys (e.g., "Key not found (available keys: title, tags, date, draft, author)").

**Value parsing:** Values passed to `set` are parsed as JSON if valid JSON, otherwise treated as plain strings.

---

## Available Sample Files

- `pristine/frontmatter-doc.md` — Frontmatter fields: `title: "Research Notes"`, `tags: ["rust", "cli", "markdown"]`, `date: "2026-03-17"`, `draft: true`, `author: "Test User"`. Has 5 fields total.
- `pristine/no-frontmatter.md` — No YAML frontmatter at all. Just an H1 heading and two H2 sections.
- `pristine/preamble-doc.md` — Frontmatter fields: `title: "Preamble Test"`, `version: 1`. Has 2 fields.

---

## Tests

### Test 1: Bare frontmatter invocation (no subcommand)

**Command:**
```bash
{{BINARY}} frontmatter pristine/frontmatter-doc.md
```

**Expected:** Output starts with `FRONTMATTER: frontmatter-doc.md` header showing "5 fields". All 5 fields are listed: `title: "Research Notes"`, `tags: ["rust", "cli", "markdown"]`, `date: "2026-03-17"`, `draft: true`, `author: "Test User"`. The bare `frontmatter` command (without `show`) should behave identically to `frontmatter show`.

### Test 2: Explicit frontmatter show

**Command:**
```bash
{{BINARY}} frontmatter show pristine/frontmatter-doc.md
```

**Expected:** Output is identical to Test 1. Same `FRONTMATTER:` header, same 5 fields listed. This confirms that `frontmatter show` and bare `frontmatter` produce the same output.

### Test 3: Get string field

**Command:**
```bash
{{BINARY}} frontmatter get pristine/frontmatter-doc.md title
```

**Expected:** Output is the raw value only — `"Research Notes"` or `Research Notes`. No field name prefix, no metadata header, no other decoration. Just the value.

### Test 4: Get array field

**Command:**
```bash
{{BINARY}} frontmatter get pristine/frontmatter-doc.md tags
```

**Expected:** Output is the raw array value: `["rust", "cli", "markdown"]`. No field name prefix or metadata.

### Test 5: Get boolean field

**Command:**
```bash
{{BINARY}} frontmatter get pristine/frontmatter-doc.md draft
```

**Expected:** Output is the raw boolean value: `true`. No field name prefix or metadata.

### Test 6: Get nonexistent key

**Command:**
```bash
{{BINARY}} frontmatter get pristine/frontmatter-doc.md nonexistent; echo "EXIT: $?"
```

**Expected:** Error output indicates the key was not found. The error message should list the available keys (title, tags, date, draft, author) so the user knows what keys exist. Check the exit code — it should be non-zero (not `0`).

### Test 7: Frontmatter on file without frontmatter

**Command:**
```bash
{{BINARY}} frontmatter pristine/no-frontmatter.md; echo "EXIT: $?"
```

**Expected:** Error output indicates "No frontmatter found" or similar message. The file `no-frontmatter.md` starts directly with `# Document Without Frontmatter` and has no `---` delimited YAML block. Check the exit code — it should be non-zero.

### Test 8: Set with --dry-run

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-8.md && {{BINARY}} frontmatter set test-8.md status "active" --dry-run
```

Then verify file was NOT modified:
```bash
cat test-8.md | head -8
```

**Expected:** The set command output shows `WOULD SET` prefix (not `FRONTMATTER SET`), indicating dry-run mode. The output shows the new field `status` being set to `"active"` and displays the frontmatter block with the change marked. After the command, `cat test-8.md | head -8` shows the original frontmatter unchanged — `status` field does NOT appear in the file. The file is identical to the pristine copy.

### Test 9: Set new field (actual write)

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-9.md && {{BINARY}} frontmatter set test-9.md status "active"
```

Then verify:
```bash
{{BINARY}} frontmatter get test-9.md status
```

**Expected:** The set command output shows `FRONTMATTER SET:` confirming the field was added. Then `frontmatter get test-9.md status` returns the raw value `"active"` or `active`, confirming the field was actually written to the file.

### Test 10: Set existing field (overwrite)

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-10.md && {{BINARY}} frontmatter set test-10.md title "New Title"
```

Then verify:
```bash
{{BINARY}} frontmatter get test-10.md title
```

**Expected:** The set command output shows `FRONTMATTER SET: title` with the old value `"Research Notes"` and new value `"New Title"` in the change summary (e.g., `was "Research Notes" → now "New Title"`). The confirmation get command returns `"New Title"` or `New Title`.

### Test 11: Set JSON array value

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-11.md && {{BINARY}} frontmatter set test-11.md categories '["a","b","c"]'
```

Then verify:
```bash
{{BINARY}} frontmatter get test-11.md categories
```

**Expected:** The value `'["a","b","c"]'` is valid JSON and should be parsed as a JSON array, not stored as a plain string. The set command confirms the field was added. The get command returns `["a", "b", "c"]` (or `["a","b","c"]`) — an array, not the string literal `'["a","b","c"]'`.

### Test 12: Delete existing field

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-12.md && {{BINARY}} frontmatter delete test-12.md draft
```

Then verify:
```bash
{{BINARY}} frontmatter show test-12.md
```

**Expected:** The delete command output shows `FRONTMATTER DELETED: draft` and displays the remaining frontmatter block without the `draft` field. The subsequent `frontmatter show` confirms only 4 fields remain: title, tags, date, author. The `draft: true` field is gone.

### Test 13: Delete nonexistent key

**Command:**
```bash
cp pristine/frontmatter-doc.md test-13.md && {{BINARY}} frontmatter delete test-13.md nonexistent; echo "EXIT: $?"
```

**Expected:** Error output indicates the key was not found. The error message should list available keys or otherwise inform the user that `nonexistent` is not a valid key. Exit code should be non-zero.

### Test 14: Delete with --dry-run

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-14.md && {{BINARY}} frontmatter delete test-14.md author --dry-run
```

Then verify field still exists:
```bash
{{BINARY}} frontmatter get test-14.md author
```

**Expected:** The delete command output shows `WOULD DELETE` prefix (not `FRONTMATTER DELETED`), indicating dry-run mode. It displays what the frontmatter would look like with `author` removed, but does NOT actually modify the file. The subsequent `frontmatter get test-14.md author` returns `"Test User"` or `Test User`, confirming the field was NOT deleted.
