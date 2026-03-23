# Group 4: Replace

Tests the `replace` command across all content input modes (inline, file, stdin), `_preamble` support, `--preserve-children`, `--dry-run`, and no-op detection.

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

### `replace` Command Syntax

```
mdedit replace <file> <section> [--content <text> | --from-file <path> | stdin]
                                [--preserve-children] [--dry-run]
```

### `replace` Output Format

```
REPLACED: "## Background" (was 12 lines, 312 words -> now 8 lines, 198 words)

  ## Introduction
  This document introduces the problem space...
  [14 more lines]

-> ## Background
  The system now operates under two constraints...
  [6 more lines]
  Both constraints are enforced at write time.

  ## Methods
  We evaluate using the following criteria...
  [64 more lines]
```

- The `->` marker identifies the changed section.
- Previous/next sections confirm correct location.
- `[end of document]` replaces next-section when target is last.

### `replace` Options

- `--preserve-children`: Replace only the section's own content; keep child sections intact.
- `--dry-run`: Preview, no file changes. Output uses `WOULD REPLACE` instead of `REPLACED`.

### `replace` Warnings

- Content reduction >50%: `WARNING: Large reduction: N lines -> M lines`
- Children removed: `WARNING: N child sections removed: ### Name, ### Name`

### `replace` No-op

When the replacement content is identical to the existing content:
- Output: `NO CHANGE: Section content is identical to replacement`
- Exit code: `10`

### Preamble Write Operations

`replace` works on `_preamble` -- content is placed after frontmatter, before the first heading. If there is no frontmatter, `_preamble` starts at byte 0.

### Whitespace Normalisation

After any write operation, mdedit normalises whitespace at section boundaries: exactly one blank line between sections, one trailing newline at EOF.

### Dry-run

All write commands support `--dry-run`. Output uses `WOULD <VERB>` instead of past tense. Header `DRY RUN -- no changes written` is prepended. No file modifications occur.

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

- `pristine/frontmatter-doc.md` -- Primary test file with YAML frontmatter and nested sections (Introduction, Background with children Prior Work and Limitations, Methods, Results, Conclusion). Has NO preamble content.
- `pristine/preamble-doc.md` -- Has YAML frontmatter followed by preamble text before the first heading (`# Main Document`). Contains three H2 sections.
- `pristine/no-frontmatter.md` -- No YAML frontmatter and no preamble. Starts directly with `# Document Without Frontmatter`.

## Tests

### Test 1: Replace with inline content

```bash
cp pristine/frontmatter-doc.md test-1.md && {{BINARY}} replace test-1.md "Introduction" --content "New introduction content here."
```

**Expected:** Output shows `REPLACED:` with the section name `"## Introduction"`, includes was/now line and word counts. The `->` marker identifies the replaced section. Then run `cat test-1.md` and verify the Introduction section now contains only "New introduction content here." and other sections are untouched.

### Test 2: Replace with --from-file

```bash
echo "Replacement from file." > /tmp/mdedit-replace-input.md && cp pristine/frontmatter-doc.md test-2.md && {{BINARY}} replace test-2.md "Introduction" --from-file /tmp/mdedit-replace-input.md
```

**Expected:** Output shows `REPLACED:` summary. Then run `cat test-2.md` and verify Introduction section contains "Replacement from file." and other sections are untouched.

### Test 3: Replace with stdin

```bash
cp pristine/frontmatter-doc.md test-3.md && echo "Piped content." | {{BINARY}} replace test-3.md "Introduction"
```

**Expected:** Output shows `REPLACED:` summary. Then run `cat test-3.md` and verify Introduction section contains "Piped content." and other sections are untouched.

### Test 4: Replace with --preserve-children

```bash
cp pristine/frontmatter-doc.md test-4.md && {{BINARY}} replace test-4.md "Background" --preserve-children --content "New background intro."
```

**Expected:** Output shows `REPLACED:` for "## Background". Then run `cat test-4.md` and verify: (a) Background section's own content is now "New background intro.", (b) child sections `### Prior Work` and `### Limitations` are still present with their original content intact.

