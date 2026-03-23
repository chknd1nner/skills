# Group 2: Read — Content

Test the content retrieval commands: `extract` and `search`.

---

## Spec Reference

### Section Addressing

All commands that take a `<section>` argument resolve it using these rules:

| Input | Matches |
|---|---|
| `"Background"` | Any heading with text "Background", any level |
| `"## Background"` | Only H2 headings with text "Background" |
| `"Background/Prior Work"` | "Prior Work" that is a child of "Background" |

Matching is exact (case-sensitive) on the heading text. If multiple headings match, exit 2 with candidate list. If no heading matches, exit 1 with fuzzy suggestions. `_preamble` addresses content before first heading (after frontmatter).

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

### `extract` Command

```
mdedit extract <file> <section> [--no-children] [--to-file <path>]
```

**TTY output format:**
```
SECTION: "## Background" — 312 words, lines 20–67, 2 children

The system operates under three constraints...
### Prior Work
Previous approaches include...
```

The first line is a metadata header showing the section name, word count, line range, and child count. The remaining lines are the raw markdown content of the section.

**Pipe/--to-file output:** Raw markdown only, no metadata header.

**With `--no-children`:** Excludes child sections from the output. The metadata header notes the exclusion count (e.g., "2 children excluded").

**With `--to-file <path>`:** Writes raw content to the specified file. Stdout shows a confirmation line:
```
EXTRACTED: "## Background" (12 lines, 312 words) → /tmp/section.md
```

**Edge cases:**
- Empty section: outputs `[no content]` in TTY mode, or empty string in pipe mode.
- `_preamble`: extracts content before the first heading, after frontmatter. If there is no preamble content, behavior may be empty or error.

**Error cases:**
- Section not found: exit 1, with fuzzy suggestions for similar headings.
- Ambiguous match (multiple headings with same text): exit 2, lists all candidates with their line numbers.

### `search` Command

```
mdedit search <file> <query> [--case-sensitive]
```

Output format:
```
SEARCH: "constraint" — 4 matches in 2 sections

  ## Background (3 matches)
    Line 22: The system operates under three |constraints|...
    Line 25: The first |constraint| requires that...
    Line 31: The second |constraint| ensures...

  ## Conclusion (1 match)
    Line 162: ...satisfying all |constraints| simultaneously.
```

Rules:
- Case-insensitive by default
- `--case-sensitive` flag for exact case matching
- Results grouped by section
- Matches highlighted with `|pipe|` delimiters around the matching text
- Line numbers shown for each match
- Header line shows total match count and section count

---

## Available Sample Files

- `pristine/frontmatter-doc.md` — 5 frontmatter fields, H1 "Research Notes" with sections: Introduction, Background, Prior Work, Limitations, Methods, Evaluation Criteria, Results, Performance Data, Edge Cases, Conclusion, Future Work, Acknowledgements. Contains text about markdown editing tools, tree-sitter, parsing approaches, and benchmark results.
- `pristine/preamble-doc.md` — Has frontmatter (title, version) + two paragraphs of preamble text before `# Main Document`. Preamble says "This is preamble content that appears before any heading." and "This paragraph is also part of the preamble." Sections: Main Document, First Section, Second Section, Nested Under Second, Third Section.
- `pristine/large-document.md` — 29 sections, 4 levels deep (H1-H4) describing a project architecture.
- `pristine/code-fences.md` — Code fences with `#` characters inside. Real headings: Code Examples (H1), Python Examples (H2), Rust Examples (H2), Indented Code (H2), Real Section After Code (H2). Code blocks contain comments like "This is NOT a heading".
- `pristine/self/duplicate-headings.md` — Has two `## Summary` sections at the same level (lines 3 and 9), plus a `## Unique Section`.
- `pristine/self/multi-level-headings.md` — Has `## Overview` (H2) and `### Overview` (H3) at different levels, plus `## Methods` (H2) and `### Methods` (H3).

---

## Tests

### Test 1: Basic extract

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Introduction"
```

**Expected:** Output starts with a `SECTION:` metadata header line containing the heading name "Introduction", a word count, a line range, and a child count (0 children for Introduction). After the metadata header, the raw content of the Introduction section appears. The content should include the text about "research notes on structured markdown editing tools" and "evaluate different approaches and select the best one". No child headings should appear (Introduction has no children).

### Test 2: Level-specific extract

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "## Background"
```

