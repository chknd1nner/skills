# mdedit v1 — Preamble Write Support & Frontmatter Bare Invocation

**Date:** 2026-03-23
**Branch:** feat/mdedit-v1
**Context:** LLM integration testing (132 tests across 10 Haiku agents) identified two gaps between the spec and implementation. This design addresses both.

## Problem

### Issue 1: `_preamble` write operations not implemented

The spec states that `replace`, `append`, and `prepend` all work on `_preamble`. The implementation currently rejects all three with error messages (exit code 4). Only `extract` and `delete` handle preamble today.

LLM workflows that need to modify preamble content (adding a summary paragraph, fixing document structure by inserting an H1) must use awkward `delete` + `insert` workarounds.

### Issue 2: `frontmatter` bare invocation fails

The spec shows `mdedit frontmatter <file>` as valid syntax. The CLI requires `mdedit frontmatter show <file>`. The error message ("unrecognized subcommand") is unhelpful for LLMs on first attempt.

## Design

### Shared preamble range helper

A new method on `Document` centralises the "where does preamble content live" logic:

```rust
impl Document {
    /// Returns the byte range for preamble content.
    /// - If preamble exists: returns its range
    /// - If no preamble exists: returns an empty range at the insertion point
    ///   (after frontmatter end, or byte 0 if no frontmatter)
    pub fn preamble_write_range(&self) -> Range<usize> {
        if let Some(ref range) = self.preamble {
            range.clone()
        } else {
            let point = self.frontmatter.as_ref()
                .map(|fm| fm.end)
                .unwrap_or(0);
            point..point
        }
    }
}
```

When the range is empty (no existing preamble), splicing at `point..point` naturally inserts content without removing anything.

This method is used by all three write commands. The "create preamble if absent" behavior follows naturally from the empty range — no special-casing needed in each command.

### Whitespace handling for preamble splices

The whitespace normaliser only normalises before headings (ensuring exactly one blank line). It does **not** handle the frontmatter-to-preamble boundary. Therefore each command must handle whitespace at the splice boundaries explicitly.

**Byte layout context:** The parser trims leading newlines from the preamble range. So `preamble.start` points to the first non-newline character of preamble content, and `frontmatter.end` points to the byte after the closing `---\n`. When no preamble exists, the insertion point is `frontmatter.end` (or byte 0).

**Content formatting rules for preamble splices:**

- **When preamble exists:** the existing range already has correct boundaries. For replace, splice new content directly over the range. For append, insert at `range.end`. For prepend, insert at `range.start`. Trailing newline ensured on new content. The normaliser will handle the preamble-to-first-heading boundary (since the heading triggers normalisation).

- **When creating preamble (no existing preamble):** the insertion point sits right after `---\n` (or at byte 0). The new content needs a leading `\n` to create the blank line after frontmatter. Format: `\n{content}\n`. The normaliser will then enforce the blank line before the first heading.

- **When no frontmatter and no preamble:** insertion point is byte 0. No leading `\n` needed (content starts at top of file). The normaliser handles the blank line before the first heading.

In summary: each command prepends `\n` to the splice content **only when** `frontmatter.is_some() && preamble.is_none()` (creating preamble after frontmatter). All other cases rely on the existing range boundaries plus the normaliser's heading-boundary cleanup.

### Output formatting for preamble operations

Preamble output is constructed inline in each command (not via `format_neighborhood`, which requires a `&Section`). This is consistent with how `delete.rs` already handles preamble — it builds output inline rather than delegating.

The output structure follows the same visual pattern as section operations:

- Summary line: `{ACTION}: N lines to "_preamble" (was M lines -> now P lines)` (or `(was M lines, W words -> now N lines, W words)` for replace)
- No "previous section" context (preamble is the first content)
- `-> _preamble` marker for the target
- Content preview with `+` prefix on new lines
- First heading (or `[end of document]`) as next section context

When creating preamble from nothing (was 0 lines), the existing content preview is omitted — only the `+` prefixed new lines are shown.

### Replace `_preamble`

The `ResolvedSection::Preamble` arm in `replace.rs`:

1. Gets the preamble range via `doc.preamble_write_range()`
2. Resolves new content (same `resolve_content` path as regular replace)
3. No-op check: compares trimmed old and new content, returns exit 10 if identical
4. Formats splice content with whitespace rules above
5. Splices new content over the full preamble range
6. No `--preserve-children` consideration (preamble has no children — the flag is accepted but ignored)
7. Output constructed inline with `"_preamble"` as the label
8. Neighborhood context: no "previous section"; first heading (or `[end of document]`) as "next section"

### Append `_preamble`

The `ResolvedSection::Preamble` arm in `append.rs`:

