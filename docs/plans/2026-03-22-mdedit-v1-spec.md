# mdedit v1 — Specification

A compiled CLI tool for structured markdown editing, designed for LLM workflows.

## Design principles

1. **Token efficiency.** Inputs and outputs are minimal. The LLM should never need to re-read a file to verify an operation succeeded.

2. **Meaningful output.** Every response tells the model what happened, where it happened, and whether anything went wrong — enough to decide "proceed" or "fix and retry" without further reads.

3. **Maximum convention adherence.** Flag names, subcommand verbs, help format, and exit codes follow GNU/POSIX majority conventions. An LLM should be able to guess the correct invocation before reading any docs.

4. **Composability.** Supports three integration modes: inline content, file-based (for LLM Edit tool workflows), and Unix pipes.

5. **Safety by default.** Destructive operations warn about data loss. `--dry-run` is available on every write command.

## Language and distribution

Rust. Single compiled binary, no runtime dependencies. Optimised for sub-millisecond startup.

### Parser: tree-sitter-md

Markdown parsing uses `tree-sitter-md` (crate: `tree-sitter-md`), which produces a concrete syntax tree (CST) with byte offsets on every node.

**Why tree-sitter over alternatives:**

- **Source surgery architecture.** No Rust markdown serializer round-trips faithfully — all normalise formatting. The correct approach is: parse to get byte ranges, then splice the original source string directly. Untouched regions are preserved byte-for-byte. tree-sitter is designed for exactly this workflow.
- **CST, not AST.** Every byte of the source is accounted for in the tree, including whitespace and punctuation. This means headings inside code fences are correctly identified as non-headings, escaped `#` characters are handled, and indented code blocks don't produce false heading matches. No edge-case handling needed — correctness by construction.
- **Future-proof.** v2 features like `shard` (splitting a document into multiple files by heading level, with heading-level rewriting) require full syntactic understanding of the document. A CST supports structural transformations that an AST would fight.
- **Byte offsets are native.** Every node has `start_byte()` and `end_byte()`. No line:column-to-offset conversion needed.
- **Frontmatter support.** The grammar recognises `---`-delimited YAML frontmatter as `minus_metadata` nodes.
- **Incremental reparsing.** After a splice, the tree can be efficiently updated rather than re-parsed from scratch. Useful for future multi-edit operations.

**Alternatives considered:**

| Crate | Why not for v1 |
|---|---|
| `markdown-rs` | Full MDAST with byte offsets — viable, but AST level of abstraction limits future structural transformations |
| `comrak` | Full AST but provides line:column, not byte offsets — adds conversion friction |
| `pulldown-cmark` | Event stream, not a tree — would require building section-boundary logic from scratch |

### Markdown subset

ATX-style headings only (lines starting with `#`). Setext-style (underline) headings are not supported in v1. YAML frontmatter (delimited by `---`) is recognised and preserved.

### Counting rules

The terms "words" and "lines" appear throughout output formats. Their definitions:

- **Words:** Whitespace-delimited tokens in content lines. Heading lines, frontmatter, and blank lines do not contribute to word counts. Content inside code fences counts as words (code is content).
- **Lines:** All lines within a section's span, including the heading line, blank lines, and code fence delimiters. This is the raw line count of the byte range.
- **Content lines:** Lines minus blank lines and the heading line itself. Used only in `validate` to identify empty sections (0 content lines).

Frontmatter is excluded from all document-level totals (`outline`, `stats`). It is its own domain, accessed via `frontmatter` commands.

---

## Section addressing

All commands that take a `<section>` argument resolve it using these rules, in order:

| Input | Matches |
|---|---|
| `"Background"` | Any heading with text "Background", any level |
| `"## Background"` | Only H2 headings with text "Background" |
| `"Background/Prior Work"` | "Prior Work" that is a child of "Background" |

Matching is exact (case-sensitive) on the heading text, ignoring the `#` prefix and any leading/trailing whitespace.

### Ambiguous match

If multiple headings match, the operation fails:

```
ERROR: "Background" matches 2 sections in doc.md
  → ## Background (H2, line 20)
  → ### Background (H3, line 89, under "## Related Work")
Disambiguate with "## Background" or "Related Work/Background"
```

Exit code: `2`

### No match

If no heading matches, fuzzy suggestions are provided:

```
ERROR: Section "Backgrond" not found in doc.md
Did you mean?
  → ## Background (H2, line 20)
  → ## Background and Motivation (H2, line 45)
```

