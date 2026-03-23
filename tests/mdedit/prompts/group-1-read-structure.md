# Group 1: Read — Structure

Test the structural inspection commands: `outline`, `stats`, and `validate`.

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

### `outline` Command

```
mdedit outline <file> [--max-depth <N>]
```

Output format:

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

Rules:
- Indentation reflects heading hierarchy
- Word count is for the section's own content plus all children
- Empty sections flagged with `⚠ empty`
- `--max-depth <N>` shows headings up to level N only

### `stats` Command

```
mdedit stats <file>
```

Output format:

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

Rules:
- Percentages relative to total document word count
- `← largest` annotation on the section with the most words
- `← empty` annotation on sections with 0 words

### `validate` Command

```
mdedit validate <file>
```

Output when issues found:

```
INVALID: document.md — 3 issues

  ⚠ Line 45: H4 "#### Detail" has no H3 parent (skipped level)
  ⚠ Line 89: Section "## TODO" is empty (0 content lines)
  ℹ Line 12: Duplicate heading text "## Notes" (also at line 67)
```

Output when clean:

```
VALID: document.md — 7 sections, max depth 3, no issues
```

Checks performed:
- Skipped heading levels (e.g., H2 followed directly by H4 with no H3)
- Empty sections (0 content lines between heading and next heading)
- Duplicate heading text at same level

Exit code: `5` if any `⚠` warnings, `0` if clean or only `ℹ` informational.

---

## Available Sample Files

- `pristine/frontmatter-doc.md` — 5 frontmatter fields (title, tags, date, draft, author), H1 title "Research Notes", 8 sections across 3 levels (H1, H2, H3). Sections: Introduction, Background, Prior Work, Limitations, Methods, Evaluation Criteria, Results, Performance Data, Edge Cases, Conclusion, Future Work, Acknowledgements. Clean structure (no validation issues).
- `pristine/large-document.md` — "Project Architecture" with 29 sections, 4 levels deep (H1-H4). Includes: Overview, Frontend, Components, Atoms, Molecules, Organisms, State Management, Routing, Backend, API Layer, Authentication, Rate Limiting, Database, Schema, Migrations, Background Jobs, Infrastructure, Kubernetes, Monitoring, CI/CD, Security, Access Control, Data Encryption, Audit Logging, Appendix, Glossary, References, Change Log.
- `pristine/validation-problems.md` — "Problem Document" with intentional issues: H4 "Skipped Level" under H2 (no H3 parent), empty "## Empty Section" (no content lines), duplicate "## Notes" headings at same level.
- `pristine/minimal.md` — Single H1 "Simple Document" + 2 short paragraphs. No subheadings.
- `pristine/code-fences.md` — "Code Examples" with Python and Rust code fences containing `#`, `##`, `###` characters that must not be parsed as headings. Real sections: Code Examples (H1), Python Examples (H2), Rust Examples (H2), Indented Code (H2), Real Section After Code (H2).

---

## Tests

### Test 1: Outline of multi-section document

**Command:**
```bash
{{BINARY}} outline pristine/frontmatter-doc.md
```

**Expected:** Output shows the heading hierarchy for all sections with word counts and line ranges. The H1 "Research Notes" appears at top with total word count and line count. H2 sections (Introduction, Background, Methods, Results, Conclusion) are indented once. H3 sections (Prior Work, Limitations, Evaluation Criteria, Performance Data, Edge Cases, Future Work, Acknowledgements) are indented twice under their parent H2. Every heading line includes `— N words (lines X–Y)` format. Verify there are exactly 12 heading entries (1 H1 + 5 H2 + 6 H3).

### Test 2: Outline with --max-depth 2

**Command:**
```bash
{{BINARY}} outline pristine/large-document.md --max-depth 2
```

**Expected:** Only H1 and H2 headings are shown. The H1 "Project Architecture" appears at top. H2 sections shown: Overview, Frontend, Backend, Infrastructure, Security, Appendix. No H3 or H4 headings should appear (no Components, State Management, Routing, API Layer, Database, Background Jobs, Kubernetes, Monitoring, CI/CD, Access Control, Data Encryption, Audit Logging, Glossary, References, Change Log). No H4 headings (Atoms, Molecules, Organisms, Authentication, Rate Limiting, Schema, Migrations).

### Test 3: Outline with code fences

**Command:**
```bash
{{BINARY}} outline pristine/code-fences.md
```

**Expected:** The `#` characters inside code fences (both fenced and indented) must NOT be treated as headings. The outline should show exactly 5 headings: H1 "Code Examples", H2 "Python Examples", H2 "Rust Examples", H2 "Indented Code", H2 "Real Section After Code". If the outline shows entries like "This is NOT a heading" or "Neither is this", the code fence detection is broken.

### Test 4: Outline of minimal document

**Command:**
```bash
{{BINARY}} outline pristine/minimal.md
```

**Expected:** Shows only the H1 "Simple Document" with its word count and line range. The file has 2 short paragraphs of content. Verify the word count is reasonable for "Just a heading and some content. Nothing fancy." + "This is a second paragraph." (approximately 15 words).

### Test 5: Stats of multi-section document

**Command:**
```bash
{{BINARY}} stats pristine/frontmatter-doc.md
```

**Expected:** Output starts with `STATS: frontmatter-doc.md` line showing total words, lines, and section count. Each H2 section shows a percentage. The section with the most words is annotated `← largest`. If any section has 0 words, it is annotated `← empty`. Percentages should be relative to total document word count. Verify that the listed percentages are plausible (they should roughly add up considering child sections are included in parent counts for display purposes).

### Test 6: Stats of large document

**Command:**
```bash
{{BINARY}} stats pristine/large-document.md
```

**Expected:** Output shows all 29 sections from large-document.md with correct nesting. H3 sections are indented under their H2 parents. H4 sections are indented under their H3 parents. The `← largest` annotation appears on exactly one section (the one with the highest word count). Verify the header line reports the correct total section count.

### Test 7: Validate clean document

**Command:**
```bash
{{BINARY}} validate pristine/frontmatter-doc.md; echo "EXIT: $?"
```

**Expected:** Output shows `VALID: frontmatter-doc.md` with section count, max depth, and "no issues". Exit code is `0`. This file has clean structure — no skipped levels, no empty sections, no duplicate headings at the same level.

### Test 8: Validate document with problems

**Command:**
```bash
{{BINARY}} validate pristine/validation-problems.md; echo "EXIT: $?"
```

**Expected:** Output shows `INVALID: validation-problems.md` with issue count. The following issues should be reported:
1. Skipped heading level: H4 "#### Skipped Level" at line 7 appears under H2 "## Overview" with no H3 in between — should produce a `⚠` warning about skipped level.
2. Empty section: "## Empty Section" at line 11 has no content lines before the next heading at line 13 — should produce a `⚠` warning about empty section.
3. Duplicate headings: "## Notes" appears twice (lines 17 and 21) at the same level — should produce an `ℹ` informational notice about duplicate heading text.

Exit code must be `5` (because there are `⚠` warnings).

### Test 9: Exit code correctness for validate

Run validate on both files and confirm the correct exit codes:

**Commands:**
```bash
{{BINARY}} validate pristine/frontmatter-doc.md; echo "EXIT: $?"
{{BINARY}} validate pristine/validation-problems.md; echo "EXIT: $?"
```

**Expected:** First command exits `0` (clean document). Second command exits `5` (has `⚠` warnings). This test explicitly verifies the exit code contract: `0` for clean/info-only, `5` for warnings.