### Test 5: Replace with --dry-run

```bash
cp pristine/frontmatter-doc.md test-5.md && {{BINARY}} replace test-5.md "Introduction" --content "Test" --dry-run
```

**Expected:** Output contains `WOULD REPLACE` (not `REPLACED`) and `DRY RUN` header. Then run `cat test-5.md` and verify the file is identical to the pristine original -- no changes were made.

### Test 6: Replace no-op (identical content)

```bash
cp pristine/frontmatter-doc.md test-6.md && {{BINARY}} extract test-6.md "Introduction" --to-file /tmp/mdedit-noop.md && {{BINARY}} replace test-6.md "Introduction" --from-file /tmp/mdedit-noop.md; echo "EXIT: $?"
```

**Expected:** The replace command outputs `NO CHANGE: Section content is identical to replacement`. Exit code is `10`. The file is unchanged.

### Test 7: Replace nonexistent section

```bash
{{BINARY}} replace pristine/frontmatter-doc.md "Nonexistent" --content "test"; echo "EXIT: $?"
```

**Expected:** Exit code `1`. Error output indicates section not found, possibly with fuzzy suggestions for similar section names.

### Test 8: Replace _preamble in file that has preamble

```bash
cp pristine/preamble-doc.md test-8.md && {{BINARY}} replace test-8.md "_preamble" --content "Replaced preamble content."
```

**Expected:** Output shows `REPLACED:` for `_preamble`. Then run `cat test-8.md` and verify: (a) YAML frontmatter (`---` block) is still intact at top, (b) "Replaced preamble content." appears after the closing `---` and before `# Main Document`, (c) the original preamble text is gone.

### Test 9: Replace _preamble in file with no preamble (creates it)

```bash
cp pristine/frontmatter-doc.md test-9.md && {{BINARY}} replace test-9.md "_preamble" --content "New preamble created."
```

**Expected:** Output shows `REPLACED:` for `_preamble`. Then run `cat test-9.md` and verify: (a) YAML frontmatter is still intact, (b) "New preamble created." appears between the frontmatter closing `---` and `# Research Notes`, (c) all other sections are untouched.

### Test 10: Replace _preamble in file with no frontmatter

```bash
cp pristine/no-frontmatter.md test-10.md && {{BINARY}} replace test-10.md "_preamble" --content "Preamble at start."
```

**Expected:** Output shows `REPLACED:` for `_preamble`. Then run `cat test-10.md` and verify: (a) "Preamble at start." appears at the very beginning of the file (byte 0), (b) `# Document Without Frontmatter` follows after it, (c) all other sections are untouched.

### Test 11: Replace _preamble with --dry-run

```bash
cp pristine/preamble-doc.md test-11.md && {{BINARY}} replace test-11.md "_preamble" --content "Dry run preamble." --dry-run
```

**Expected:** Output contains `WOULD REPLACE` and `DRY RUN` header. Then run `cat test-11.md` and verify the file is identical to the pristine original -- no changes were made. The original preamble text is still present.

### Test 12: Replace _preamble no-op (identical content)

First extract the existing preamble content, then replace with it:

```bash
cp pristine/preamble-doc.md test-12.md && {{BINARY}} extract pristine/preamble-doc.md "_preamble" --to-file /tmp/mdedit-preamble-noop.md && {{BINARY}} replace test-12.md "_preamble" --from-file /tmp/mdedit-preamble-noop.md; echo "EXIT: $?"
```

**Expected:** The replace outputs `NO CHANGE` message. Exit code is `10`. The file is unchanged.

### Test 13: Replace with no content provided

```bash
cp pristine/frontmatter-doc.md test-13.md && {{BINARY}} replace test-13.md "Introduction"; echo "EXIT: $?"
```

**Expected:** No `--content`, no `--from-file`, and stdin is a TTY. Error output indicates no content provided. Exit code is `4`.
