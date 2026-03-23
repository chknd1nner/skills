# mdedit Preamble Write Support & Frontmatter Bare Invocation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `_preamble` support to replace, append, and prepend commands, and make `mdedit frontmatter <file>` work without requiring the `show` subcommand.

**Architecture:** A shared `preamble_write_range()` method on `Document` provides the byte range for all three preamble write commands. Each command's `ResolvedSection::Preamble` arm builds output inline (matching the pattern in `delete.rs`). The frontmatter change restructures clap's `Frontmatter` variant to accept an optional subcommand.

**Tech Stack:** Rust, clap 4 (derive API), assert_cmd + predicates (testing)

**Spec:** `docs/plans/2026-03-23-mdedit-preamble-and-frontmatter-design.md`

---

### Task 1: Add `preamble_write_range()` to Document

**Files:**
- Modify: `claude-code-only/mdedit/src/document.rs:37-67` (inside `impl Document`)

- [ ] **Step 1: Write unit test for `preamble_write_range`**

Add this test block at the end of `claude-code-only/mdedit/src/document.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preamble_write_range_with_preamble() {
        let doc = Document {
            source: "---\ntitle: x\n---\n\nPreamble text.\n\n# Heading\n".to_string(),
            frontmatter: Some(0..17),
            preamble: Some(18..33), // "Preamble text.\n"
            sections: vec![],
        };
        assert_eq!(doc.preamble_write_range(), 18..33);
    }

    #[test]
    fn preamble_write_range_no_preamble_with_frontmatter() {
        let doc = Document {
            source: "---\ntitle: x\n---\n\n# Heading\n".to_string(),
            frontmatter: Some(0..17),
            preamble: None,
            sections: vec![],
        };
        // Insertion point is at frontmatter.end
        let range = doc.preamble_write_range();
        assert_eq!(range.start, 17);
        assert_eq!(range.end, 17);
        assert!(range.is_empty());
    }

    #[test]
    fn preamble_write_range_no_preamble_no_frontmatter() {
        let doc = Document {
            source: "# Heading\n".to_string(),
            frontmatter: None,
            preamble: None,
            sections: vec![],
        };
        let range = doc.preamble_write_range();
        assert_eq!(range.start, 0);
        assert_eq!(range.end, 0);
        assert!(range.is_empty());
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd claude-code-only/mdedit && cargo test --lib document::tests -- --nocapture`
Expected: FAIL — `preamble_write_range` method does not exist.

- [ ] **Step 3: Implement `preamble_write_range`**

Add this method inside the `impl Document` block in `claude-code-only/mdedit/src/document.rs`, after the `byte_to_line` method (line 66):

```rust
    /// Returns the byte range for preamble content, for write operations.
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd claude-code-only/mdedit && cargo test --lib document::tests -- --nocapture`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add claude-code-only/mdedit/src/document.rs
git commit -m "feat(mdedit): add preamble_write_range() helper to Document"
```

---

### Task 2: Implement `_preamble` support in `replace`

**Files:**
- Modify: `claude-code-only/mdedit/src/commands/replace.rs:35-42` (replace the `Preamble` error arm)
- Modify: `claude-code-only/mdedit/tests/replace.rs` (add preamble tests)

**Context:** The existing `Preamble` arm at line 37-41 returns an `InvalidOperation` error. Replace it with a working implementation. Output is built inline (not via `format_neighborhood` which requires `&Section`). Follow the pattern in `delete.rs` lines 35-101 for inline preamble output.

- [ ] **Step 1: Write failing tests for preamble replace**

Add these tests at the end of `claude-code-only/mdedit/tests/replace.rs`:

```rust
#[test]
fn replace_preamble_existing() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nOld preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "New preamble."])
        .assert()
        .success()
        .stdout(predicate::str::contains("REPLACED"))
        .stdout(predicate::str::contains("_preamble"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New preamble."));
    assert!(!result.contains("Old preamble."));
    assert!(result.contains("# Heading")); // heading preserved
    assert!(result.contains("Content.")); // section content preserved
    drop(dir);
}

#[test]
fn replace_preamble_creates_when_absent() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "Created preamble."])
        .assert()
        .success()
        .stdout(predicate::str::contains("REPLACED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Created preamble."));
    assert!(result.contains("# Heading"));
    // Preamble should be between frontmatter and heading
    let preamble_pos = result.find("Created preamble.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(preamble_pos < heading_pos);
    drop(dir);
}

