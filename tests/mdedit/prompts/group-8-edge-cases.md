# Group 8: Edge Cases

Test boundary conditions: code fences with `#` characters, empty sections, minimal documents, missing frontmatter, content input modes, and multi-word section names.

---

## Spec Reference

### Code Fence Handling

Uses tree-sitter-md parser. `#` inside code fences are NOT headings — correctness by construction from CST. This means lines like `# comment` inside ````python` or ````rust` code blocks must never appear in the outline or be addressable as sections.

### Empty Sections

Empty section: outputs `[no content]` (TTY) or empty string (pipe).

### Whitespace Normalisation

After any write operation: exactly one blank line between sections, one trailing newline at EOF.

### Content Input Modes

All write commands accept content via three mechanisms:

| Mode | Flag | Description |
|---|---|---|
| Inline | `--content <text>` | Content passed as argument string |
| File | `--from-file <path>` | Content read from a file on disk |
| Stdin | (no flag) | Content read from stdin when stdin is not a TTY |

If none provided: `ERROR: No content provided`. Exit code: `4`.

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
```

Rules:
- Indentation reflects heading hierarchy
- Word count is for the section's own content plus all children
- Empty sections flagged with `⚠ empty`

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

### `frontmatter` Command

```
mdedit frontmatter <file>           # show all fields
mdedit frontmatter get <file> <key>  # get single field
```

Show: `FRONTMATTER:` header with fields. Get: raw value. If no frontmatter exists, error behavior applies.

### Section Addressing

All commands that take a `<section>` argument resolve it using these rules:

| Input | Matches |
|---|---|
| `"Background"` | Any heading with text "Background", any level |
| `"## Background"` | Only H2 headings with text "Background" |
| `"Background/Prior Work"` | "Prior Work" that is a child of "Background" |

Matching is exact (case-sensitive) on the heading text.

---

## Available Sample Files

- `pristine/code-fences.md` — "Code Examples" (H1) with Python and Rust code fences containing `#`, `##`, `###` characters that must not be parsed as headings. Real sections: Code Examples (H1), Python Examples (H2), Rust Examples (H2), Indented Code (H2), Real Section After Code (H2).
- `pristine/frontmatter-doc.md` — 5 frontmatter fields, H1 "Research Notes", sections including Introduction, Background (with Prior Work, Limitations), Methods, Results, Edge Cases, Conclusion. Clean structure.
- `pristine/large-document.md` — "Project Architecture" with 29 sections, 4 levels deep (H1-H4). Includes deeply nested sections like Frontend/Components/Atoms.
- `pristine/minimal.md` — Single H1 "Simple Document" with 2 short paragraphs. No subheadings.
- `pristine/no-frontmatter.md` — No YAML frontmatter. Has sections starting directly with headings.
- `pristine/validation-problems.md` — Has intentional issues including `## Empty Section` (no content between this heading and the next).

---

## Tests

### Test 1: Code fences — outline excludes false headings

**Command:**
```bash
{{BINARY}} outline pristine/code-fences.md
```

**Expected:** The `#` characters inside code fences (both fenced with triple backticks and indented code blocks) must NOT be treated as headings. The outline should show exactly 5 headings:
1. H1 "Code Examples"
2. H2 "Python Examples"
3. H2 "Rust Examples"
4. H2 "Indented Code"
5. H2 "Real Section After Code"

If the outline shows entries like "This is NOT a heading", "Neither is this", or any other text from inside code fences, the test FAILS — code fence detection is broken.

### Test 2: Code fences — extract preserves code block content

**Command:**
```bash
{{BINARY}} extract pristine/code-fences.md "Python Examples"
```

**Expected:** The extracted content includes the Python code fence verbatim — the ````python` opening, the code lines (which contain `#` comment characters), and the closing ```` `` ```. The code block content must be preserved exactly as written, not interpreted or modified. Exit code `0`.

### Test 3: Empty section — extract behavior

**Command:**
```bash
{{BINARY}} extract pristine/validation-problems.md "Empty Section"
```

**Expected:** The section `## Empty Section` has no content between its heading and the next heading. In TTY mode, the output should show `[no content]`. Exit code `0`. The command must not error — empty sections are valid, they just have no content.

### Test 4: Large document — outline shows all sections

**Command:**
```bash
{{BINARY}} outline pristine/large-document.md
```