Exit code: `1`

### Preamble

Content before the first heading is addressed with the reserved name `_preamble`:

```bash
mdedit extract doc.md "_preamble"
```

**Frontmatter is not part of `_preamble`.** `_preamble` spans from the byte after the closing frontmatter `---` delimiter to the byte before the first heading. If there is no frontmatter, `_preamble` starts at byte 0.

**Write operations on `_preamble`:** `replace`, `append`, and `prepend` all work on `_preamble` — content is placed after frontmatter, before the first heading. `delete` on `_preamble` removes all content between frontmatter and the first heading. `rename` is not valid for `_preamble` (no heading to rename). `insert --before _preamble` is not valid; use `prepend` to `_preamble` instead.

### Section boundaries

A section spans from its heading line to the line before the next heading of equal or higher level. Child headings (deeper level) are included in the parent section's span recursively — "children" always means all descendants (H3s, H4s, etc.), not just immediate children.

### Whitespace normalisation

After any write operation, `mdedit` normalises whitespace at section boundaries: exactly one blank line between the end of one section's content and the next heading, and exactly one trailing newline at EOF. This prevents blank-line accumulation after repeated automated edits. Whitespace within section content is never modified.

---

## Content input modes

All write commands accept content via three mechanisms, checked in this priority order:

| Mode | Flag | Description |
|---|---|---|
| Inline | `--content <text>` | Content passed as argument string |
| File | `--from-file <path>` | Content read from a file on disk |
| Stdin | (no flag) | Content read from stdin when stdin is not a TTY |

If none are provided:

```
ERROR: No content provided
Use --content "...", --from-file <path>, or pipe to stdin
```

Exit code: `4`

### File mode workflow (primary LLM pattern)

```bash
# Step 1: Extract section to temp file
mdedit extract doc.md "Background" --to-file /tmp/section.md

# Step 2: Surgical edit using the LLM's Edit tool (str_replace)
# (separate tool call — small file, minimal context)

# Step 3: Replace section from edited file
mdedit replace doc.md "Background" --from-file /tmp/section.md
```

### Pipe mode workflow

```bash
mdedit extract doc.md "Background" | sed 's/old/new/' | mdedit replace doc.md "Background"
```

---

## TTY-aware output

Output format adapts based on whether stdout is a terminal:

| Command | TTY (terminal) | Pipe (not TTY) |
|---|---|---|
| `extract` | `SECTION:` metadata header + content | Raw markdown only |
| `outline` | Full formatted outline | Same (unchanged) |
| Write ops | Verification output to stdout | Verification to stderr |

---

## Commands — read operations

### `outline`

Display the document's heading structure with word counts and line ranges.

```
mdedit outline <file> [--max-depth <N>]
```

**Output:**

```
# My Document — 847 words, 142 lines

  ## Introduction — 120 words (lines 3–18)
  ## Background — 312 words (lines 20–67)
    ### Prior Work — 89 words (lines 45–58)
    ### Definitions — 43 words (lines 60–67)
  ## Methods — 201 words (lines 69–134)
  ## Results — 98 words (lines 136–158)
  ## Conclusion — 27 words (lines 160–170)
    ### TODO — 0 words ⚠ empty
```

**Options:**

| Flag | Description |
|---|---|
| `--max-depth <N>` | Only show headings up to level N (e.g. `--max-depth 2` shows H1 and H2 only) |

**Notes:**
- Indentation reflects heading hierarchy
- Word count is for the section's own content plus all children
- Empty sections are flagged with `⚠ empty`
- Line ranges help with debugging and cross-referencing

---

### `extract`

Pull a section's content from the document.

```
mdedit extract <file> <section> [--no-children] [--to-file <path>]
```

**Output (TTY):**

```
SECTION: "## Background" — 312 words, lines 20–67, 2 children

The system operates under three constraints that govern
all write operations in the pipeline...

### Prior Work

Previous approaches include...

### Definitions

For the purposes of this document...
```

**Output (pipe or `--to-file`):**

Raw markdown content only, no metadata header.

**Options:**

| Flag | Description |
|---|---|
| `--no-children` | Extract only the section's own content, excluding child sections |
| `--to-file <path>` | Write extracted content to a file instead of stdout |

**With `--no-children`:**

```
SECTION: "## Background" — 180 words, lines 20–44 (2 children excluded)

The system operates under three constraints that govern
all write operations in the pipeline...
```

**With `--to-file`:**