#[test]
fn replace_preamble_noop() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "Existing."])
        .assert()
        .code(10)
        .stdout(predicate::str::contains("NO CHANGE"));
    drop(dir);
}

#[test]
fn replace_preamble_dry_run() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nOld.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"))
        .stdout(predicate::str::contains("WOULD REPLACE"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Old.")); // file unchanged
    drop(dir);
}

#[test]
fn replace_preamble_no_frontmatter() {
    let (dir, file) = common::temp_md_file(
        "Old preamble text.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "New preamble."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New preamble."));
    assert!(!result.contains("Old preamble text."));
    drop(dir);
}

#[test]
fn replace_preamble_preserve_children_accepted() {
    // --preserve-children is accepted but has no effect (preamble has no children)
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nOld.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble",
                "--content", "New.", "--preserve-children"])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New."));
    drop(dir);
}

#[test]
fn replace_preamble_no_headings_document() {
    // Document with no headings — preamble is entire content
    let (dir, file) = common::temp_md_file(
        "Just some text.\nAnother line.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "Replaced."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Replaced."));
    assert!(!result.contains("Just some text."));
    drop(dir);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd claude-code-only/mdedit && cargo test --test replace replace_preamble -- --nocapture`
Expected: FAIL — all 5 tests fail with "replace does not support _preamble" error.

- [ ] **Step 3: Implement preamble support in replace.rs**

In `claude-code-only/mdedit/src/commands/replace.rs`, add `use crate::counting::word_count;` to imports (line 3, it's already there), and add `use crate::output::format_section_preview;` to imports.

Replace the `Preamble` arm (lines 37-41) with:

```rust
        ResolvedSection::Preamble => {
            // Replace preamble content
            let preamble_range = doc.preamble_write_range();
            let old_content = &source[preamble_range.clone()];

            // Resolve new content
            let new_content_raw = resolve_content(content, from_file)?;

            // Ensure trailing newline
            let new_content_with_newline = format!(
                "{}{}",
                new_content_raw,
                if new_content_raw.ends_with('\n') { "" } else { "\n" }
            );

            // No-op check
            if old_content.trim() == new_content_raw.trim() {
                return Err(MdeditError::NoOp(
                    "Preamble content is identical to replacement".to_string(),
                ));
            }

            // Whitespace: prepend \n only when creating preamble after frontmatter
            let splice_content = if doc.frontmatter.is_some() && doc.preamble.is_none() {
                format!("\n{}", new_content_with_newline)
            } else {
                new_content_with_newline.clone()
            };

            // Metrics
            let old_lines = old_content.trim().lines().count();
            let new_lines = new_content_raw.trim().lines().count();
            let old_words = word_count(&source, &preamble_range);
            let new_words = word_count(&new_content_raw, &(0..new_content_raw.len()));

            // Build output
            let action_label = if dry_run { "WOULD REPLACE" } else { "REPLACED" };
            let mut output = String::new();
            if dry_run {
                output.push_str("DRY RUN \u{2014} no changes written\n\n");
            }
            output.push_str(&format!(
                "{}: \"_preamble\" (was {} lines, {} words \u{2192} now {} lines, {} words)\n",
                action_label, old_lines, old_words, new_lines, new_words
            ));

            // Warnings
            if old_lines > 0 && new_lines < old_lines {
                let reduction_pct = ((old_lines - new_lines) * 100) / old_lines;
                if reduction_pct > 50 {
                    output.push_str(&format!(
                        "\u{26a0} Large reduction: {} lines \u{2192} {} lines\n",
                        old_lines, new_lines
                    ));
                }
            }

            output.push('\n');

            // Target with → marker
            output.push_str("\u{2192} _preamble\n");
            let new_non_empty: Vec<&str> = new_content_raw.lines()
                .filter(|l| !l.trim().is_empty()).collect();
            if let Some(first) = new_non_empty.first() {
                output.push_str(&format!("  {}\n", first));
            }
            let remaining = if new_non_empty.len() > 1 { new_non_empty.len() - 1 } else { 0 };
            if remaining > 1 {
                output.push_str(&format!("  [{} more lines]\n", remaining - 1));
                if let Some(last) = new_non_empty.last() {
                    if new_non_empty.len() > 1 {
                        output.push_str(&format!("  {}\n", last));
                    }
                }
            } else if remaining == 1 {
                if let Some(last) = new_non_empty.last() {
                    output.push_str(&format!("  {}\n", last));
                }
            }

            // Next section context
            output.push('\n');
            if let Some(first_section) = doc.sections.first() {
                output.push_str(&format_section_preview(&doc, first_section));
            } else {
                output.push_str("  [end of document]\n");
            }

            if dry_run {
                print!("{}", output);
                return Ok(());
            }

            // Splice
            let new_source = format!(
                "{}{}{}",
                &source[..preamble_range.start],
                splice_content,
                &source[preamble_range.end..]
            );
            let normalised = normalise(&new_source);
            std::fs::write(file, &normalised)
                .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

            print!("{}", output);
            return Ok(());
        }