1. Gets the preamble range; splice point is `range.end`
2. Resolves content, ensures trailing newline, applies whitespace rules above
3. Splices content at end of existing preamble (or at insertion point if no preamble exists)
4. Output: `APPENDED: N lines to "_preamble" (was M lines -> now P lines)`
5. Neighborhood: shows tail of existing preamble (omitted if creating), `+` prefix on new lines, first heading as next context

### Prepend `_preamble`

The `ResolvedSection::Preamble` arm in `prepend.rs`:

1. Gets the preamble range; splice point is `range.start`
2. Resolves content, ensures trailing newline, applies whitespace rules above
3. Splices content at start of preamble (right after frontmatter, or byte 0)
4. Output: `PREPENDED: N lines to "_preamble" (was M lines -> now P lines)`
5. Neighborhood: `+` prefix on new lines, head of existing preamble (omitted if creating), first heading as next context

### Content validation

No validation is performed on content for embedded headings. This is consistent with how all other write commands behave — the LLM is responsible for what it puts in the content. Prepending heading-containing content to `_preamble` is a legitimate operation (e.g., adding an H1 title to a document that only has H2-level headings).

### Edge cases

| Scenario | Behavior |
|----------|----------|
| No preamble, no frontmatter | Inserts at byte 0, no leading `\n` |
| No preamble, has frontmatter | Inserts after frontmatter closing `---`, with leading `\n` for blank line |
| Empty preamble (whitespace only) | Replace: no-op if new content also empty. Append/prepend: creates content |
| Document with no headings | Preamble is entire document content; operations work normally |
| Replace with `--preserve-children` | Flag accepted, no effect (preamble has no children) |
| Append/prepend with empty content (`--content ""`) | Proceeds (adds only whitespace; normaliser cleans up) |

### Frontmatter bare invocation

Change in `main.rs` only. The `Frontmatter` variant gains an optional `file` positional arg, and `action` becomes `Option<FrontmatterAction>`:

```rust
Frontmatter {
    /// File path (used when no subcommand given)
    file: Option<String>,
    #[command(subcommand)]
    action: Option<FrontmatterAction>,
},
```

Dispatch logic:

```rust
Commands::Frontmatter { file, action } => match action {
    Some(FrontmatterAction::Show { file }) => commands::frontmatter::run_show(&file),
    Some(FrontmatterAction::Get { file, key }) => commands::frontmatter::run_get(&file, &key),
    Some(FrontmatterAction::Set { file, key, value, dry_run }) => {
        commands::frontmatter::run_set(&file, &key, &value, dry_run)
    }
    Some(FrontmatterAction::Delete { file, key, dry_run }) => {
        commands::frontmatter::run_delete(&file, &key, dry_run)
    }
    None => {
        let file = file.ok_or_else(|| MdeditError::InvalidOperation(
            "file required: mdedit frontmatter <file>".to_string()
        ))?;
        commands::frontmatter::run_show(&file)
    }
}
```

No changes to `FrontmatterAction` enum or any command implementations. All existing subcommands (`show`, `get`, `set`, `delete`) keep their own `file` arg and work exactly as before.

Help text shows `Usage: mdedit frontmatter [FILE] [COMMAND]` which is intuitive.

**Known limitation:** Files literally named `show`, `get`, `set`, or `delete` will be parsed as subcommands rather than as the `file` positional arg. This is a clap ambiguity — subcommand matching takes precedence over positional args. In practice this is a non-issue (markdown files have `.md` extensions).

## Files changed

| File | Change |
|------|--------|
| `src/document.rs` | Add `preamble_write_range()` method |
| `src/commands/replace.rs` | Replace `Preamble` error arm with working implementation |
| `src/commands/append.rs` | Replace `Preamble` error arm with working implementation |
| `src/commands/prepend.rs` | Replace `Preamble` error arm with working implementation |
| `src/main.rs` | Restructure `Frontmatter` variant for optional subcommand |
| `tests/replace.rs` | Add preamble replace tests |
| `tests/append.rs` | Add preamble append tests |
| `tests/prepend.rs` | Add preamble prepend tests |
| `tests/frontmatter.rs` | Add bare invocation test |

## Testing

### Preamble write tests (per command)

1. Replace existing preamble content
2. Replace preamble when none exists (creates it)
3. Replace preamble no-op (identical content, exit 10)
4. Append to existing preamble
5. Append when no preamble exists (creates it)
6. Prepend to existing preamble
7. Prepend when no preamble exists (creates it)
8. Dry-run on each (verify file unchanged)
9. Preamble operations on document with frontmatter
10. Preamble operations on document without frontmatter

### Frontmatter bare invocation tests

1. `mdedit frontmatter doc.md` produces same output as `mdedit frontmatter show doc.md`
2. `mdedit frontmatter` (no file) produces error
3. Existing subcommand forms still work unchanged