Only the confirmation line is written to stdout — section content goes to the file, not the terminal:

```
EXTRACTED: "## Background" (12 lines, 312 words) → /tmp/section.md
```

**Edge cases:**
- Empty section: outputs `[no content]` (TTY) or empty string (pipe)
- `_preamble`: extracts content before first heading, after frontmatter

---

### `search`

Find sections containing a text pattern.

```
mdedit search <file> <query> [--case-sensitive]
```

Search is case-insensitive by default. Use `--case-sensitive` for exact case matching.

**Output:**

```
SEARCH: "constraint" — 4 matches in 2 sections

  ## Background (3 matches)
    Line 22: The system operates under three |constraints|...
    Line 25: The first |constraint| requires that...
    Line 31: The second |constraint| ensures...

  ## Conclusion (1 match)
    Line 162: ...satisfying all |constraints| simultaneously.
```

**Notes:**
- Results are grouped by section, not listed flat
- Match text is highlighted with `|pipe|` delimiters (no ANSI codes)
- Section names in the output tell the LLM which section to target for edits

---

### `stats`

Word and line counts per section.

```
mdedit stats <file>
```

**Output:**

```
STATS: document.md — 847 words, 142 lines, 7 sections

  ## Introduction — 120 words (14%)
  ## Background — 312 words (37%) ← largest
    ### Prior Work — 89 words
    ### Definitions — 43 words
  ## Methods — 201 words (24%)
  ## Results — 98 words (12%)
  ## Conclusion — 27 words (3%)
    ### TODO — 0 words ← empty
```

**Notes:**
- Percentages are relative to total document word count
- `← largest` and `← empty` annotations flag outliers

---

### `validate`

Check heading structure for common problems.

```
mdedit validate <file>
```

**Output (issues found):**

```
INVALID: document.md — 3 issues

  ⚠ Line 45: H4 "#### Detail" has no H3 parent (skipped level)
  ⚠ Line 89: Section "## TODO" is empty (0 content lines)
  ℹ Line 12: Duplicate heading text "## Notes" (also at line 67)
```

**Output (clean):**

```
VALID: document.md — 7 sections, max depth 3, no issues
```

**Checks performed:**
- Skipped heading levels (H2 → H4 with no H3)
- Empty sections (heading with no content before next heading)
- Duplicate heading text at the same level (ambiguity risk)

**Exit code:** `5` if any `⚠` warnings are present, `0` if clean or only `ℹ` informational findings. Warnings (`⚠`) indicate structural problems — skipped heading levels, empty sections. Informational findings (`ℹ`) flag potential ambiguity risks like duplicate heading text, but are not structural errors.

---

### `frontmatter`

Read YAML frontmatter fields.

```
mdedit frontmatter <file>
mdedit frontmatter get <file> <key>
```

**Output (all fields):**

```
FRONTMATTER: document.md — 4 fields

  title: "My Document"
  tags: ["rust", "cli", "markdown"]
  date: "2026-03-17"
  draft: true
```

**Output (`get` single key):**

```
["rust", "cli", "markdown"]
```

Pure value output for `get` — no metadata wrapper. Suitable for piping or capture.

**Errors:**
- No frontmatter: `ERROR: No frontmatter found in document.md`
- Key not found: `ERROR: Key "author" not found in frontmatter. Available keys: title, tags, date, draft`

---

## Commands — write operations

All write commands support `--dry-run`. Dry-run output is identical to actual output except the summary line uses `WOULD <VERB>` instead of `<VERB>` past tense, and a header `DRY RUN — no changes written` is prepended. No file modifications occur.

### Output format conventions

All write command outputs follow this structure:

```
<SUMMARY LINE>

  <previous section — first line + [N more lines]>

→ <target section — first line + [N more lines] + last line>

  <next section — first line + [N more lines]>
```

| Element | Purpose |
|---|---|
| Summary line | Action, section name, before/after metrics |
| `→` marker | Identifies the changed section |
| Previous section | Confirms correct location in document |
| First + last line of change | Verifies content was written correctly, catches truncation |
| `[N more lines]` | Confirms section size without token cost |
| Next section | Confirms nothing was destroyed |
| `[end of document]` | Replaces next-section when target is last |

### Headings in replacement content

Replacement content (via `replace`, `append`, `prepend`, `insert`) is treated as literal markdown. If it contains headings, they become real document structure. The tool does not escape, reinterpret, or strip headings from input — it splices the bytes in as-is.