```

Also add `use crate::output::format_section_preview;` to the imports at the top. The existing imports are:

```rust
use crate::addressing::{resolve, ResolvedSection};
use crate::content::resolve_content;
use crate::counting::word_count;
use crate::error::MdeditError;
use crate::output::format_neighborhood;
use crate::parser;
use crate::whitespace::normalise;
```

Add `format_section_preview` to the `output` import:

```rust
use crate::output::{format_neighborhood, format_section_preview};
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd claude-code-only/mdedit && cargo test --test replace -- --nocapture`
Expected: All tests PASS (existing 10 + new 7 = 17 total).

- [ ] **Step 5: Commit**

```bash
git add claude-code-only/mdedit/src/commands/replace.rs claude-code-only/mdedit/tests/replace.rs
git commit -m "feat(mdedit): implement _preamble support for replace command"
```

---

### Task 3: Implement `_preamble` support in `append`

**Files:**
- Modify: `claude-code-only/mdedit/src/commands/append.rs:33-40` (replace the `Preamble` error arm)
- Modify: `claude-code-only/mdedit/tests/append.rs` (add preamble tests)

**Context:** Same pattern as replace. Splice point is `preamble_range.end`. Output shows tail of existing preamble + `+` prefixed new lines.

- [ ] **Step 1: Write failing tests for preamble append**

Add these tests at the end of `claude-code-only/mdedit/tests/append.rs`:

```rust
#[test]
fn append_to_preamble_existing() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "Appended line."])
        .assert()
        .success()
        .stdout(predicate::str::contains("APPENDED"))
        .stdout(predicate::str::contains("_preamble"))
        .stdout(predicate::str::contains("+ Appended line."));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Existing preamble."));
    assert!(result.contains("Appended line."));
    let existing_pos = result.find("Existing preamble.").unwrap();
    let appended_pos = result.find("Appended line.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(existing_pos < appended_pos);
    assert!(appended_pos < heading_pos);
    drop(dir);
}

#[test]
fn append_to_preamble_creates_when_absent() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "New preamble."])
        .assert()
        .success()
        .stdout(predicate::str::contains("APPENDED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New preamble."));
    let preamble_pos = result.find("New preamble.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(preamble_pos < heading_pos);
    drop(dir);
}