**Expected:** Output starts with `SECTION:` header for "## Background". Because the level prefix `##` is specified, only the H2 heading "Background" matches. The content should include the Background section's own text about markdown being "widely used for documentation" AND its children (### Prior Work and ### Limitations) with their content.

### Test 3: Nested path extract

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Background/Prior Work"
```

**Expected:** Output starts with `SECTION:` header for "Prior Work" (the child of Background). Content should include the list of tools: mdcat, pandoc, and regex-based approaches. This uses the hierarchical path syntax — "Prior Work" that is specifically a child of "Background".

### Test 4: Extract with --no-children

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Background" --no-children
```

**Expected:** Output starts with `SECTION:` header. The metadata should note that children were excluded (Background has 2 children: Prior Work and Limitations). The content should include only the Background section's own text ("Markdown is widely used for documentation...") but NOT include the "### Prior Work" or "### Limitations" headings or their content.

### Test 5: Extract with --to-file

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Introduction" --to-file /tmp/mdedit-test-extract.md
```

Then verify the written file:
```bash
cat /tmp/mdedit-test-extract.md
```

**Expected:** The stdout from the extract command shows an `EXTRACTED:` confirmation line with the section name, line count, word count, and the destination path `/tmp/mdedit-test-extract.md`. The file at `/tmp/mdedit-test-extract.md` contains raw markdown only (no `SECTION:` metadata header) — just the section content text.

### Test 6: Extract _preamble from preamble-doc

**Command:**
```bash
{{BINARY}} extract pristine/preamble-doc.md "_preamble"
```

**Expected:** Output returns the preamble content — the text that appears after the frontmatter but before the first heading `# Main Document`. This should include "This is preamble content that appears before any heading." and "This paragraph is also part of the preamble." The frontmatter block itself (title, version) must NOT be included in the output.

### Test 7: Extract _preamble from file without preamble

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "_preamble"
```

**Expected:** frontmatter-doc.md has frontmatter followed immediately by `# Research Notes` with no text in between. There is no preamble content. Verify the behavior — this should either return empty/`[no content]` or produce an appropriate error. The key point is that it does NOT return the frontmatter block itself.

### Test 8: Extract nonexistent section

**Command:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Nonexistent"; echo "EXIT: $?"
```

**Expected:** Exit code is `1` (section not found). The error output should include fuzzy suggestions of similar heading names from the document. It should NOT silently succeed or return empty content.

### Test 9: Extract ambiguous section (duplicate headings)

**Command:**
```bash
{{BINARY}} extract pristine/self/duplicate-headings.md "Summary"; echo "EXIT: $?"
```

**Expected:** Exit code is `2` (ambiguous match). The file has two `## Summary` headings (at lines 3 and 9). The error output should list both candidates with their line numbers so the user can disambiguate.

### Test 10: Search with matches

**Command:**
```bash
{{BINARY}} search pristine/frontmatter-doc.md "constraint"
```

**Expected:** Output starts with `SEARCH:` header showing the query, total match count, and number of sections containing matches. The word "constraint" (or "constraints") appears in frontmatter-doc.md in the Limitations section ("they can't address sections by name") — search for actual occurrences. Results are grouped by section name. Each match shows the line number and the matching text with `|pipe|` delimiters highlighting the match. Search is case-insensitive by default so "constraint" matches "Constraint" too.

### Test 11: Case-sensitive search with no matches

**Command:**
```bash
{{BINARY}} search pristine/frontmatter-doc.md "CONSTRAINT" --case-sensitive
```

**Expected:** With `--case-sensitive` flag, the search looks for the exact uppercase string "CONSTRAINT". The document content uses lowercase. This should return zero matches. Verify the output indicates no matches found.

### Test 12: Search with zero matches

**Command:**
```bash
{{BINARY}} search pristine/frontmatter-doc.md "xyznonexistent"
```

**Expected:** The query string "xyznonexistent" does not appear anywhere in the document. Output should indicate zero matches. No section groups should be listed.

### Test 13: Search inside code fences

**Command:**
```bash
{{BINARY}} search pristine/code-fences.md "heading"
```

**Expected:** The code fence content IS searchable. The file contains text like "This is NOT a heading", "Neither is this", "Not a heading either", "Still not a heading" inside code blocks. The search should find these occurrences. Verify that matches are reported with their line numbers and section groupings, and that the matching text is highlighted with `|pipe|` delimiters.