When heading levels in the input are inconsistent with the target section's position in the document hierarchy, a warning is emitted but the operation proceeds. This is "you probably made a mistake" feedback, not a block.

### Warnings

Warnings appear after the summary line when potentially destructive outcomes are detected. The operation still proceeds — warnings are informational.

```
⚠ Large reduction: 45 lines → 2 lines
⚠ 2 child sections removed: ### Prior Work, ### Definitions
⚠ Inserting H3 between two H2 sections — heading level mismatch
⚠ Content contains heading levels higher than parent section
```

---

### `replace`

Substitute a section's content. Replaces everything under the heading including child sections by default.

```
mdedit replace <file> <section> [--content <text> | --from-file <path> | stdin]
                                [--preserve-children] [--dry-run]
```

**Output:**

```
REPLACED: "## Background" (was 12 lines, 312 words → now 8 lines, 198 words)

  ## Introduction
  This document introduces the problem space...
  [14 more lines]

→ ## Background
  The system now operates under two constraints...
  [6 more lines]
  Both constraints are enforced at write time.

  ## Methods
  We evaluate using the following criteria...
  [64 more lines]
```

**Options:**

| Flag | Description |
|---|---|
| `--preserve-children` | Replace only the section's own content; keep child sections intact |
| `--dry-run` | Preview the change without writing to disk |

**Warnings:**
- Content reduction >50%: `⚠ Large reduction: 45 lines → 2 lines`
- Children removed: `⚠ 2 child sections removed: ### Prior Work, ### Definitions`

**No-op:**

```
NO CHANGE: Section content is identical to replacement
```

Exit code: `10`

**Dry-run:**

```
DRY RUN — no changes written

WOULD REPLACE: "## Background" (12 lines, 312 words → 8 lines, 198 words)

  [same neighborhood format as actual output]
```

---

### `append`

Add content to the end of a section, before the next heading.

```
mdedit append <file> <section> [--content <text> | --from-file <path> | stdin]
                               [--dry-run]
```

**Output:**

```
APPENDED: 3 lines to "## Background" (was 12 lines → now 15 lines)

→ ## Background
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

**Notes:**
- `+` prefix marks appended lines
- Shows the last 1–2 existing lines for continuity context
- Only the tail of the existing section is shown, not the full content

---

### `prepend`

Add content to the start of a section, immediately after the heading.

```
mdedit prepend <file> <section> [--content <text> | --from-file <path> | stdin]
                                [--dry-run]
```

**Output:**

```
PREPENDED: 2 lines to "## Background" (was 12 lines → now 14 lines)

  ## Introduction
  [14 more lines]

→ ## Background
+ Note: This section was revised on 2026-03-17.
+
  The system operates under three constraints...
  [11 more lines]

  ## Methods
  [64 more lines]
```

**Notes:**
- `+` prefix marks prepended lines
- Shows the first 1–2 existing lines after the prepended content for continuity

---

### `insert`

Add a new section at a specific position in the document.

```
mdedit insert <file> --after <section> --heading <heading> [--content <text> | --from-file <path> | stdin]
                                                           [--dry-run]
mdedit insert <file> --before <section> --heading <heading> [--content <text> | --from-file <path> | stdin]
                                                            [--dry-run]
```

Exactly one of `--after` or `--before` is required.

**Output:**

```
INSERTED: "## Related Work" (4 lines) after "## Background"

  ## Background
  The system operates under three constraints...
  [10 more lines]

→ ## Related Work
  Previous approaches have focused on rule-based...
  [2 more lines]
  No prior work addresses the combined constraints.

  ## Methods
  We evaluate using the following criteria...
  [64 more lines]
```

**Warnings:**
- Heading level mismatch: `⚠ Inserting H3 between two H2 sections — heading level mismatch`

**Notes:**
- `--heading` must include the `#` prefix (e.g. `"## Related Work"`)
- Content is optional — omitting it creates a heading-only (empty) section

---

### `delete`

Remove a section and its content from the document. Includes child sections.

```
mdedit delete <file> <section> [--dry-run]
```

**Output:**

```
DELETED: "## Appendix" (8 lines, 145 words removed)

  ## Conclusion
  In summary, the approach demonstrates...
  [4 more lines]

✗ ## Appendix (deleted)
  Was: "The following tables provide supplementary..."
  [6 more lines]
  Was: "See also: references.md"

  [end of document]
```

**Notes:**
- `✗` marks the deleted section
- `Was:` prefix on first and last lines of deleted content — confirms the right section was removed
- Child sections included in deletion