#[test]
fn append_to_preamble_dry_run() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("New.")); // file unchanged
    drop(dir);
}

#[test]
fn append_to_preamble_no_frontmatter() {
    let (dir, file) = common::temp_md_file(
        "Existing preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "Appended."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Existing preamble."));
    assert!(result.contains("Appended."));
    let existing_pos = result.find("Existing preamble.").unwrap();
    let appended_pos = result.find("Appended.").unwrap();
    assert!(existing_pos < appended_pos);
    drop(dir);
}

#[test]
fn append_to_preamble_no_headings_document() {
    // Document with no headings — preamble is entire content
    let (dir, file) = common::temp_md_file(
        "Just some text.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "Appended."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Just some text."));
    assert!(result.contains("Appended."));
    let existing_pos = result.find("Just some text.").unwrap();
    let appended_pos = result.find("Appended.").unwrap();
    assert!(existing_pos < appended_pos);
    drop(dir);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd claude-code-only/mdedit && cargo test --test append append_to_preamble -- --nocapture`
Expected: FAIL — all 5 tests fail with "append does not yet support _preamble" error.

- [ ] **Step 3: Implement preamble support in append.rs**

In `claude-code-only/mdedit/src/commands/append.rs`, replace the `Preamble` arm (lines 35-39) with:

```rust
        ResolvedSection::Preamble => {
            // Append to preamble content
            let preamble_range = doc.preamble_write_range();
            let existing_content = &source[preamble_range.clone()];

            // Resolve new content
            let append_content_raw = resolve_content(content, from_file)?;
            let append_content_with_newline = format!(
                "{}{}",
                append_content_raw,
                if append_content_raw.ends_with('\n') { "" } else { "\n" }
            );

            // Whitespace: prepend \n only when creating preamble after frontmatter
            let splice_content = if doc.frontmatter.is_some() && doc.preamble.is_none() {
                format!("\n{}", append_content_with_newline)
            } else {
                append_content_with_newline.clone()
            };

            // Metrics
            let existing_lines = existing_content.trim().lines().count();
            let appended_lines = append_content_raw.lines().count();
            let combined = format!("{}{}", existing_content, append_content_with_newline);
            let combined_lines = combined.trim().lines().count();

            // Build output
            let action_label = if dry_run { "WOULD APPEND" } else { "APPENDED" };
            let mut output = String::new();
            if dry_run {
                output.push_str("DRY RUN \u{2014} no changes written\n\n");
            }
            output.push_str(&format!(
                "{}: {} lines to \"_preamble\" (was {} lines \u{2192} now {} lines)\n",
                action_label, appended_lines, existing_lines, combined_lines
            ));

            output.push('\n');

            // Target with → marker
            output.push_str("\u{2192} _preamble\n");

            // Tail of existing content (if any)
            let existing_text = existing_content.trim();
            let existing_non_empty: Vec<&str> = existing_text.lines()
                .filter(|l| !l.trim().is_empty()).collect();
            if existing_non_empty.len() > 2 {
                output.push_str("  [existing content...]\n");
                output.push_str(&format!("  [{} more lines]\n", existing_non_empty.len() - 1));
                if let Some(last) = existing_non_empty.last() {
                    output.push_str(&format!("  {}\n", last));
                }
            } else {
                for line in &existing_non_empty {
                    output.push_str(&format!("  {}\n", line));
                }
            }

            // Appended lines with + prefix
            for line in append_content_raw.lines() {
                output.push_str(&format!("+ {}\n", line));
            }

            // Next section context
            output.push('\n');
            if let Some(first_section) = doc.sections.first() {
                output.push_str(&format_section_preview(&doc, first_section));
            } else {
                output.push_str("  [end of document]\n");
            }

            if dry_run {
                print!("{}", output);
                return Ok(());
            }

            // Splice at preamble_range.end
            let new_source = format!(
                "{}{}{}",
                &source[..preamble_range.end],
                splice_content,
                &source[preamble_range.end..]
            );
            let normalised = normalise(&new_source);
            std::fs::write(file, &normalised)
                .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

            print!("{}", output);
            return Ok(());
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd claude-code-only/mdedit && cargo test --test append -- --nocapture`
Expected: All tests PASS (existing 6 + new 5 = 11 total).

- [ ] **Step 5: Commit**

```bash
git add claude-code-only/mdedit/src/commands/append.rs claude-code-only/mdedit/tests/append.rs
git commit -m "feat(mdedit): implement _preamble support for append command"
```

---

### Task 4: Implement `_preamble` support in `prepend`

**Files:**
- Modify: `claude-code-only/mdedit/src/commands/prepend.rs:35-39` (replace the `Preamble` error arm)
- Modify: `claude-code-only/mdedit/tests/prepend.rs` (add preamble tests)

**Context:** Same pattern. Splice point is `preamble_range.start`. Output shows `+` prefixed new lines + head of existing preamble.

- [ ] **Step 1: Write failing tests for preamble prepend**

Add these tests at the end of `claude-code-only/mdedit/tests/prepend.rs`:

```rust
#[test]
fn prepend_to_preamble_existing() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "_preamble", "--content", "Prepended line."])
        .assert()
        .success()
        .stdout(predicate::str::contains("PREPENDED"))
        .stdout(predicate::str::contains("_preamble"))
        .stdout(predicate::str::contains("+ Prepended line."));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Prepended line."));
    assert!(result.contains("Existing preamble."));
    let prepended_pos = result.find("Prepended line.").unwrap();
    let existing_pos = result.find("Existing preamble.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(prepended_pos < existing_pos);
    assert!(existing_pos < heading_pos);
    drop(dir);
}

