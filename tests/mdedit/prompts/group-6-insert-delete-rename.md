# Group 6: Insert, Delete, and Rename

Tests the `insert`, `delete`, and `rename` commands including positional insertion (`--before`/`--after`), heading level mismatch warnings, cascade deletion of children, `_preamble` deletion, and dry-run for all three.

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

If none provided for commands that require content: `ERROR: No content provided`. Exit code: `4`.

### `insert` Command Syntax

```
mdedit insert <file> --after <section> --heading <heading> [--content <text> | --from-file <path> | stdin] [--dry-run]
mdedit insert <file> --before <section> --heading <heading> [--content <text> | --from-file <path> | stdin] [--dry-run]
```

Exactly one of `--after` or `--before` is required.

### `insert` Output Format

```
INSERTED: "## Related Work" (4 lines) after "## Background"

  ## Background
  The system operates under three constraints...
  [10 more lines]

-> ## Related Work
  Previous approaches have focused on rule-based...
  [2 more lines]
  No prior work addresses the combined constraints.

  ## Methods
  We evaluate using the following criteria...
  [64 more lines]
```

- `->` marker identifies the newly inserted section.
- Previous/next sections confirm correct placement.
- `[end of document]` replaces next-section when inserted section is last.

### `insert` Notes

- `--heading` must include the `#` prefix (e.g., `"## Related Work"`).
- Content is optional -- omitting it creates a heading-only empty section.
- Warning when heading level mismatches surroundings: `WARNING: Inserting H3 between two H2 sections -- heading level mismatch`

### `delete` Command Syntax

```
mdedit delete <file> <section> [--dry-run]
```

### `delete` Output Format

```
DELETED: "## Appendix" (8 lines, 145 words removed)

  ## Conclusion
  In summary, the approach demonstrates...
  [4 more lines]

x ## Appendix (deleted)
  Was: "The following tables provide supplementary..."
  [6 more lines]
  Was: "See also: references.md"

  [end of document]
```

- `x` marker on the deleted section heading, with `(deleted)` suffix.
- `Was:` prefix on first and last content lines of the deleted section.
- Children are included in the deletion.
- Warning when children exist: `WARNING: N child sections also deleted: ### Name, ### Name`

### `delete` on `_preamble`

`delete` on `_preamble` removes all content between frontmatter and first heading. If there is no frontmatter, it removes content before the first heading starting at byte 0.

### `rename` Command Syntax

```
mdedit rename <file> <section> <new-name> [--dry-run]
```

### `rename` Output Format

```
RENAMED: "## Background" -> "## Context and Background" (line 20)

  ## Introduction
  [14 more lines]

-> ## Context and Background
  The system operates under three constraints...
  [10 more lines]

  ## Methods
  [64 more lines]
```

- `<new-name>` is text only, without `#` prefix.
- Heading level is preserved from the original heading.

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

- `pristine/frontmatter-doc.md` -- Primary test file with YAML frontmatter and nested sections. Structure: `# Research Notes` > `## Introduction`, `## Background` (children: `### Prior Work`, `### Limitations`), `## Methods` (child: `### Evaluation Criteria`), `## Results` (children: `### Performance Data`, `### Edge Cases`), `## Conclusion` (children: `### Future Work`, `### Acknowledgements`).
- `pristine/preamble-doc.md` -- Has YAML frontmatter followed by preamble text before the first heading (`# Main Document`). Contains `## First Section`, `## Second Section` (child: `### Nested Under Second`), `## Third Section`.
- `pristine/large-document.md` -- Deep nesting up to H4. Structure: `# Project Architecture` > `## Overview`, `## Frontend` (children include H3 and H4 levels), `## Backend` (children include H3 and H4 levels), `## Infrastructure`, `## Security`, `## Appendix`.

## Tests

### Test 1: Insert section after a given section

```bash
cp pristine/frontmatter-doc.md test-1.md && {{BINARY}} insert test-1.md --after "Background" --heading "## Related Work" --content "Previous studies show..."
```

**Expected:** Output shows `INSERTED: "## Related Work"` with line count and `after "## Background"`. The `->` marker identifies the new section. Context shows Background before and Methods after. Then run `{{BINARY}} outline test-1.md` and verify the new `## Related Work` section appears between `## Background` (and its children) and `## Methods`.

### Test 2: Insert section before a given section

```bash
cp pristine/frontmatter-doc.md test-2.md && {{BINARY}} insert test-2.md --before "Methods" --heading "## Hypothesis" --content "We hypothesize that..."
```

**Expected:** Output shows `INSERTED: "## Hypothesis"` with `before "## Methods"`. Then run `{{BINARY}} outline test-2.md` and verify `## Hypothesis` appears between `## Background` (after its children) and `## Methods`.