**Warnings:**
- Children removed: `⚠ 3 child sections also deleted: ### Table A, ### Table B, ### Table C`

---

### `rename`

Change a heading's text without modifying its content or level.

```
mdedit rename <file> <section> <new-name> [--dry-run]
```

The `<new-name>` argument is the new heading text without the `#` prefix. The heading level is preserved.

**Output:**

```
RENAMED: "## Background" → "## Context and Background" (line 20)

  ## Introduction
  [14 more lines]

→ ## Context and Background
  The system operates under three constraints...
  [10 more lines]

  ## Methods
  [64 more lines]
```

---

### `frontmatter set` / `frontmatter delete`

Modify individual YAML frontmatter fields.

```
mdedit frontmatter set <file> <key> <value> [--dry-run]
mdedit frontmatter delete <file> <key> [--dry-run]
```

**Output (set):**

```
FRONTMATTER SET: tags (was ["rust", "cli"] → now ["rust", "cli", "llm"])

---
title: "My Document"
→ tags: ["rust", "cli", "llm"]
date: "2026-03-17"
---
```

**Output (delete):**

```
FRONTMATTER DELETED: draft

---
title: "My Document"
tags: ["rust", "cli"]
date: "2026-03-17"
---
```

**Notes:**
- Full frontmatter is shown (it's always small) with `→` marking the changed line
- For `set`, `was → now` in summary line shows before/after
- Value is parsed as JSON if valid, otherwise treated as a plain string

**Errors:**
- No frontmatter exists: `ERROR: No frontmatter found in document.md. Use ---\n...\n--- delimiters to add frontmatter.`
- Key not found (for delete): `ERROR: Key "author" not found in frontmatter. Available keys: title, tags, date, draft`

---

## Exit codes

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

## Help text

### Top-level `--help`

```
mdedit — structured markdown editing for LLM workflows

Commands:
  outline     <file>                          Section hierarchy with word counts
  extract     <file> <section>                Pull section content (raw or to file)
  search      <file> <query>                  Find sections containing text
  stats       <file>                          Word/line counts per section
  validate    <file>                          Check heading structure
  frontmatter <file> [get|set|delete]         Read/write YAML frontmatter

  replace     <file> <section>                Substitute section content
  append      <file> <section>                Add content to end of section
  prepend     <file> <section>                Add content to start of section
  insert      <file> --before|after <section> Add new section at position
  delete      <file> <section>                Remove section and content
  rename      <file> <section> <new-name>     Change heading text

All write commands support --dry-run and accept --content, --from-file, or stdin.
Section addressing: "Name", "## Name" (level-specific), "Parent/Child" (nested).
Exit codes: 0=success, 1=not found, 2=ambiguous, 3=file error, 4=no content, 5=invalid, 10=no-op
```

### Per-subcommand `--help`

Each subcommand help includes an input/output/exit contract:

```
mdedit replace <file> <section> [--content <text> | --from-file <path> | stdin]

  Replace a section's content. Includes child sections by default.

  Input:   Section content via --content, --from-file, or stdin
  Output:  Summary line + neighborhood context (prev section, changed section, next section)
  Exits:   0=success, 1=not found, 2=ambiguous, 4=no content, 10=no change

  Options:
    --content <text>        Replacement content as string
    --from-file <path>      Read replacement from file
    --preserve-children     Keep child sections, replace only own content
    --dry-run               Show what would change without writing

  Example:
    mdedit replace doc.md "Background" --from-file /tmp/new.md
```

---

## Scope

### v1 — in scope

- All read commands: `outline`, `extract`, `search`, `stats`, `validate`, `frontmatter`, `frontmatter get`
- All write commands: `replace`, `append`, `prepend`, `insert`, `delete`, `rename`, `frontmatter set`, `frontmatter delete`
- Content input: `--content`, `--from-file`, stdin
- Extract output: `--to-file`, `--no-children`
- Replace option: `--preserve-children`
- `--dry-run` on all write commands
- Fuzzy match suggestions on section-not-found
- TTY-aware output formatting
- ATX-style heading parsing only
- YAML frontmatter support

### v2 — out of scope

- `move` (section reordering)
- `promote` / `demote` (heading level shifting)
- `--exec` (extract-transform-replace in one command)
- Atomic multi-edit (JSON ops array)
- `--json` output mode
- Cross-file operations
- Setext-style heading support
- Content fingerprinting / optimistic locking