#[test]
fn prepend_to_preamble_creates_when_absent() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "_preamble", "--content", "New preamble."])
        .assert()
        .success()
        .stdout(predicate::str::contains("PREPENDED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New preamble."));
    let preamble_pos = result.find("New preamble.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(preamble_pos < heading_pos);
    drop(dir);
}

#[test]
fn prepend_to_preamble_dry_run() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "_preamble", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("New.")); // file unchanged
    drop(dir);
}

#[test]
fn prepend_to_preamble_no_frontmatter() {
    let (dir, file) = common::temp_md_file(
        "Existing preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "_preamble", "--content", "Prepended."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Prepended."));
    assert!(result.contains("Existing preamble."));
    let prepended_pos = result.find("Prepended.").unwrap();
    let existing_pos = result.find("Existing preamble.").unwrap();
    assert!(prepended_pos < existing_pos);
    drop(dir);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd claude-code-only/mdedit && cargo test --test prepend prepend_to_preamble -- --nocapture`
Expected: FAIL — all 4 tests fail with "prepend does not yet support _preamble" error.

- [ ] **Step 3: Implement preamble support in prepend.rs**

In `claude-code-only/mdedit/src/commands/prepend.rs`, replace the `Preamble` arm (lines 35-39) with:

```rust
        ResolvedSection::Preamble => {
            // Prepend to preamble content
            let preamble_range = doc.preamble_write_range();
            let existing_content = &source[preamble_range.clone()];

            // Resolve new content
            let prepend_content_raw = resolve_content(content, from_file)?;
            let prepend_content_with_newline = format!(
                "{}{}",
                prepend_content_raw,
                if prepend_content_raw.ends_with('\n') { "" } else { "\n" }
            );

            // Whitespace: prepend \n only when creating preamble after frontmatter
            let splice_content = if doc.frontmatter.is_some() && doc.preamble.is_none() {
                format!("\n{}", prepend_content_with_newline)
            } else {
                prepend_content_with_newline.clone()
            };

            // Metrics
            let existing_lines = existing_content.trim().lines().count();
            let prepended_lines = prepend_content_raw.lines().count();
            let combined = format!("{}{}", prepend_content_with_newline, existing_content);
            let combined_lines = combined.trim().lines().count();

            // Build output
            let action_label = if dry_run { "WOULD PREPEND" } else { "PREPENDED" };
            let mut output = String::new();
            if dry_run {
                output.push_str("DRY RUN \u{2014} no changes written\n\n");
            }
            output.push_str(&format!(
                "{}: {} lines to \"_preamble\" (was {} lines \u{2192} now {} lines)\n",
                action_label, prepended_lines, existing_lines, combined_lines
            ));

            output.push('\n');

            // Target with → marker
            output.push_str("\u{2192} _preamble\n");

            // Prepended lines with + prefix
            for line in prepend_content_raw.lines() {
                output.push_str(&format!("+ {}\n", line));
            }

            // Head of existing content (if any)
            let existing_text = existing_content.trim();
            let existing_non_empty: Vec<&str> = existing_text.lines()
                .filter(|l| !l.trim().is_empty()).collect();
            if let Some(first) = existing_non_empty.first() {
                output.push_str(&format!("  {}\n", first));
            }
            if existing_non_empty.len() > 1 {
                output.push_str(&format!("  [{} more lines]\n", existing_non_empty.len() - 1));
            }

            // Next section context
            output.push('\n');
            if let Some(first_section) = doc.sections.first() {
                output.push_str(&format_section_preview(&doc, first_section));
            } else {
                output.push_str("  [end of document]\n");
            }

            if dry_run {
                print!("{}", output);
                return Ok(());
            }

            // Splice at preamble_range.start
            let new_source = format!(
                "{}{}{}",
                &source[..preamble_range.start],
                splice_content,
                &source[preamble_range.start..]
            );
            let normalised = normalise(&new_source);
            std::fs::write(file, &normalised)
                .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

            print!("{}", output);
            return Ok(());
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd claude-code-only/mdedit && cargo test --test prepend -- --nocapture`
Expected: All tests PASS (existing 7 + new 4 = 11 total).

- [ ] **Step 5: Commit**

```bash
git add claude-code-only/mdedit/src/commands/prepend.rs claude-code-only/mdedit/tests/prepend.rs
git commit -m "feat(mdedit): implement _preamble support for prepend command"
```

---

### Task 5: Implement frontmatter bare invocation

**Files:**
- Modify: `claude-code-only/mdedit/src/main.rs:56-59` (Frontmatter variant) and `175-188` (dispatch logic)
- Modify: `claude-code-only/mdedit/tests/frontmatter.rs` (add bare invocation test)

- [ ] **Step 1: Write failing test for bare invocation**

Add this test at the end of `claude-code-only/mdedit/tests/frontmatter.rs`:

```rust
#[test]
fn frontmatter_bare_invocation() {
    // mdedit frontmatter doc.md should behave like mdedit frontmatter show doc.md
    let show_output = Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "show", &common::fixture_path_str("with_frontmatter.md")])
        .output()
        .unwrap();

    let bare_output = Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", &common::fixture_path_str("with_frontmatter.md")])
        .output()
        .unwrap();

    assert!(bare_output.status.success());
    assert_eq!(
        String::from_utf8_lossy(&show_output.stdout),
        String::from_utf8_lossy(&bare_output.stdout)
    );
}