### Test 3: Insert with heading level mismatch warning

```bash
cp pristine/frontmatter-doc.md test-3.md && {{BINARY}} insert test-3.md --after "Introduction" --heading "### Subsection" --content "Detail here."
```

**Expected:** Output includes a warning about heading level mismatch (inserting H3 between H2 sections). The operation still succeeds -- the section is inserted. Then run `{{BINARY}} outline test-3.md` and verify `### Subsection` appears between `## Introduction` and `## Background`.

### Test 4: Insert with --dry-run

```bash
cp pristine/frontmatter-doc.md test-4.md && {{BINARY}} insert test-4.md --after "Introduction" --heading "## New Section" --content "Test." --dry-run
```

**Expected:** Output contains `WOULD INSERT` (not `INSERTED`) and `DRY RUN` header. Then run `cat test-4.md` and verify the file is identical to the pristine original -- no changes were made.

### Test 5: Insert after last top-level section (end of document)

```bash
cp pristine/frontmatter-doc.md test-5.md && {{BINARY}} insert test-5.md --after "Conclusion" --heading "## New Last" --content "At the end."
```

**Expected:** Output shows `INSERTED: "## New Last"` after `"## Conclusion"`. Since the new section is now the last in the document, context after it should show `[end of document]`. Then run `{{BINARY}} outline test-5.md` and verify `## New Last` is the last top-level section (appearing after Conclusion and its children Future Work and Acknowledgements).

### Test 6: Delete a section with no children

```bash
cp pristine/frontmatter-doc.md test-6.md && {{BINARY}} delete test-6.md "Conclusion"
```

**Expected:** Output shows `DELETED:` with section name, line count, and word count. The `x` marker appears on the deleted section heading with `(deleted)` suffix. `Was:` prefix shows first/last content lines of the deleted section. Note that Conclusion has children (Future Work, Acknowledgements), so there should be a warning about child sections also being deleted. Then run `{{BINARY}} outline test-6.md` and verify `## Conclusion`, `### Future Work`, and `### Acknowledgements` are all removed.

### Test 7: Delete a section with children (cascade warning)

```bash
cp pristine/frontmatter-doc.md test-7.md && {{BINARY}} delete test-7.md "Background"
```

**Expected:** Output shows `DELETED:` for "## Background". Since Background has children (`### Prior Work`, `### Limitations`), the output should include a warning about child sections being deleted. Then run `{{BINARY}} outline test-7.md` and verify `## Background`, `### Prior Work`, and `### Limitations` are all removed, while other sections remain.

### Test 8: Delete _preamble

```bash
cp pristine/preamble-doc.md test-8.md && {{BINARY}} delete test-8.md "_preamble"
```

**Expected:** Output shows `DELETED:` for `_preamble`. Then run `cat test-8.md` and verify: (a) YAML frontmatter is intact, (b) the preamble text ("This is preamble content..." etc.) is removed, (c) `# Main Document` follows directly after frontmatter with proper spacing.

### Test 9: Delete with --dry-run

```bash
cp pristine/frontmatter-doc.md test-9.md && {{BINARY}} delete test-9.md "Introduction" --dry-run
```

**Expected:** Output contains `WOULD DELETE` (not `DELETED`) and `DRY RUN` header. Then run `cat test-9.md` and verify the file is identical to the pristine original -- no changes were made. The Introduction section is still present.

### Test 10: Rename a section

```bash
cp pristine/frontmatter-doc.md test-10.md && {{BINARY}} rename test-10.md "Introduction" "Overview"
```

**Expected:** Output shows `RENAMED: "## Introduction" -> "## Overview"` with the line number. Heading level `##` is preserved. The `->` marker identifies the renamed section in the context output. Then run `{{BINARY}} outline test-10.md` and verify `## Overview` appears where `## Introduction` was, and no `## Introduction` exists.

### Test 11: Rename with level-specific addressing

```bash
cp pristine/frontmatter-doc.md test-11.md && {{BINARY}} rename test-11.md "## Background" "Context and Background"
```

**Expected:** Output shows `RENAMED: "## Background" -> "## Context and Background"`. The level-specific address `"## Background"` correctly targets the H2 heading. Heading level is preserved. Then run `{{BINARY}} outline test-11.md` and verify the section is now named `## Context and Background`.

### Test 12: Rename with --dry-run

```bash
cp pristine/frontmatter-doc.md test-12.md && {{BINARY}} rename test-12.md "Introduction" "New Name" --dry-run
```

**Expected:** Output contains `WOULD RENAME` (not `RENAMED`) and `DRY RUN` header. Then run `cat test-12.md` and verify the file is identical to the pristine original -- no changes were made. The heading still reads `## Introduction`.
