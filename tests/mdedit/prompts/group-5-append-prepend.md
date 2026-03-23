# Group 5: Append and Prepend

Tests the `append` and `prepend` commands including `_preamble` support, `--dry-run`, content at the last section, and preamble creation when absent.

---

## Spec Reference

### Section Addressing

All commands that take a `<section>` argument resolve it using these rules:

| Input | Matches |
|---|---|
| `"Background"` | Any heading with text "Background", any level |
| `"## Background"` | Only H2 headings with text "Background" |
| `"Background/Prior Work"` | "Prior Work" that is a child of "Background" |

Matching is exact (case-sensitive). If multiple headings match, exit 2. If no match, exit 1 with fuzzy suggestions. `_preamble` addresses content before first heading (after frontmatter). Frontmatter is NOT part of `_preamble`.

### Content Input Modes

All write commands accept content via three mechanisms, checked in this priority order:

| Mode | Flag | Description |
|---|---|---|
| Inline | `--content <text>` | Content passed as argument string |
| File | `--from-file <path>` | Content read from a file on disk |
| Stdin | (no flag) | Content read from stdin when stdin is not a TTY |

If none provided: `ERROR: No content provided`. Exit code: `4`.

### `append` Command Syntax

```
mdedit append <file> <section> [--content <text> | --from-file <path> | stdin] [--dry-run]
```

### `append` Output Format

```
APPENDED: 3 lines to "## Background" (was 12 lines -> now 15 lines)

-> ## Background
  [existing content...]
  [10 more lines]
  Last existing line before append.
+
+ Additional paragraph that provides more
+ context about the constraints.

  ## Methods
  We evaluate using the following criteria...
  [64 more lines]
```

- `+` prefix marks appended lines.
- Shows last 1-2 existing lines for continuity before the appended content.
- `[end of document]` replaces next-section when target is last section.

### `prepend` Command Syntax

```
mdedit prepend <file> <section> [--content <text> | --from-file <path> | stdin] [--dry-run]
```

### `prepend` Output Format

```
PREPENDED: 2 lines to "## Background" (was 12 lines -> now 14 lines)

  ## Introduction
  [14 more lines]

-> ## Background
+ Note: This section was revised on 2026-03-17.
+
  The system operates under three constraints...
  [11 more lines]

  ## Methods
  [64 more lines]
```

- `+` prefix marks prepended lines.
- Shows first 1-2 existing lines after the prepended content.

### Preamble Write Operations

`append` and `prepend` both work on `_preamble` -- content is placed after frontmatter, before the first heading. If there is no frontmatter, `_preamble` starts at byte 0.

### Whitespace Normalisation

After any write operation, mdedit normalises whitespace at section boundaries: exactly one blank line between sections, one trailing newline at EOF.

### Dry-run

All write commands support `--dry-run`. Output uses `WOULD <VERB>` instead of past tense. Header `DRY RUN -- no changes written` is prepended. No file modifications occur.

### Write Command Output Format Conventions

All write command outputs follow this structure:

```
<SUMMARY LINE>

  <previous section -- first line + [N more lines]>

-> <target section -- first line + [N more lines] + last line>

  <next section -- first line + [N more lines]>
```

- `->` marker identifies the changed section.
- Previous/next sections confirm correct location.
- `[end of document]` replaces next-section when target is last.

### Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Section not found |
| `2` | Ambiguous section match |
| `3` | File error |
| `4` | Content error (no content provided) |
| `5` | Validation failures |
| `10` | No-op (content identical) |

## Available Sample Files

- `pristine/frontmatter-doc.md` -- Primary test file with YAML frontmatter and nested sections (Introduction, Background with children Prior Work and Limitations, Methods, Results, Conclusion with children Future Work and Acknowledgements). Has NO preamble content.
- `pristine/preamble-doc.md` -- Has YAML frontmatter followed by preamble text before the first heading (`# Main Document`). Contains First Section, Second Section (with child Nested Under Second), and Third Section.
- `pristine/no-frontmatter.md` -- No YAML frontmatter and no preamble. Starts directly with `# Document Without Frontmatter`. Contains Section One and Section Two.

## Tests

### Test 1: Append inline content to a section

```bash
cp pristine/frontmatter-doc.md test-1.md && {{BINARY}} append test-1.md "Introduction" --content "Appended paragraph."
```

**Expected:** Output shows `APPENDED:` with line counts (was/now). The `->` marker identifies the Introduction section. Appended lines are shown with `+` prefix. Then run `{{BINARY}} extract test-1.md "Introduction"` and verify "Appended paragraph." appears at the end of the section content, after the original introduction text.

### Test 2: Append with --dry-run

```bash
cp pristine/frontmatter-doc.md test-2.md && {{BINARY}} append test-2.md "Introduction" --content "Test" --dry-run
```

**Expected:** Output contains `WOULD APPEND` (not `APPENDED`) and `DRY RUN` header. Then run `cat test-2.md` and verify the file is identical to the pristine original -- no changes were made.