#[test]
fn frontmatter_bare_no_file_errors() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter"])
        .assert()
        .failure();
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd claude-code-only/mdedit && cargo test --test frontmatter frontmatter_bare -- --nocapture`
Expected: FAIL — `frontmatter_bare_invocation` fails because bare form is not recognized.

- [ ] **Step 3: Modify the Frontmatter clap definition in main.rs**

In `claude-code-only/mdedit/src/main.rs`, replace the `Frontmatter` variant (lines 56-59):

```rust
    /// Read/write YAML frontmatter
    Frontmatter {
        #[command(subcommand)]
        action: FrontmatterAction,
    },
```

with:

```rust
    /// Read/write YAML frontmatter
    Frontmatter {
        /// File path (used when no subcommand given, defaults to show)
        file: Option<String>,
        #[command(subcommand)]
        action: Option<FrontmatterAction>,
    },
```

Then replace the dispatch logic (lines 175-188):

```rust
        Commands::Frontmatter { action } => match action {
            FrontmatterAction::Show { file } => {
                commands::frontmatter::run_show(&file)
            }
            FrontmatterAction::Get { file, key } => {
                commands::frontmatter::run_get(&file, &key)
            }
            FrontmatterAction::Set { file, key, value, dry_run } => {
                commands::frontmatter::run_set(&file, &key, &value, dry_run)
            }
            FrontmatterAction::Delete { file, key, dry_run } => {
                commands::frontmatter::run_delete(&file, &key, dry_run)
            }
        },