**Expected:** All 29 sections are shown with correct hierarchy. The output should include:
- H1: Project Architecture
- H2: Overview, Frontend, Backend, Infrastructure, Security, Appendix
- H3 under Frontend: Components, State Management, Routing
- H4 under Components: Atoms, Molecules, Organisms
- H3 under Backend: API Layer, Database, Background Jobs
- H4 under API Layer: Authentication, Rate Limiting
- H4 under Database: Schema, Migrations
- H3 under Infrastructure: Kubernetes, Monitoring, CI/CD
- H3 under Security: Access Control, Data Encryption, Audit Logging
- H3 under Appendix: Glossary, References, Change Log

Each heading includes word count and line range. Indentation correctly reflects the nesting depth.

### Test 5: Large document — deeply nested extraction

**Command:**
```bash
{{BINARY}} extract pristine/large-document.md "Atoms"
```

**Expected:** Extracts the H4 "Atoms" section which is deeply nested under Frontend/Components/Atoms. The content is extracted successfully despite being at the 4th heading level. Exit code `0`.

### Test 6: Minimal document — outline, extract, and replace

**Commands:**
```bash
{{BINARY}} outline pristine/minimal.md
{{BINARY}} extract pristine/minimal.md "Simple Document"
cp pristine/minimal.md test-6.md
{{BINARY}} replace test-6.md "Simple Document" --content "Replaced."
cat test-6.md
```

**Expected:**
1. `outline` shows only H1 "Simple Document" with word count and line range. No other headings.
2. `extract` shows the content of the single section (2 short paragraphs). Exit code `0`.
3. After `replace`, `cat test-6.md` shows the H1 heading `# Simple Document` followed by "Replaced." as the only content. The file should end with exactly one trailing newline. Exit code `0` for the replace.

### Test 7: No frontmatter — frontmatter show and extract

**Commands:**
```bash
{{BINARY}} frontmatter show pristine/no-frontmatter.md; echo "EXIT: $?"
{{BINARY}} extract pristine/no-frontmatter.md "Section One"
```

**Expected:**
1. `frontmatter show` on a file without frontmatter should produce an error or indicate no frontmatter found. Check the exit code — it should be non-zero (likely `3` for file error or a specific frontmatter error).
2. `extract` should work normally on a file without frontmatter — sections are still addressable. Output shows the Section One content. Exit code `0`.

### Test 8: Replace with --content flag

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-8.md
{{BINARY}} replace test-8.md "Introduction" --content "Test content."
cat test-8.md
```

**Expected:** The `replace` command succeeds with `REPLACED:` output showing before/after metrics. After the operation, `cat test-8.md` shows the file with `## Introduction` followed by "Test content." instead of the original introduction content. Frontmatter and all other sections remain intact. Exit code `0`.

### Test 9: Empty stdin — exit 4

**Command:**
```bash
cp pristine/frontmatter-doc.md test-9.md
< /dev/null {{BINARY}} replace test-9.md "Introduction"; echo "EXIT: $?"
```

**Expected:** With stdin redirected from `/dev/null` and no `--content` or `--from-file` flag, no content is provided. The command should fail with an error about no content provided. Exit code must be `4`.

### Test 10: Stdin with content

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-10.md
echo "Stdin content here." | {{BINARY}} replace test-10.md "Introduction"
{{BINARY}} extract test-10.md "Introduction"
```

**Expected:** The `replace` command reads content from stdin (the pipe). It succeeds with `REPLACED:` output. The subsequent `extract` should show "Stdin content here." as the Introduction content. Exit code `0` for both commands.

### Test 11: Multi-line content via --content flag

**Commands:**
```bash
cp pristine/frontmatter-doc.md test-11.md
{{BINARY}} replace test-11.md "Introduction" --content "Line one.\nLine two.\nLine three."
{{BINARY}} extract test-11.md "Introduction"
```

**Expected:** Test what happens with `\n` in the `--content` argument. The shell may or may not expand `\n` to actual newlines (this depends on how the binary parses the argument). Run the command and observe: does the content appear as three separate lines, or as a single line with literal `\n` characters? Report what actually happens. Exit code `0` if the replacement succeeds regardless of newline handling.

### Test 12: Multi-word section names

**Commands:**
```bash
{{BINARY}} extract pristine/frontmatter-doc.md "Edge Cases"
{{BINARY}} extract pristine/frontmatter-doc.md "Prior Work"
```

**Expected:** Both multi-word section names resolve correctly. "Edge Cases" matches `### Edge Cases` under Results. "Prior Work" matches `### Prior Work` under Background. Both commands output the section content with `SECTION:` header. Exit code `0` for both.