### Test 3: Append to last section (end of document context)

```bash
cp pristine/frontmatter-doc.md test-3.md && {{BINARY}} append test-3.md "Acknowledgements" --content "Final note."
```

**Expected:** Output shows `APPENDED:` for "### Acknowledgements". Since Acknowledgements is the last section in the document, the context after the target section should show `[end of document]` instead of a next section. Then run `{{BINARY}} extract test-3.md "Acknowledgements"` to verify "Final note." was appended after the original content.

### Test 4: Append to _preamble in file that has preamble

```bash
cp pristine/preamble-doc.md test-4.md && {{BINARY}} append test-4.md "_preamble" --content "Appended to preamble."
```

**Expected:** Output shows `APPENDED:` for `_preamble`. Then run `cat test-4.md` and verify: (a) YAML frontmatter is intact, (b) original preamble text is still present, (c) "Appended to preamble." appears after the original preamble text and before `# Main Document`.

### Test 5: Append to _preamble in file with no preamble (creates it)

```bash
cp pristine/frontmatter-doc.md test-5.md && {{BINARY}} append test-5.md "_preamble" --content "Created preamble via append."
```

**Expected:** Output shows the append operation on `_preamble`. Then run `cat test-5.md` and verify: (a) YAML frontmatter is intact, (b) "Created preamble via append." appears between the frontmatter closing `---` and `# Research Notes`.

### Test 6: Append to _preamble in file with no frontmatter

```bash
cp pristine/no-frontmatter.md test-6.md && {{BINARY}} append test-6.md "_preamble" --content "Preamble at byte 0."
```

**Expected:** Output shows the append operation on `_preamble`. Then run `cat test-6.md` and verify: (a) "Preamble at byte 0." appears at the very beginning of the file, (b) `# Document Without Frontmatter` follows after it with proper spacing.

### Test 7: Append to _preamble with --dry-run

```bash
cp pristine/preamble-doc.md test-7.md && {{BINARY}} append test-7.md "_preamble" --content "Dry run." --dry-run
```

**Expected:** Output contains `WOULD APPEND` and `DRY RUN` header. Then run `cat test-7.md` and verify the file is identical to the pristine original -- no changes were made.

### Test 8: Prepend inline content to a section

```bash
cp pristine/frontmatter-doc.md test-8.md && {{BINARY}} prepend test-8.md "Introduction" --content "Prepended note."
```

**Expected:** Output shows `PREPENDED:` with line counts (was/now). The `->` marker identifies the Introduction section. Prepended lines are shown with `+` prefix. Shows first 1-2 existing lines after the prepended content. Then run `{{BINARY}} extract test-8.md "Introduction"` and verify "Prepended note." appears at the start of the section content, before the original introduction text.

### Test 9: Prepend with --dry-run

```bash
cp pristine/frontmatter-doc.md test-9.md && {{BINARY}} prepend test-9.md "Introduction" --content "Test" --dry-run
```

**Expected:** Output contains `WOULD PREPEND` and `DRY RUN` header. Then run `cat test-9.md` and verify the file is identical to the pristine original -- no changes were made.

### Test 10: Prepend to _preamble in file that has preamble

```bash
cp pristine/preamble-doc.md test-10.md && {{BINARY}} prepend test-10.md "_preamble" --content "Prepended to preamble."
```

**Expected:** Output shows `PREPENDED:` for `_preamble`. Then run `cat test-10.md` and verify: (a) YAML frontmatter is intact, (b) "Prepended to preamble." appears immediately after the frontmatter closing `---`, (c) the original preamble text follows after it, (d) `# Main Document` comes after all preamble content.

### Test 11: Prepend to _preamble in file with no preamble (creates it)

```bash
cp pristine/frontmatter-doc.md test-11.md && {{BINARY}} prepend test-11.md "_preamble" --content "Created preamble via prepend."
```

**Expected:** Output shows the prepend operation on `_preamble`. Then run `cat test-11.md` and verify: (a) YAML frontmatter is intact, (b) "Created preamble via prepend." appears between the frontmatter closing `---` and `# Research Notes`.

### Test 12: Prepend to _preamble in file with no frontmatter

```bash
cp pristine/no-frontmatter.md test-12.md && {{BINARY}} prepend test-12.md "_preamble" --content "Preamble at byte 0."
```

**Expected:** Output shows the prepend operation on `_preamble`. Then run `cat test-12.md` and verify: (a) "Preamble at byte 0." appears at the very beginning of the file (byte 0), (b) `# Document Without Frontmatter` follows after it with proper spacing.

### Test 13: Prepend to _preamble with --dry-run

```bash
cp pristine/preamble-doc.md test-13.md && {{BINARY}} prepend test-13.md "_preamble" --content "Dry run." --dry-run
```

**Expected:** Output contains `WOULD PREPEND` and `DRY RUN` header. Then run `cat test-13.md` and verify the file is identical to the pristine original -- no changes were made.