```

with:

```rust
        Commands::Frontmatter { file, action } => match action {
            Some(FrontmatterAction::Show { file }) => {
                commands::frontmatter::run_show(&file)
            }
            Some(FrontmatterAction::Get { file, key }) => {
                commands::frontmatter::run_get(&file, &key)
            }
            Some(FrontmatterAction::Set { file, key, value, dry_run }) => {
                commands::frontmatter::run_set(&file, &key, &value, dry_run)
            }
            Some(FrontmatterAction::Delete { file, key, dry_run }) => {
                commands::frontmatter::run_delete(&file, &key, dry_run)
            }
            None => {
                let file = file.ok_or_else(|| error::MdeditError::InvalidOperation(
                    "file required: mdedit frontmatter <file>".to_string()
                ))?;
                commands::frontmatter::run_show(&file)
            }
        },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd claude-code-only/mdedit && cargo test --test frontmatter -- --nocapture`
Expected: All tests PASS (existing 7 + new 2 = 9 total).

- [ ] **Step 5: Commit**

```bash
git add claude-code-only/mdedit/src/main.rs claude-code-only/mdedit/tests/frontmatter.rs
git commit -m "feat(mdedit): support bare frontmatter invocation without show subcommand"
```

---

### Task 6: Full test suite verification

**Files:** None (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `cd claude-code-only/mdedit && cargo test 2>&1`
Expected: All tests pass. No regressions. The total count should be approximately 120+ (existing 105 + ~15 new).

- [ ] **Step 2: Verify release build compiles**

Run: `cd claude-code-only/mdedit && cargo build --release 2>&1`
Expected: Clean compile with no warnings.

- [ ] **Step 3: Manual smoke test of preamble operations**

Create a temp file and run each command:

```bash
cd claude-code-only/mdedit
MDEDIT=./target/release/mdedit
echo -e "---\ntitle: Test\n---\n\n# Heading\n\nContent.\n" > /tmp/test-preamble.md

# Create preamble via prepend
$MDEDIT prepend /tmp/test-preamble.md "_preamble" --content "Created via prepend."
cat /tmp/test-preamble.md

# Append to it
$MDEDIT append /tmp/test-preamble.md "_preamble" --content "Appended line."
cat /tmp/test-preamble.md

# Replace it
$MDEDIT replace /tmp/test-preamble.md "_preamble" --content "Replaced entirely."
cat /tmp/test-preamble.md

# Bare frontmatter
echo -e "---\ntitle: Test\n---\n\n# H\n" > /tmp/test-fm.md
$MDEDIT frontmatter /tmp/test-fm.md
```

Expected: Each command produces correct output and the file content is as expected. Bare frontmatter shows the same output as `frontmatter show`.

- [ ] **Step 4: Commit (if any fixes were needed)**

Only if manual testing revealed issues that required code changes.
