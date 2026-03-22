# mdedit v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a compiled Rust CLI tool (`mdedit`) for structured markdown editing via heading-based section addressing, designed for LLM workflows with token-efficient I/O.

**Architecture:** Source surgery on the original byte string — parse with tree-sitter-md to get byte ranges for sections, then splice content directly. Untouched regions are preserved byte-for-byte. No serialization round-trips.

**Tech Stack:** Rust (2021 edition), tree-sitter 0.26 + tree-sitter-md 0.5 (block grammar only), clap 4 (derive), strsim 0.11 (fuzzy matching), serde_yaml 0.9 + serde_json 1 (frontmatter), assert_cmd 2 + predicates 3 + tempfile 3 (testing)

**Spec:** `docs/plans/2026-03-22-mdedit-v1-spec.md` — all command behaviors, output formats, error messages, and exit codes are defined there. Reference it throughout implementation.

---

## File Structure

```
claude-code-only/mdedit/
├── Cargo.toml
├── src/
│   ├── main.rs                # CLI entry point (clap), subcommand dispatch, mod declarations
│   ├── error.rs               # MdeditError enum, exit codes, error formatting
│   ├── document.rs            # Document and Section structs (the data model)
│   ├── parser.rs              # tree-sitter-md parsing → Document model
│   ├── addressing.rs          # Section name resolution, fuzzy matching
│   ├── content.rs             # Content input resolution (--content, --from-file, stdin)
│   ├── counting.rs            # Word/line counting per spec rules
│   ├── output.rs              # Neighborhood formatter, TTY detection, write output
│   ├── whitespace.rs          # Whitespace normalisation after writes
│   └── commands/
│       ├── mod.rs             # Re-exports all command modules
│       ├── outline.rs         # outline command
│       ├── extract.rs         # extract command
│       ├── search.rs          # search command
│       ├── stats.rs           # stats command
│       ├── validate.rs        # validate command
│       ├── frontmatter.rs     # frontmatter, frontmatter get/set/delete
│       ├── replace.rs         # replace command
│       ├── append.rs          # append command
│       ├── prepend.rs         # prepend command
│       ├── insert.rs          # insert command
│       ├── delete.rs          # delete command
│       └── rename.rs          # rename command
└── tests/
    ├── common/
    │   └── mod.rs             # Shared test helpers (fixture paths, temp file creation)
    ├── outline.rs             # Integration tests for outline
    ├── extract.rs             # Integration tests for extract
    ├── search.rs              # Integration tests for search
    ├── stats.rs               # Integration tests for stats
    ├── validate.rs            # Integration tests for validate
    ├── frontmatter.rs         # Integration tests for frontmatter
    ├── replace.rs             # Integration tests for replace
    ├── append.rs              # Integration tests for append
    ├── prepend.rs             # Integration tests for prepend
    ├── insert.rs              # Integration tests for insert
    ├── delete_cmd.rs          # Integration tests for delete (delete.rs conflicts with Rust keyword)
    ├── rename.rs              # Integration tests for rename
    └── fixtures/
        ├── simple.md
        ├── nested.md
        ├── with_frontmatter.md
        ├── with_preamble.md
        ├── empty_sections.md
        ├── duplicate_headings.md
        ├── code_fences.md
        └── no_headings.md
```

**Key design decisions:**
- Each command is its own file — commands are independent and shouldn't grow beyond ~200 lines each
- `document.rs` is separate from `parser.rs` — the data model is pure Rust structs; the parser is the tree-sitter integration that populates them. This means tests can construct Documents without parsing if needed.
- Integration tests are one file per command — mirrors the command structure, tests are independent
- `error.rs` handles all error formatting and exit code mapping — commands return `Result<(), MdeditError>`, main handles display

---

## Test Fixtures

These files are created in Task 1 and used by all subsequent tasks. Each fixture is designed to exercise specific edge cases.

### `simple.md` — Basic H1/H2 structure, no nesting

```markdown
# My Document

## Introduction

This is the introduction section.
It has two lines of content.

## Background

The system operates under three constraints.
Each constraint governs a different aspect.
Together they form the core model.

## Conclusion

In summary, the approach works.
```

### `nested.md` — H1/H2/H3 hierarchy with multiple branches

```markdown
# Research Paper

## Introduction

Opening text for the paper.

## Background

Background overview paragraph.

### Prior Work

Previous approaches include X and Y.
They had significant limitations.

### Definitions

Term A means something specific.
Term B means something else entirely.

## Methods

We use a novel approach here.

### Experimental Setup

The setup consists of three parts.

### Metrics

We measure accuracy and speed.

## Results

The results are promising overall.

## Conclusion

We conclude that it works well.
```

### `with_frontmatter.md` — YAML frontmatter + content

```markdown
---
title: "My Document"
tags: ["rust", "cli"]
date: "2026-03-17"
draft: true
---

# Document Title

Some content here.

## Section One

First section content.
```

### `with_preamble.md` — Frontmatter + preamble text + headings

```markdown
---
title: "My Document"
---

This is preamble text before any heading.
It can span multiple lines.

# First Heading

Content under first heading.

## Sub Section

Sub section content.
```

### `empty_sections.md` — Sections with no content between headings

```markdown
# Document

## Filled Section

This section has content.

## Empty Section

## Another Filled Section

This section also has content.

## Also Empty

### Empty Child

## Final Section

Last section content.
```

### `duplicate_headings.md` — Same heading text at different levels/locations

```markdown
# Document

## Notes

These are general notes.

## Background

Background content here.

### Notes

These are background-specific notes.

## Conclusion

Final thoughts.
```

### `code_fences.md` — Headings inside code fences must be ignored

````markdown
# Real Heading

Some content before code.

```markdown
# This is not a heading
## Neither is this
```

## Another Real Heading

More content here.

```python
# This is a Python comment, not a heading
def hello():
    pass
```

## Final Real Heading

End content.
````

### `no_headings.md` — Plain text, no headings at all

```markdown
This document has no headings.
It is just plain text content.
Multiple lines of it.
```

---

## Task 1: Project Scaffolding + Error Types + Test Fixtures

**Files:**
- Create: `claude-code-only/mdedit/Cargo.toml`
- Create: `claude-code-only/mdedit/src/main.rs`
- Create: `claude-code-only/mdedit/src/error.rs`
- Create: `claude-code-only/mdedit/src/document.rs` (structs only, no logic)
- Create: all `tests/fixtures/*.md` files
- Create: `claude-code-only/mdedit/tests/common/mod.rs`

- [ ] **Step 1: Create directory structure**

Run: `mkdir -p claude-code-only/mdedit/src/commands && mkdir -p claude-code-only/mdedit/tests/{fixtures,common}`

- [ ] **Step 2: Write Cargo.toml**

```toml
[package]
name = "mdedit"
version = "0.1.0"
edition = "2021"
description = "Structured markdown editing for LLM workflows"

[dependencies]
clap = { version = "4", features = ["derive"] }
tree-sitter = "0.26"
tree-sitter-md = "0.5"
serde = { version = "1", features = ["derive"] }
serde_yaml = "0.9"
serde_json = "1"
strsim = "0.11"

[dev-dependencies]
assert_cmd = "2"
predicates = "3"
tempfile = "3"
```

- [ ] **Step 3: Write src/error.rs**

```rust
use std::fmt;
use std::process;

/// Exit codes per spec
#[derive(Debug, Clone, Copy)]
pub enum ExitCode {
    Success = 0,
    SectionNotFound = 1,
    AmbiguousMatch = 2,
    FileError = 3,
    ContentError = 4,
    ValidationFailure = 5,
    NoOp = 10,
}

/// A matched section for error messages
#[derive(Debug, Clone)]
pub struct SectionRef {
    pub heading: String,  // e.g. "## Background"
    pub level: u8,
    pub line: usize,      // 1-indexed
    pub parent: Option<String>,
}

impl fmt::Display for SectionRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{} (H{}, line {})", self.heading, self.level, self.line)?;
        if let Some(parent) = &self.parent {
            write!(f, ", under \"{}\"", parent)?;
        }
        Ok(())
    }
}

#[derive(Debug)]
pub enum MdeditError {
    SectionNotFound {
        query: String,
        file: String,
        suggestions: Vec<SectionRef>,
    },
    AmbiguousMatch {
        query: String,
        file: String,
        matches: Vec<SectionRef>,
    },
    FileError(String),
    ContentError(String),
    ValidationFailures(Vec<ValidationIssue>),
    NoOp(String),
    InvalidOperation(String),
}

#[derive(Debug, Clone)]
pub enum Severity {
    Warning,
    Info,
}

#[derive(Debug, Clone)]
pub struct ValidationIssue {
    pub severity: Severity,
    pub line: usize,
    pub message: String,
}

impl MdeditError {
    pub fn exit_code(&self) -> i32 {
        match self {
            MdeditError::SectionNotFound { .. } => ExitCode::SectionNotFound as i32,
            MdeditError::AmbiguousMatch { .. } => ExitCode::AmbiguousMatch as i32,
            MdeditError::FileError(_) => ExitCode::FileError as i32,
            MdeditError::ContentError(_) => ExitCode::ContentError as i32,
            MdeditError::ValidationFailures(_) => ExitCode::ValidationFailure as i32,
            MdeditError::NoOp(_) => ExitCode::NoOp as i32,
            MdeditError::InvalidOperation(_) => ExitCode::ContentError as i32,
        }
    }
}

impl fmt::Display for MdeditError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            MdeditError::SectionNotFound { query, file, suggestions } => {
                writeln!(f, "ERROR: Section \"{}\" not found in {}", query, file)?;
                if !suggestions.is_empty() {
                    writeln!(f, "Did you mean?")?;
                    for s in suggestions {
                        writeln!(f, "  → {}", s)?;
                    }
                }
                Ok(())
            }
            MdeditError::AmbiguousMatch { query, file, matches } => {
                writeln!(f, "ERROR: \"{}\" matches {} sections in {}",
                    query, matches.len(), file)?;
                for m in matches {
                    writeln!(f, "  → {}", m)?;
                }
                writeln!(f, "Disambiguate with level prefix or path syntax")
            }
            MdeditError::FileError(msg) => write!(f, "ERROR: {}", msg),
            MdeditError::ContentError(msg) => write!(f, "ERROR: {}", msg),
            MdeditError::ValidationFailures(issues) => {
                let warning_count = issues.iter()
                    .filter(|i| matches!(i.severity, Severity::Warning))
                    .count();
                let total = issues.len();
                writeln!(f, "INVALID: {} issues", total)?;
                for issue in issues {
                    let marker = match issue.severity {
                        Severity::Warning => "⚠",
                        Severity::Info => "ℹ",
                    };
                    writeln!(f, "  {} Line {}: {}", marker, issue.line, issue.message)?;
                }
                Ok(())
            }
            MdeditError::NoOp(msg) => write!(f, "NO CHANGE: {}", msg),
            MdeditError::InvalidOperation(msg) => write!(f, "ERROR: {}", msg),
        }
    }
}
```

- [ ] **Step 4: Write src/document.rs (data model only)**

```rust
use std::ops::Range;

/// A parsed markdown document
#[derive(Debug, Clone)]
pub struct Document {
    /// Original source text (owned)
    pub source: String,
    /// Byte range of YAML frontmatter (including --- delimiters), if present
    pub frontmatter: Option<Range<usize>>,
    /// Byte range of content between frontmatter and first heading, if present
    pub preamble: Option<Range<usize>>,
    /// Top-level sections (nested hierarchy)
    pub sections: Vec<Section>,
}

/// A section: heading + content + child sections
#[derive(Debug, Clone)]
pub struct Section {
    /// Heading text without # prefix, trimmed (e.g. "Background")
    pub heading_text: String,
    /// Heading level (1-6)
    pub level: u8,
    /// Byte range of the heading line only
    pub heading_range: Range<usize>,
    /// Byte range of own content (after heading, before first child section)
    pub own_content_range: Range<usize>,
    /// Byte range of entire section (heading + own content + all children)
    pub full_range: Range<usize>,
    /// 1-indexed line number of heading
    pub line_start: usize,
    /// 1-indexed line number of last line in section
    pub line_end: usize,
    /// Nested child sections
    pub children: Vec<Section>,
}

impl Document {
    /// Get the source text for a byte range
    pub fn slice(&self, range: &Range<usize>) -> &str {
        &self.source[range.start..range.end]
    }

    /// All sections flattened (recursive depth-first), with parent info
    pub fn all_sections(&self) -> Vec<(&Section, Option<&Section>)> {
        let mut result = Vec::new();
        for section in &self.sections {
            Self::collect_sections(section, None, &mut result);
        }
        result
    }

    fn collect_sections<'a>(
        section: &'a Section,
        parent: Option<&'a Section>,
        result: &mut Vec<(&'a Section, Option<&'a Section>)>,
    ) {
        result.push((section, parent));
        for child in &section.children {
            Self::collect_sections(child, Some(section), result);
        }
    }

    /// Compute 1-indexed line number from byte offset
    pub fn byte_to_line(&self, byte: usize) -> usize {
        self.source[..byte].matches('\n').count() + 1
    }
}

impl Section {
    /// Full heading with # prefix (e.g. "## Background")
    pub fn full_heading(&self) -> String {
        format!("{} {}", "#".repeat(self.level as usize), self.heading_text)
    }

    /// Total number of lines in this section
    pub fn line_count(&self) -> usize {
        if self.line_end >= self.line_start {
            self.line_end - self.line_start + 1
        } else {
            0
        }
    }

    /// All descendant sections (recursive)
    pub fn all_descendants(&self) -> Vec<&Section> {
        let mut result = Vec::new();
        for child in &self.children {
            result.push(child);
            result.extend(child.all_descendants());
        }
        result
    }
}
```

- [ ] **Step 5: Write src/main.rs with clap skeleton**

```rust
use clap::{Parser, Subcommand};
use std::process;

mod error;
mod document;
mod parser;
mod addressing;
mod content;
mod counting;
mod output;
mod whitespace;
mod commands;

#[derive(Parser)]
#[command(name = "mdedit")]
#[command(about = "Structured markdown editing for LLM workflows")]
#[command(version)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Section hierarchy with word counts
    Outline {
        file: String,
        #[arg(long)]
        max_depth: Option<u8>,
    },
    /// Pull section content (raw or to file)
    Extract {
        file: String,
        section: String,
        #[arg(long)]
        no_children: bool,
        #[arg(long)]
        to_file: Option<String>,
    },
    /// Find sections containing text
    Search {
        file: String,
        query: String,
        #[arg(long)]
        case_sensitive: bool,
    },
    /// Word/line counts per section
    Stats {
        file: String,
    },
    /// Check heading structure
    Validate {
        file: String,
    },
    /// Read/write YAML frontmatter
    Frontmatter {
        /// File to operate on
        file: String,
        /// Subcommand: get, set, or delete (omit to show all fields)
        #[command(subcommand)]
        action: Option<FrontmatterAction>,
    },
    /// Substitute section content
    Replace {
        file: String,
        section: String,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        from_file: Option<String>,
        #[arg(long)]
        preserve_children: bool,
        #[arg(long)]
        dry_run: bool,
    },
    /// Add content to end of section
    Append {
        file: String,
        section: String,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        from_file: Option<String>,
        #[arg(long)]
        dry_run: bool,
    },
    /// Add content to start of section
    Prepend {
        file: String,
        section: String,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        from_file: Option<String>,
        #[arg(long)]
        dry_run: bool,
    },
    /// Add new section at position
    Insert {
        file: String,
        #[arg(long, required_unless_present = "before", conflicts_with = "before")]
        after: Option<String>,
        #[arg(long, required_unless_present = "after", conflicts_with = "after")]
        before: Option<String>,
        #[arg(long)]
        heading: String,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        from_file: Option<String>,
        #[arg(long)]
        dry_run: bool,
    },
    /// Remove section and content
    Delete {
        file: String,
        section: String,
        #[arg(long)]
        dry_run: bool,
    },
    /// Change heading text
    Rename {
        file: String,
        section: String,
        new_name: String,
        #[arg(long)]
        dry_run: bool,
    },
}

#[derive(Subcommand)]
enum FrontmatterAction {
    /// Get a frontmatter field value
    Get {
        key: String,
    },
    /// Set a frontmatter field value
    Set {
        key: String,
        value: String,
        #[arg(long)]
        dry_run: bool,
    },
    /// Delete a frontmatter field
    Delete {
        key: String,
        #[arg(long)]
        dry_run: bool,
    },
}

fn main() {
    let cli = Cli::parse();

    let result = match cli.command {
        // Commands will be dispatched here as they are implemented.
        // For now, each prints "not yet implemented" and exits.
        _ => {
            eprintln!("Command not yet implemented");
            process::exit(1);
        }
    };
}
```

**Note:** The `Frontmatter` variant needs careful clap modelling. The spec supports both `mdedit frontmatter <file>` (show all) and `mdedit frontmatter get/set/delete <file> <key>`. The clap structure above may need adjustment during implementation — the important thing is that all argument combinations from the spec are parseable. Test with `cargo run -- --help` and `cargo run -- frontmatter --help`.

- [ ] **Step 7: Write src/commands/mod.rs (empty re-exports)**

```rust
pub mod outline;
pub mod extract;
pub mod search;
pub mod stats;
pub mod validate;
pub mod frontmatter;
pub mod replace;
pub mod append;
pub mod prepend;
pub mod insert;
pub mod delete;
pub mod rename;
```

Create each command file as an empty module for now (just `// TODO`).

- [ ] **Step 8: Create stub files for remaining src modules**

Create empty files: `src/parser.rs`, `src/addressing.rs`, `src/content.rs`, `src/counting.rs`, `src/output.rs`, `src/whitespace.rs` — each with just a comment placeholder.

- [ ] **Step 9: Write all test fixture files**

Write each fixture file from the Test Fixtures section above to `tests/fixtures/`.

- [ ] **Step 10: Write tests/common/mod.rs**

```rust
use std::path::PathBuf;

pub fn fixture_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join(name)
}

pub fn fixture_path_str(name: &str) -> String {
    fixture_path(name).to_string_lossy().to_string()
}

/// Create a temp directory with a markdown file, returning (dir, file_path)
pub fn temp_md_file(content: &str) -> (tempfile::TempDir, PathBuf) {
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("test.md");
    std::fs::write(&file, content).unwrap();
    (dir, file)
}
```

- [ ] **Step 11: Verify build**

Run: `cd claude-code-only/mdedit && cargo build`
Expected: Compiles successfully (downloads dependencies on first run, may take 1-2 minutes)

- [ ] **Step 12: Commit**

```bash
cd claude-code-only/mdedit
git add -A
git commit -m "feat(mdedit): project scaffolding with clap CLI, error types, and test fixtures"
```

---

## Task 2: Parser + Document Model

**Files:**
- Modify: `src/parser.rs` — tree-sitter-md parsing logic
- Modify: `src/document.rs` — may need minor adjustments based on tree-sitter CST structure

- [ ] **Step 1: Write unit tests for parser**

Add to `src/parser.rs`:

```rust
use crate::document::{Document, Section};

/// Parse a markdown string into a Document
pub fn parse(source: &str) -> Result<Document, String> {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_simple_document() {
        let source = std::fs::read_to_string("tests/fixtures/simple.md").unwrap();
        let doc = parse(&source).unwrap();

        // No frontmatter, no preamble
        assert!(doc.frontmatter.is_none());
        assert!(doc.preamble.is_none());

        // H1 is the document title — it wraps everything in one top-level section
        assert_eq!(doc.sections.len(), 1);
        let root = &doc.sections[0];
        assert_eq!(root.heading_text, "My Document");
        assert_eq!(root.level, 1);

        // Three H2 children
        assert_eq!(root.children.len(), 3);
        assert_eq!(root.children[0].heading_text, "Introduction");
        assert_eq!(root.children[0].level, 2);
        assert_eq!(root.children[1].heading_text, "Background");
        assert_eq!(root.children[2].heading_text, "Conclusion");

        // No grandchildren in simple.md
        assert!(root.children[0].children.is_empty());
    }

    #[test]
    fn parse_nested_document() {
        let source = std::fs::read_to_string("tests/fixtures/nested.md").unwrap();
        let doc = parse(&source).unwrap();

        let root = &doc.sections[0];
        assert_eq!(root.heading_text, "Research Paper");

        // H2 sections: Introduction, Background, Methods, Results, Conclusion
        assert_eq!(root.children.len(), 5);

        // Background has 2 H3 children
        let bg = &root.children[1];
        assert_eq!(bg.heading_text, "Background");
        assert_eq!(bg.children.len(), 2);
        assert_eq!(bg.children[0].heading_text, "Prior Work");
        assert_eq!(bg.children[1].heading_text, "Definitions");

        // Methods has 2 H3 children
        let methods = &root.children[2];
        assert_eq!(methods.children.len(), 2);
    }

    #[test]
    fn parse_frontmatter() {
        let source = std::fs::read_to_string("tests/fixtures/with_frontmatter.md").unwrap();
        let doc = parse(&source).unwrap();

        assert!(doc.frontmatter.is_some());
        let fm_range = doc.frontmatter.as_ref().unwrap();
        let fm_text = &source[fm_range.start..fm_range.end];
        assert!(fm_text.contains("title:"));
        assert!(fm_text.contains("tags:"));
    }

    #[test]
    fn parse_preamble() {
        let source = std::fs::read_to_string("tests/fixtures/with_preamble.md").unwrap();
        let doc = parse(&source).unwrap();

        assert!(doc.frontmatter.is_some());
        assert!(doc.preamble.is_some());
        let pre_text = doc.slice(doc.preamble.as_ref().unwrap());
        assert!(pre_text.contains("preamble text"));
    }

    #[test]
    fn parse_code_fences_ignores_fake_headings() {
        let source = std::fs::read_to_string("tests/fixtures/code_fences.md").unwrap();
        let doc = parse(&source).unwrap();

        // Should only find 3 real headings, not the ones inside code fences
        let all = doc.all_sections();
        let heading_texts: Vec<&str> = all.iter().map(|(s, _)| s.heading_text.as_str()).collect();
        assert!(heading_texts.contains(&"Real Heading"));
        assert!(heading_texts.contains(&"Another Real Heading"));
        assert!(heading_texts.contains(&"Final Real Heading"));
        // "This is not a heading" should NOT be found
        assert!(!heading_texts.contains(&"This is not a heading"));
    }

    #[test]
    fn parse_no_headings() {
        let source = std::fs::read_to_string("tests/fixtures/no_headings.md").unwrap();
        let doc = parse(&source).unwrap();

        assert!(doc.sections.is_empty());
        // Entire content is preamble
        assert!(doc.preamble.is_some());
    }

    #[test]
    fn parse_byte_ranges_are_correct() {
        let source = "# Title\n\nContent line.\n\n## Section\n\nSection content.\n";
        let doc = parse(source).unwrap();

        let root = &doc.sections[0];
        // Heading range should cover "# Title\n"
        assert_eq!(&source[root.heading_range.clone()], "# Title\n");
        // Full range should cover entire document
        assert_eq!(root.full_range.start, 0);
        assert_eq!(root.full_range.end, source.len());
    }

    #[test]
    fn parse_line_numbers_are_one_indexed() {
        let source = "# Title\n\n## Second\n\nContent.\n";
        let doc = parse(source).unwrap();

        let root = &doc.sections[0];
        assert_eq!(root.line_start, 1); // "# Title" is line 1
        let second = &root.children[0];
        assert_eq!(second.line_start, 3); // "## Second" is line 3
    }
}
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd claude-code-only/mdedit && cargo test parser::tests -- --nocapture 2>&1 | head -30`
Expected: Compilation error or `todo!()` panic

- [ ] **Step 3: Implement the parser**

Implement `parse()` in `src/parser.rs`. Key logic:

1. Create a tree-sitter `Parser`, set language to `tree_sitter_md::LANGUAGE`
2. Parse the source bytes
3. Walk the root node's children:
   - `minus_metadata` → record frontmatter byte range
   - `paragraph`, `blank_line`, etc. (before first `section`) → record as preamble
   - `section` → recursively build `Section` structs
4. For each `section` node:
   - First child is `atx_heading` — extract heading text and level from marker type
   - Remaining children: `paragraph`, `blank_line`, `fenced_code_block`, etc. are content
   - `section` children are nested child sections
   - `heading_range`: the `atx_heading` node's byte range
   - `own_content_range`: from `atx_heading.end_byte()` to first child `section.start_byte()` (or `section.end_byte()` if no children)
   - `full_range`: the `section` node's byte range
   - Line numbers: `node.start_position().row + 1` (tree-sitter rows are 0-indexed)

```rust
use tree_sitter::{Parser, Node};
use crate::document::{Document, Section};

pub fn parse(source: &str) -> Result<Document, String> {
    let mut parser = Parser::new();
    let language: tree_sitter::Language = tree_sitter_md::LANGUAGE.into();
    parser.set_language(&language)
        .map_err(|e| format!("Failed to set language: {}", e))?;

    let tree = parser.parse(source.as_bytes(), None)
        .ok_or_else(|| "Failed to parse markdown".to_string())?;

    let root = tree.root_node();
    let mut frontmatter: Option<std::ops::Range<usize>> = None;
    let mut preamble_start: Option<usize> = None;
    let mut preamble_end: Option<usize> = None;
    let mut sections = Vec::new();
    let mut found_section = false;

    let mut cursor = root.walk();
    for child in root.children(&mut cursor) {
        match child.kind() {
            "minus_metadata" => {
                frontmatter = Some(child.start_byte()..child.end_byte());
            }
            "section" => {
                found_section = true;
                sections.push(build_section(child, source));
            }
            _ if !found_section => {
                // Content before first section = preamble
                if child.kind() != "minus_metadata" {
                    if preamble_start.is_none() {
                        preamble_start = Some(child.start_byte());
                    }
                    preamble_end = Some(child.end_byte());
                }
            }
            _ => {}
        }
    }

    let preamble = match (preamble_start, preamble_end) {
        (Some(start), Some(end)) => Some(start..end),
        _ => None,
    };

    Ok(Document {
        source: source.to_string(),
        frontmatter,
        preamble,
        sections,
    })
}

fn build_section(node: Node, source: &str) -> Section {
    let mut heading_text = String::new();
    let mut level: u8 = 0;
    let mut heading_range = 0..0;
    let mut children = Vec::new();
    let mut first_child_section_start: Option<usize> = None;

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        match child.kind() {
            "atx_heading" => {
                heading_range = child.start_byte()..child.end_byte();
                level = extract_heading_level(child);
                heading_text = extract_heading_text(child, source);
            }
            "section" => {
                if first_child_section_start.is_none() {
                    first_child_section_start = Some(child.start_byte());
                }
                children.push(build_section(child, source));
            }
            _ => {}
        }
    }

    let own_content_end = first_child_section_start.unwrap_or(node.end_byte());

    Section {
        heading_text,
        level,
        heading_range: heading_range.clone(),
        own_content_range: heading_range.end..own_content_end,
        full_range: node.start_byte()..node.end_byte(),
        line_start: node.start_position().row + 1,
        line_end: if node.end_byte() > 0 && source.as_bytes().get(node.end_byte() - 1) == Some(&b'\n') {
            node.end_position().row // end_position is exclusive; if last char is \n, row is next line
        } else {
            node.end_position().row + 1
        },
        children,
    }
}

fn extract_heading_level(heading: Node) -> u8 {
    let mut cursor = heading.walk();
    for child in heading.children(&mut cursor) {
        match child.kind() {
            "atx_h1_marker" => return 1,
            "atx_h2_marker" => return 2,
            "atx_h3_marker" => return 3,
            "atx_h4_marker" => return 4,
            "atx_h5_marker" => return 5,
            "atx_h6_marker" => return 6,
            _ => continue,
        }
    }
    1 // fallback
}

fn extract_heading_text(heading: Node, source: &str) -> String {
    // heading_content is a field on atx_heading
    let mut cursor = heading.walk();
    for child in heading.children(&mut cursor) {
        // The heading content is typically an "inline" node
        if child.kind() == "inline" || cursor.field_name() == Some("heading_content") {
            return child.utf8_text(source.as_bytes())
                .unwrap_or("")
                .trim()
                .to_string();
        }
    }
    String::new()
}
```

**Important:** The exact node kinds and field names above are based on tree-sitter-md research. Verify by printing the CST during development: add a `debug_print_tree(root, source, 0)` helper that prints `node.kind()` at each depth. Adjust the code if node kinds differ from expectations.

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd claude-code-only/mdedit && cargo test parser::tests -- --nocapture`
Expected: All parser tests pass

- [ ] **Step 5: Fix any line_end calculation issues**

The `line_end` computation is tricky because tree-sitter's `end_position()` is exclusive (points to the byte after the node). Test with the `parse_line_numbers_are_one_indexed` test and adjust. You may need:

```rust
// Simpler approach: count newlines in the section's byte range
line_end: source[..node.end_byte()].matches('\n').count(),
// This gives the last line number (1-indexed) that the section occupies
```

Verify line numbers match the fixture files manually.

- [ ] **Step 6: Commit**

```bash
git add src/parser.rs src/document.rs
git commit -m "feat(mdedit): tree-sitter-md parser builds Document model from markdown"
```

---

## Task 3: Section Addressing + Fuzzy Matching

**Files:**
- Modify: `src/addressing.rs`

- [ ] **Step 1: Write unit tests for addressing**

```rust
use crate::document::{Document, Section};
use crate::parser;
use crate::error::MdeditError;

/// Result of resolving a section address
pub enum ResolvedSection<'a> {
    Found(&'a Section),
    Preamble,
}

/// Resolve a section query against a document
pub fn resolve<'a>(doc: &'a Document, query: &str) -> Result<ResolvedSection<'a>, MdeditError> {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse_fixture(name: &str) -> Document {
        let source = std::fs::read_to_string(format!("tests/fixtures/{}", name)).unwrap();
        parser::parse(&source).unwrap()
    }

    #[test]
    fn resolve_by_name() {
        let doc = parse_fixture("simple.md");
        let result = resolve(&doc, "Introduction").unwrap();
        match result {
            ResolvedSection::Found(s) => assert_eq!(s.heading_text, "Introduction"),
            _ => panic!("expected Found"),
        }
    }

    #[test]
    fn resolve_by_level_prefix() {
        let doc = parse_fixture("duplicate_headings.md");
        // "Notes" is ambiguous, but "## Notes" matches only the H2
        let result = resolve(&doc, "## Notes").unwrap();
        match result {
            ResolvedSection::Found(s) => {
                assert_eq!(s.heading_text, "Notes");
                assert_eq!(s.level, 2);
            }
            _ => panic!("expected Found"),
        }
    }

    #[test]
    fn resolve_by_path() {
        let doc = parse_fixture("duplicate_headings.md");
        let result = resolve(&doc, "Background/Notes").unwrap();
        match result {
            ResolvedSection::Found(s) => {
                assert_eq!(s.heading_text, "Notes");
                assert_eq!(s.level, 3); // It's a child of Background
            }
            _ => panic!("expected Found"),
        }
    }

    #[test]
    fn resolve_preamble() {
        let doc = parse_fixture("with_preamble.md");
        let result = resolve(&doc, "_preamble").unwrap();
        assert!(matches!(result, ResolvedSection::Preamble));
    }

    #[test]
    fn resolve_ambiguous_returns_error() {
        let doc = parse_fixture("duplicate_headings.md");
        let result = resolve(&doc, "Notes");
        assert!(result.is_err());
        match result.unwrap_err() {
            MdeditError::AmbiguousMatch { matches, .. } => {
                assert_eq!(matches.len(), 2);
            }
            e => panic!("expected AmbiguousMatch, got {:?}", e),
        }
    }

    #[test]
    fn resolve_not_found_has_fuzzy_suggestions() {
        let doc = parse_fixture("simple.md");
        let result = resolve(&doc, "Introductoin"); // typo
        assert!(result.is_err());
        match result.unwrap_err() {
            MdeditError::SectionNotFound { suggestions, .. } => {
                assert!(!suggestions.is_empty());
                // Should suggest "Introduction"
                assert!(suggestions.iter().any(|s| s.heading.contains("Introduction")));
            }
            e => panic!("expected SectionNotFound, got {:?}", e),
        }
    }

    #[test]
    fn resolve_preamble_when_none_exists() {
        let doc = parse_fixture("simple.md");
        let result = resolve(&doc, "_preamble");
        // simple.md has no preamble — _preamble should still resolve,
        // but operations on it will find no content
        assert!(matches!(result.unwrap(), ResolvedSection::Preamble));
    }
}
```

- [ ] **Step 2: Run tests, verify failure**

Run: `cd claude-code-only/mdedit && cargo test addressing::tests`
Expected: FAIL

- [ ] **Step 3: Implement addressing**

Key logic:
1. Check for `_preamble` → return `ResolvedSection::Preamble`
2. Parse the query:
   - If starts with `#` → extract level and text (e.g. `"## Background"` → level 2, text "Background")
   - If contains `/` → split into path components (e.g. `"Background/Prior Work"` → ["Background", "Prior Work"])
   - Otherwise → search by text only
3. Search `doc.all_sections()` for matches
4. If path query → walk the tree: find first component, then find second component among its children, etc.
5. If exactly 1 match → `Found`
6. If 0 matches → compute fuzzy suggestions using `strsim::normalized_levenshtein`, return `SectionNotFound`
7. If >1 matches → return `AmbiguousMatch` with all matches

For fuzzy matching, use a threshold of ~0.5 similarity and return the top 3 suggestions.

- [ ] **Step 4: Run tests, verify pass**

Run: `cd claude-code-only/mdedit && cargo test addressing::tests`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/addressing.rs
git commit -m "feat(mdedit): section addressing with name, level, path, and fuzzy matching"
```

---

## Task 4: Content Input + Counting + Output Formatting

**Files:**
- Modify: `src/content.rs`
- Modify: `src/counting.rs`
- Modify: `src/output.rs`

- [ ] **Step 1: Write unit tests for content input**

```rust
// In src/content.rs

/// Resolve content from --content, --from-file, or stdin (in priority order)
pub fn resolve_content(
    content: Option<&str>,
    from_file: Option<&str>,
) -> Result<String, crate::error::MdeditError> {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::NamedTempFile;
    use std::io::Write;

    #[test]
    fn content_from_flag() {
        let result = resolve_content(Some("hello world"), None).unwrap();
        assert_eq!(result, "hello world");
    }

    #[test]
    fn content_from_file() {
        let mut f = NamedTempFile::new().unwrap();
        write!(f, "file content").unwrap();
        let result = resolve_content(None, Some(f.path().to_str().unwrap())).unwrap();
        assert_eq!(result, "file content");
    }

    #[test]
    fn content_flag_takes_priority_over_file() {
        let mut f = NamedTempFile::new().unwrap();
        write!(f, "file content").unwrap();
        let result = resolve_content(Some("flag content"), Some(f.path().to_str().unwrap())).unwrap();
        assert_eq!(result, "flag content");
    }

    #[test]
    fn no_content_returns_error() {
        let result = resolve_content(None, None);
        assert!(result.is_err());
    }
}
```

- [ ] **Step 2: Implement content.rs**

```rust
use crate::error::MdeditError;
use std::io::{self, Read};

pub fn resolve_content(
    content: Option<&str>,
    from_file: Option<&str>,
) -> Result<String, MdeditError> {
    if let Some(text) = content {
        return Ok(text.to_string());
    }
    if let Some(path) = from_file {
        return std::fs::read_to_string(path)
            .map_err(|e| MdeditError::ContentError(format!("--from-file not found: {} ({})", path, e)));
    }
    // Try stdin if not a TTY
    if !io::stdin().is_terminal() {
        let mut buf = String::new();
        io::stdin().read_to_string(&mut buf)
            .map_err(|e| MdeditError::ContentError(format!("Failed to read stdin: {}", e)))?;
        if !buf.is_empty() {
            return Ok(buf);
        }
    }
    Err(MdeditError::ContentError(
        "No content provided\nUse --content \"...\", --from-file <path>, or pipe to stdin".to_string()
    ))
}
```

Note: `io::stdin().is_terminal()` requires `use std::io::IsTerminal;` (stable since Rust 1.70).

- [ ] **Step 3: Run content tests**

Run: `cd claude-code-only/mdedit && cargo test content::tests`
Expected: PASS

- [ ] **Step 4: Write unit tests for counting**

```rust
// In src/counting.rs

use crate::document::{Document, Section};

/// Count words in a byte range of the source, excluding heading lines and blank lines
pub fn word_count(source: &str, range: &std::ops::Range<usize>) -> usize {
    todo!()
}

/// Count words for a section including all children
pub fn section_word_count(doc: &Document, section: &Section) -> usize {
    todo!()
}

/// Count words for a section's own content only (excluding children)
pub fn section_own_word_count(doc: &Document, section: &Section) -> usize {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser;

    #[test]
    fn word_count_simple_section() {
        let doc = parser::parse("# Title\n\n## Section\n\nOne two three.\nFour five.\n").unwrap();
        let section = &doc.sections[0].children[0];
        // "One two three." = 3 words, "Four five." = 2 words = 5 total
        assert_eq!(section_word_count(&doc, section), 5);
    }

    #[test]
    fn word_count_excludes_heading_line() {
        let doc = parser::parse("# Title\n\n## Section Name\n\nContent here.\n").unwrap();
        let section = &doc.sections[0].children[0];
        // Only "Content here." = 2 words (heading excluded)
        assert_eq!(section_word_count(&doc, section), 2);
    }

    #[test]
    fn word_count_excludes_blank_lines() {
        let doc = parser::parse("# T\n\n## S\n\nLine one.\n\nLine two.\n").unwrap();
        let section = &doc.sections[0].children[0];
        // "Line one." + "Line two." = 4 words
        assert_eq!(section_word_count(&doc, section), 4);
    }

    #[test]
    fn word_count_includes_code_fence_content() {
        let source = "# T\n\n## S\n\n```\ncode word\n```\n";
        let doc = parser::parse(source).unwrap();
        let section = &doc.sections[0].children[0];
        // "code word" = 2 words (code fence content counts)
        assert_eq!(section_word_count(&doc, section), 2);
    }

    #[test]
    fn word_count_with_children() {
        let doc = parser::parse("# T\n\n## Parent\n\nParent text.\n\n### Child\n\nChild text.\n").unwrap();
        let parent = &doc.sections[0].children[0];
        // "Parent text." = 2, "Child text." = 2, total = 4
        assert_eq!(section_word_count(&doc, parent), 4);
        // Own only = 2
        assert_eq!(section_own_word_count(&doc, parent), 2);
    }
}
```

- [ ] **Step 5: Implement counting.rs**

Key logic: extract the text for the byte range, split into lines, skip lines that are the heading line or blank, split remaining by whitespace, count tokens.

- [ ] **Step 6: Run counting tests**

Run: `cd claude-code-only/mdedit && cargo test counting::tests`
Expected: PASS

- [ ] **Step 7: Write output.rs with TTY detection and neighborhood formatting**

```rust
// In src/output.rs

use std::io::IsTerminal;
use crate::document::{Document, Section};
use crate::counting;

pub fn is_tty() -> bool {
    std::io::stdout().is_terminal()
}

/// Format the neighborhood view for a write operation
/// Shows previous section, target section, next section
pub fn format_neighborhood(
    doc: &Document,
    target: &Section,
    marker: &str,   // "→" for modified, "✗" for deleted, "+" prefix for added
) -> String {
    todo!() // Implement in Task 8 when write commands need it
}

/// Format a section summary for neighborhood view:
/// "  ## Heading\n  First line of content...\n  [N more lines]\n"
pub fn format_section_preview(doc: &Document, section: &Section) -> String {
    let content = doc.slice(&section.own_content_range).trim();
    let lines: Vec<&str> = content.lines().collect();

    let mut out = format!("  {}\n", section.full_heading());
    if let Some(first) = lines.iter().find(|l| !l.is_empty()) {
        out.push_str(&format!("  {}\n", first));
    }
    let remaining = if lines.len() > 1 { lines.len() - 1 } else { 0 };
    if remaining > 0 {
        out.push_str(&format!("  [{} more lines]\n", remaining));
    }
    out
}
```

- [ ] **Step 8: Commit**

```bash
git add src/content.rs src/counting.rs src/output.rs
git commit -m "feat(mdedit): content input, word/line counting, and output formatting"
```

---

## Task 5: outline + extract Commands

**Files:**
- Modify: `src/commands/outline.rs`
- Modify: `src/commands/extract.rs`
- Modify: `src/main.rs` (wire up commands)
- Create: `tests/outline.rs`
- Create: `tests/extract.rs`

- [ ] **Step 1: Write integration tests for outline**

```rust
// tests/outline.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn outline_simple() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("# My Document"))
        .stdout(predicate::str::contains("## Introduction"))
        .stdout(predicate::str::contains("## Background"))
        .stdout(predicate::str::contains("## Conclusion"))
        .stdout(predicate::str::contains("words"));
}

#[test]
fn outline_nested_shows_hierarchy() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", &common::fixture_path_str("nested.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("### Prior Work"))
        .stdout(predicate::str::contains("### Definitions"));
}

#[test]
fn outline_max_depth() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", &common::fixture_path_str("nested.md"), "--max-depth", "2"])
        .assert()
        .success()
        .stdout(predicate::str::contains("## Background"))
        // H3 should NOT appear
        .stdout(predicate::str::contains("### Prior Work").not());
}

#[test]
fn outline_flags_empty_sections() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", &common::fixture_path_str("empty_sections.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("⚠ empty"));
}

#[test]
fn outline_file_not_found() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", "nonexistent.md"])
        .assert()
        .code(3)
        .stderr(predicate::str::contains("ERROR"));
}
```

- [ ] **Step 2: Implement outline command**

In `src/commands/outline.rs`, implement the outline command per spec output format. Read the file, parse it, walk sections recursively, compute word counts and line ranges, format output with indentation.

See spec section "Commands — read operations > outline" for exact output format.

- [ ] **Step 3: Wire outline into main.rs dispatch**

In `src/main.rs`, update the match arm:
```rust
Commands::Outline { file, max_depth } => {
    commands::outline::run(&file, max_depth)
}
```

Handle the `Result` — on `Err`, print the error and exit with the error's exit code.

- [ ] **Step 4: Run outline tests**

Run: `cd claude-code-only/mdedit && cargo test --test outline`
Expected: PASS

- [ ] **Step 5: Write integration tests for extract**

```rust
// tests/extract.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn extract_section_shows_content() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("simple.md"), "Introduction"])
        .assert()
        .success()
        .stdout(predicate::str::contains("SECTION:"))
        .stdout(predicate::str::contains("introduction section"));
}

#[test]
fn extract_with_children() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("nested.md"), "Background"])
        .assert()
        .success()
        .stdout(predicate::str::contains("Prior Work"))
        .stdout(predicate::str::contains("Definitions"));
}

#[test]
fn extract_no_children() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("nested.md"), "Background", "--no-children"])
        .assert()
        .success()
        .stdout(predicate::str::contains("children excluded"))
        .stdout(predicate::str::contains("Prior Work").not());
}

#[test]
fn extract_to_file() {
    let dir = tempfile::tempdir().unwrap();
    let out_path = dir.path().join("section.md");
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("simple.md"), "Introduction",
                "--to-file", out_path.to_str().unwrap()])
        .assert()
        .success()
        .stdout(predicate::str::contains("EXTRACTED:"))
        .stdout(predicate::str::contains("→"));

    // Verify file was written
    let content = std::fs::read_to_string(&out_path).unwrap();
    assert!(content.contains("introduction section"));
    // Should NOT contain SECTION: header
    assert!(!content.contains("SECTION:"));
}

#[test]
fn extract_preamble() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("with_preamble.md"), "_preamble"])
        .assert()
        .success()
        .stdout(predicate::str::contains("preamble text"));
}

#[test]
fn extract_not_found() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("simple.md"), "Nonexistent"])
        .assert()
        .code(1)
        .stderr(predicate::str::contains("not found"));
}

#[test]
fn extract_empty_section() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("empty_sections.md"), "Empty Section"])
        .assert()
        .success()
        .stdout(predicate::str::contains("[no content]"));
}
```

- [ ] **Step 6: Implement extract command**

See spec section "Commands — read operations > extract" for exact output format, including TTY vs pipe behavior and `--to-file` output.

- [ ] **Step 7: Wire extract into main.rs dispatch**

- [ ] **Step 8: Run extract tests**

Run: `cd claude-code-only/mdedit && cargo test --test extract`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/commands/outline.rs src/commands/extract.rs src/main.rs tests/outline.rs tests/extract.rs
git commit -m "feat(mdedit): outline and extract commands with TTY-aware output"
```

---

## Task 6: search + stats + validate Commands

**Files:**
- Modify: `src/commands/search.rs`
- Modify: `src/commands/stats.rs`
- Modify: `src/commands/validate.rs`
- Modify: `src/main.rs` (wire up)
- Create: `tests/search.rs`, `tests/stats.rs`, `tests/validate.rs`

- [ ] **Step 1: Write integration tests for search**

```rust
// tests/search.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn search_finds_matches_grouped_by_section() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["search", &common::fixture_path_str("simple.md"), "content"])
        .assert()
        .success()
        .stdout(predicate::str::contains("SEARCH:"))
        .stdout(predicate::str::contains("## Introduction"));
}

#[test]
fn search_case_insensitive_by_default() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["search", &common::fixture_path_str("simple.md"), "INTRODUCTION"])
        .assert()
        .success()
        .stdout(predicate::str::contains("match"));
}

#[test]
fn search_case_sensitive_flag() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["search", &common::fixture_path_str("simple.md"), "INTRODUCTION", "--case-sensitive"])
        .assert()
        .success()
        // Should find 0 matches since source uses lowercase
        .stdout(predicate::str::contains("0 matches"));
}

#[test]
fn search_highlights_with_pipes() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["search", &common::fixture_path_str("simple.md"), "constraints"])
        .assert()
        .success()
        .stdout(predicate::str::contains("|constraints|"));
}
```

- [ ] **Step 2: Implement search command**

Per spec: case-insensitive by default, results grouped by section, matches highlighted with `|pipes|`.

- [ ] **Step 3: Write integration tests for stats**

```rust
// tests/stats.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn stats_shows_word_counts() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("STATS:"))
        .stdout(predicate::str::contains("words"));
}

#[test]
fn stats_shows_percentages() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("%"));
}

#[test]
fn stats_annotates_largest_section() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("← largest"));
}

#[test]
fn stats_annotates_empty_sections() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("empty_sections.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("← empty"));
}

#[test]
fn stats_shows_hierarchy() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("nested.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("### Prior Work"));
}
```

- [ ] **Step 4: Implement stats command**

Per spec: word/line counts per section, percentages relative to total.

- [ ] **Step 5: Write integration tests for validate**

```rust
// tests/validate.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn validate_clean_document() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["validate", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("VALID"));
}

#[test]
fn validate_finds_empty_sections() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["validate", &common::fixture_path_str("empty_sections.md")])
        .assert()
        .code(5)
        .stdout(predicate::str::contains("⚠"))
        .stdout(predicate::str::contains("empty"));
}

#[test]
fn validate_finds_duplicate_headings() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["validate", &common::fixture_path_str("duplicate_headings.md")])
        .assert()
        .success() // ℹ only, not ⚠, so exit 0
        .stdout(predicate::str::contains("ℹ"))
        .stdout(predicate::str::contains("Duplicate"));
}
```

- [ ] **Step 6: Implement validate command**

Checks: skipped heading levels, empty sections, duplicate heading text. Exit 5 only for `⚠` warnings, exit 0 for `ℹ` info only.

- [ ] **Step 7: Wire all three commands into main.rs**

- [ ] **Step 8: Run all tests**

Run: `cd claude-code-only/mdedit && cargo test --test search --test stats --test validate`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/commands/{search,stats,validate}.rs src/main.rs tests/{search,stats,validate}.rs
git commit -m "feat(mdedit): search, stats, and validate commands"
```

---

## Task 7: frontmatter Commands (read + set + delete)

**Files:**
- Modify: `src/commands/frontmatter.rs`
- Modify: `src/main.rs`
- Create: `tests/frontmatter.rs`

- [ ] **Step 1: Write integration tests**

```rust
// tests/frontmatter.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn frontmatter_show_all() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", &common::fixture_path_str("with_frontmatter.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("FRONTMATTER:"))
        .stdout(predicate::str::contains("title:"))
        .stdout(predicate::str::contains("tags:"));
}

#[test]
fn frontmatter_get_key() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "get", &common::fixture_path_str("with_frontmatter.md"), "title"])
        .assert()
        .success()
        .stdout(predicate::str::contains("My Document"));
}

#[test]
fn frontmatter_get_missing_key() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "get", &common::fixture_path_str("with_frontmatter.md"), "nonexistent"])
        .assert()
        .code(4)
        .stderr(predicate::str::contains("not found"));
}

#[test]
fn frontmatter_set() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: \"Old\"\n---\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "set", file.to_str().unwrap(), "title", "\"New\""])
        .assert()
        .success()
        .stdout(predicate::str::contains("FRONTMATTER SET:"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New"));
}

#[test]
fn frontmatter_delete_key() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: \"Doc\"\ndraft: true\n---\n\n# H\n\nC.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "delete", file.to_str().unwrap(), "draft"])
        .assert()
        .success()
        .stdout(predicate::str::contains("FRONTMATTER DELETED:"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("draft"));
    assert!(result.contains("title")); // other keys preserved
}

#[test]
fn frontmatter_no_frontmatter() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", &common::fixture_path_str("simple.md")])
        .assert()
        .code(3)
        .stderr(predicate::str::contains("No frontmatter"));
}

#[test]
fn frontmatter_set_dry_run() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: \"Old\"\n---\n\n# H\n\nC.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "set", file.to_str().unwrap(), "title", "\"New\"", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    // File should NOT be changed
    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Old"));
}
```

- [ ] **Step 2: Implement frontmatter command**

Parse YAML frontmatter with `serde_yaml`. For `set`, parse value as JSON if valid, otherwise treat as plain string. For `delete`, remove the key. Write back by splicing the new frontmatter YAML into the document at the frontmatter byte range.

Note: The clap modelling for `frontmatter` is tricky because it supports both `mdedit frontmatter <file>` and `mdedit frontmatter get <file> <key>`. You may need to adjust the clap structure from Task 1. Consider using `#[command(subcommand)]` for the action, with a fallback to "show all" when no subcommand is given.

- [ ] **Step 3: Wire into main.rs, run tests**

Run: `cd claude-code-only/mdedit && cargo test --test frontmatter`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/commands/frontmatter.rs src/main.rs tests/frontmatter.rs
git commit -m "feat(mdedit): frontmatter read, get, set, delete commands"
```

---

## Task 8: Write Infrastructure + replace Command

**Files:**
- Modify: `src/output.rs` (complete the neighborhood formatter)
- Modify: `src/whitespace.rs`
- Modify: `src/commands/replace.rs`
- Modify: `src/main.rs`
- Create: `tests/replace.rs`

This is the most complex task — it establishes all the infrastructure that write commands share.

- [ ] **Step 1: Write unit tests for whitespace normalisation**

```rust
// In src/whitespace.rs

/// Normalise whitespace at section boundaries:
/// - Exactly one blank line between sections
/// - Exactly one trailing newline at EOF
/// - Whitespace within section content is never modified
pub fn normalise(source: &str) -> String {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalise_double_blank_lines() {
        let input = "# Title\n\n\n\n## Section\n\nContent.\n";
        let result = normalise(input);
        // Should have exactly one blank line between title content and ## Section
        assert!(!result.contains("\n\n\n"));
    }

    #[test]
    fn normalise_trailing_newline() {
        let input = "# Title\n\nContent.\n\n\n";
        let result = normalise(input);
        assert!(result.ends_with('\n'));
        assert!(!result.ends_with("\n\n"));
    }

    #[test]
    fn normalise_preserves_internal_whitespace() {
        let input = "# Title\n\n## Section\n\nLine one.\n\nLine two.\n";
        let result = normalise(input);
        // The blank line between "Line one." and "Line two." should be preserved
        assert!(result.contains("Line one.\n\nLine two."));
    }
}
```

- [ ] **Step 2: Implement whitespace.rs**

Key insight: normalisation only affects blank lines *between* sections (i.e., at positions where one section ends and another begins). It must NOT affect blank lines within content. The simplest approach: re-parse the result after splicing, identify section boundary positions, and ensure exactly one blank line at each.

Alternative simpler approach: after the splice, only normalise the area around the splice point (the bytes that changed), not the entire document. This is more efficient and less error-prone.

- [ ] **Step 3: Complete the neighborhood formatter in output.rs**

```rust
/// Format the full write operation output:
/// summary line + warnings + neighborhood view
pub fn format_write_output(
    doc: &Document,           // document BEFORE the write
    target: &Section,
    action: &str,             // "REPLACED", "APPENDED", etc.
    summary: &str,            // e.g. "(was 12 lines → now 8 lines)"
    new_content_preview: &str, // first+last lines of new content
    warnings: &[String],
    dry_run: bool,
) -> String {
    let mut out = String::new();

    if dry_run {
        out.push_str("DRY RUN — no changes written\n\n");
    }

    // Summary line
    let verb = if dry_run {
        format!("WOULD {}", action)
    } else {
        action.to_string()
    };
    out.push_str(&format!("{}: \"{}\" {}\n", verb, target.full_heading(), summary));

    // Warnings
    for w in warnings {
        out.push_str(&format!("⚠ {}\n", w));
    }

    out.push('\n');

    // Previous section
    if let Some(prev) = find_previous_section(doc, target) {
        out.push_str(&format_section_preview(doc, prev));
        out.push('\n');
    }

    // Target section (with → marker)
    out.push_str(&format!("→ {}\n", target.full_heading()));
    out.push_str(new_content_preview);
    out.push('\n');

    // Next section
    if let Some(next) = find_next_section(doc, target) {
        out.push_str(&format_section_preview(doc, next));
    } else {
        out.push_str("  [end of document]\n");
    }

    out
}
```

The `find_previous_section` and `find_next_section` helpers need to walk the document's flat section list to find siblings. Implement these.

The `format_section_preview` shows: heading + first line + `[N more lines]` per the spec.

- [ ] **Step 4: Write integration tests for replace**

```rust
// tests/replace.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn replace_section_content() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOld content.\n\n## Other\n\nOther content.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "New content."])
        .assert()
        .success()
        .stdout(predicate::str::contains("REPLACED"))
        .stdout(predicate::str::contains("→ ## Section"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New content."));
    assert!(!result.contains("Old content."));
    assert!(result.contains("Other content.")); // other section preserved
}

#[test]
fn replace_from_file() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOld.\n"
    );
    let content_file = dir.path().join("new_content.md");
    std::fs::write(&content_file, "Replacement text.").unwrap();

    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section",
                "--from-file", content_file.to_str().unwrap()])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Replacement text."));
}

#[test]
fn replace_preserve_children() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Parent\n\nParent content.\n\n### Child\n\nChild content.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Parent",
                "--content", "New parent content.", "--preserve-children"])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New parent content."));
    assert!(result.contains("### Child"));        // child preserved
    assert!(result.contains("Child content."));   // child content preserved
}

#[test]
fn replace_warns_on_large_reduction() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nLine 1.\nLine 2.\nLine 3.\nLine 4.\nLine 5.\nLine 6.\nLine 7.\nLine 8.\nLine 9.\nLine 10.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "Short."])
        .assert()
        .success()
        .stdout(predicate::str::contains("⚠"));
}

#[test]
fn replace_no_change() {
    let content = "# Doc\n\n## Section\n\nContent.\n";
    let (dir, file) = common::temp_md_file(content);
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "Content."])
        .assert()
        .code(10)
        .stdout(predicate::str::contains("NO CHANGE"));
}

#[test]
fn replace_dry_run() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOld.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"))
        .stdout(predicate::str::contains("WOULD REPLACE"));

    // File unchanged
    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Old."));
}

#[test]
fn replace_section_not_found() {
    let (dir, file) = common::temp_md_file("# Doc\n\n## Section\n\nContent.\n");
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Nonexistent", "--content", "X"])
        .assert()
        .code(1);
}

#[test]
fn replace_shows_before_after_metrics() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOld line 1.\nOld line 2.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "New line."])
        .assert()
        .success()
        .stdout(predicate::str::contains("was"))
        .stdout(predicate::str::contains("now"));
}
```

- [ ] **Step 5: Implement replace command**

The core write operation — source surgery:
1. Parse the file
2. Resolve the section
3. Determine the byte range to replace:
   - Default: `own_content_range.start..full_range.end` (replaces own content + children)
   - With `--preserve-children`: `own_content_range` only
4. Compare old content with new — if identical, return `NoOp`
5. Generate warnings (large reduction, children removed)
6. If `--dry-run`, format output and return without writing
7. Splice: `source[..range.start] + new_content + source[range.end..]`
8. Normalise whitespace
9. Write file
10. Re-parse the result to generate accurate neighborhood output

```rust
pub fn run(
    file: &str,
    section_query: &str,
    content: Option<&str>,
    from_file: Option<&str>,
    preserve_children: bool,
    dry_run: bool,
) -> Result<(), MdeditError> {
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("{}: {}", file, e)))?;
    let doc = parser::parse(&source)?;

    let new_content = content::resolve_content(content, from_file)?;

    let section = match addressing::resolve(&doc, section_query)? {
        addressing::ResolvedSection::Found(s) => s,
        addressing::ResolvedSection::Preamble => {
            // Handle preamble replace separately
            return replace_preamble(&doc, file, &new_content, dry_run);
        }
    };

    // Determine byte range to replace
    let replace_range = if preserve_children && !section.children.is_empty() {
        section.own_content_range.clone()
    } else {
        section.own_content_range.start..section.full_range.end
    };

    let old_content = &source[replace_range.clone()];

    // Trailing newline on new content
    let new_with_newline = if new_content.ends_with('\n') {
        new_content.clone()
    } else {
        format!("{}\n", new_content)
    };

    // No-op check
    if old_content.trim() == new_with_newline.trim() {
        return Err(MdeditError::NoOp("Section content is identical to replacement".to_string()));
    }

    // Generate warnings
    let mut warnings = Vec::new();
    let old_lines = old_content.lines().count();
    let new_lines = new_with_newline.lines().count();
    if old_lines > 2 && new_lines < old_lines / 2 {
        warnings.push(format!("Large reduction: {} lines → {} lines", old_lines, new_lines));
    }
    if !preserve_children && !section.children.is_empty() {
        let child_names: Vec<String> = section.children.iter()
            .map(|c| c.full_heading())
            .collect();
        warnings.push(format!("{} child sections removed: {}",
            section.children.len(), child_names.join(", ")));
    }

    // Splice
    let mut result = String::with_capacity(source.len());
    result.push_str(&source[..replace_range.start]);
    result.push_str(&new_with_newline);
    if preserve_children && !section.children.is_empty() {
        result.push_str(&source[replace_range.end..]);
    } else {
        // When replacing including children, append from after the section
        result.push_str(&source[replace_range.end..]);
    }

    let result = whitespace::normalise(&result);

    // Format output (using original doc for neighborhood context)
    // ... format summary, neighborhood, etc.

    if !dry_run {
        std::fs::write(file, &result)
            .map_err(|e| MdeditError::FileError(format!("Failed to write {}: {}", file, e)))?;
    }

    // Print output
    // ...

    Ok(())
}
```

This is a sketch — the actual implementation should handle all the output formatting per the spec.

- [ ] **Step 6: Wire replace into main.rs**

- [ ] **Step 7: Run replace tests**

Run: `cd claude-code-only/mdedit && cargo test --test replace`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/whitespace.rs src/output.rs src/commands/replace.rs src/main.rs tests/replace.rs
git commit -m "feat(mdedit): write infrastructure (splice, whitespace, neighborhood) and replace command"
```

---

## Task 9: append + prepend Commands

**Files:**
- Modify: `src/commands/append.rs`
- Modify: `src/commands/prepend.rs`
- Modify: `src/main.rs`
- Create: `tests/append.rs`, `tests/prepend.rs`

These commands follow the same pattern as `replace` but are simpler — they insert content at a specific position rather than replacing a range.

- [ ] **Step 1: Write integration tests for append**

```rust
// tests/append.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn append_to_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting content.\n\n## Other\n\nOther.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Section", "--content", "Appended line."])
        .assert()
        .success()
        .stdout(predicate::str::contains("APPENDED"))
        .stdout(predicate::str::contains("+"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Existing content."));
    assert!(result.contains("Appended line."));
    // Appended content should come after existing, before ## Other
    let existing_pos = result.find("Existing content.").unwrap();
    let appended_pos = result.find("Appended line.").unwrap();
    let other_pos = result.find("## Other").unwrap();
    assert!(existing_pos < appended_pos);
    assert!(appended_pos < other_pos);
}

#[test]
fn append_to_empty_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Empty\n\n## Next\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Empty", "--content", "New content."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New content."));
}

#[test]
fn append_shows_plus_prefix() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Section", "--content", "Added."])
        .assert()
        .success()
        .stdout(predicate::str::contains("+ Added."));
}
```

- [ ] **Step 2: Implement append command**

Append inserts content at the end of the section's own content (before children or before next section). The splice point is `own_content_range.end`. If the section has no trailing newline, add one before the appended content.

**`_preamble` handling:** When `addressing::resolve` returns `ResolvedSection::Preamble`, append to the preamble byte range. The splice point is `doc.preamble.end` (or, if no preamble exists, the byte after frontmatter's closing `---`, or byte 0 if no frontmatter). Append content goes before the first heading.

- [ ] **Step 3: Write integration tests for prepend**

```rust
// tests/prepend.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn prepend_to_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting content.\n\n## Other\n\nOther.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--content", "Prepended line."])
        .assert()
        .success()
        .stdout(predicate::str::contains("PREPENDED"))
        .stdout(predicate::str::contains("+"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Prepended line."));
    assert!(result.contains("Existing content."));
    // Prepended content should come before existing
    let prepended_pos = result.find("Prepended line.").unwrap();
    let existing_pos = result.find("Existing content.").unwrap();
    assert!(prepended_pos < existing_pos);
}

#[test]
fn prepend_goes_after_heading() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--content", "First."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    // Heading should still be before prepended content
    let heading_pos = result.find("## Section").unwrap();
    let prepended_pos = result.find("First.").unwrap();
    assert!(heading_pos < prepended_pos);
}

#[test]
fn prepend_to_empty_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Empty\n\n## Next\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Empty", "--content", "Now has content."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Now has content."));
}

#[test]
fn prepend_shows_plus_prefix() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--content", "Added."])
        .assert()
        .success()
        .stdout(predicate::str::contains("+ Added."));
}

#[test]
fn prepend_dry_run() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("New.")); // unchanged
}
```

- [ ] **Step 4: Implement prepend command**

Prepend inserts content at the start of the section's own content (right after the heading line). The splice point is `own_content_range.start`.

**`_preamble` handling:** When `ResolvedSection::Preamble`, prepend to the start of the preamble. The splice point is `doc.preamble.start` (or the byte after frontmatter's closing `---`, or byte 0 if no frontmatter). Content is placed immediately after frontmatter, before any existing preamble text.

- [ ] **Step 5: Wire both into main.rs, run tests**

Run: `cd claude-code-only/mdedit && cargo test --test append --test prepend`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/commands/{append,prepend}.rs src/main.rs tests/{append,prepend}.rs
git commit -m "feat(mdedit): append and prepend commands"
```

---

## Task 10: insert + delete + rename Commands

**Files:**
- Modify: `src/commands/insert.rs`
- Modify: `src/commands/delete.rs`
- Modify: `src/commands/rename.rs`
- Modify: `src/main.rs`
- Create: `tests/insert.rs`, `tests/delete_cmd.rs`, `tests/rename.rs`

- [ ] **Step 1: Write integration tests for insert**

```rust
// tests/insert.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn insert_after_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## First\n\nFirst content.\n\n## Third\n\nThird content.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--after", "First", "--heading", "## Second", "--content", "Second content."])
        .assert()
        .success()
        .stdout(predicate::str::contains("INSERTED"));

    let result = std::fs::read_to_string(&file).unwrap();
    let first_pos = result.find("## First").unwrap();
    let second_pos = result.find("## Second").unwrap();
    let third_pos = result.find("## Third").unwrap();
    assert!(first_pos < second_pos);
    assert!(second_pos < third_pos);
}

#[test]
fn insert_before_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## First\n\nContent.\n\n## Second\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--before", "Second", "--heading", "## Middle", "--content", "Middle content."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    let first_pos = result.find("## First").unwrap();
    let middle_pos = result.find("## Middle").unwrap();
    let second_pos = result.find("## Second").unwrap();
    assert!(first_pos < middle_pos);
    assert!(middle_pos < second_pos);
}

#[test]
fn insert_warns_on_level_mismatch() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## First\n\nContent.\n\n## Second\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--after", "First", "--heading", "### Wrong Level"])
        .assert()
        .success()
        .stdout(predicate::str::contains("⚠"));
}

#[test]
fn insert_without_content_creates_empty_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## First\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--after", "First", "--heading", "## Empty New"])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("## Empty New"));
}

#[test]
fn insert_requires_after_or_before() {
    let (dir, file) = common::temp_md_file("# Doc\n");
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(), "--heading", "## New"])
        .assert()
        .failure(); // clap should enforce this
}
```

- [ ] **Step 2: Implement insert command**

Insert creates a new section at a position. The splice point is:
- `--after "Section"`: insert after the target section's `full_range.end`
- `--before "Section"`: insert at the target section's `full_range.start`

Build the new section text: `heading + "\n\n" + content + "\n"`. Splice into source.

Warn if the heading level of the new section doesn't match the level of its neighbors.

**`_preamble` handling:**
- `--after "_preamble"`: insert the new section after the preamble, before the first existing section. Splice point is the first section's `full_range.start`, or end of preamble if no sections exist.
- `--before "_preamble"`: **invalid per spec.** Return `MdeditError::InvalidOperation("insert --before _preamble is not valid; use prepend to _preamble instead")`.


- [ ] **Step 3: Write integration tests for delete**

```rust
// tests/delete_cmd.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn delete_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Keep\n\nKeep content.\n\n## Remove\n\nRemove content.\n\n## Also Keep\n\nAlso keep.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["delete", file.to_str().unwrap(), "Remove"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DELETED"))
        .stdout(predicate::str::contains("✗"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("Remove content."));
    assert!(result.contains("Keep content."));
    assert!(result.contains("Also keep."));
}

#[test]
fn delete_shows_was_lines() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nFirst line.\nLast line.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["delete", file.to_str().unwrap(), "Section"])
        .assert()
        .success()
        .stdout(predicate::str::contains("Was:"));
}

#[test]
fn delete_warns_about_children() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Parent\n\nContent.\n\n### Child\n\nChild content.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["delete", file.to_str().unwrap(), "Parent"])
        .assert()
        .success()
        .stdout(predicate::str::contains("⚠"))
        .stdout(predicate::str::contains("child"));
}

#[test]
fn delete_dry_run() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["delete", file.to_str().unwrap(), "Section", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Content.")); // not deleted
}
```

- [ ] **Step 4: Implement delete command**

Delete removes the section's `full_range` from the source. Show the deleted content's first and last lines in output with `Was:` prefix.

**`_preamble` handling:** When `ResolvedSection::Preamble`, remove all bytes in the preamble range (`doc.preamble`). If no preamble exists, return `NoOp`. Output shows `DELETED: "_preamble"` with the removed content's first and last lines.

- [ ] **Step 5: Write integration tests for rename**

```rust
// tests/rename.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn rename_heading() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Old Name\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["rename", file.to_str().unwrap(), "Old Name", "New Name"])
        .assert()
        .success()
        .stdout(predicate::str::contains("RENAMED"))
        .stdout(predicate::str::contains("→"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("## New Name"));
    assert!(!result.contains("## Old Name"));
    assert!(result.contains("Content.")); // content preserved
}

#[test]
fn rename_preserves_level() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n### Deep Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["rename", file.to_str().unwrap(), "Deep Heading", "New Deep"])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("### New Deep")); // still H3
}
```

- [ ] **Step 6: Implement rename command**

Rename replaces only the heading line. Splice the `heading_range` with the new heading text at the same level: `format!("{} {}\n", "#".repeat(level), new_name)`.

**`_preamble` handling:** When `ResolvedSection::Preamble`, return `MdeditError::InvalidOperation("rename is not valid for _preamble (no heading to rename)")`. The preamble has no heading, so renaming it is meaningless.

- [ ] **Step 7: Wire all three into main.rs, run tests**

Run: `cd claude-code-only/mdedit && cargo test --test insert --test delete_cmd --test rename`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/commands/{insert,delete,rename}.rs src/main.rs tests/{insert,delete_cmd,rename}.rs
git commit -m "feat(mdedit): insert, delete, and rename commands"
```

---

## Task 11: Help Text + End-to-End Polish

**Files:**
- Modify: `src/main.rs` (custom help text)
- Possibly modify various command files for output consistency

- [ ] **Step 1: Verify all commands work end-to-end**

Run: `cd claude-code-only/mdedit && cargo test`
Expected: All tests pass

- [ ] **Step 2: Test the CLI manually against the spec**

Run each command against the fixtures and compare output to the spec examples:

```bash
cd claude-code-only/mdedit
cargo run -- outline tests/fixtures/simple.md
cargo run -- extract tests/fixtures/simple.md "Introduction"
cargo run -- extract tests/fixtures/nested.md "Background" --no-children
cargo run -- search tests/fixtures/simple.md "content"
cargo run -- stats tests/fixtures/nested.md
cargo run -- validate tests/fixtures/empty_sections.md
cargo run -- frontmatter tests/fixtures/with_frontmatter.md
cargo run -- --help
cargo run -- replace --help
```

Fix any output format discrepancies vs the spec.

- [ ] **Step 3: Customize help text to match spec**

The spec defines exact help text format in the "Help text" section. Clap's default `--help` won't match exactly. Use clap's `help_template` and `about` attributes to get as close as possible. The key requirements:
- Top-level help shows all commands grouped (read ops, then write ops)
- Each subcommand help shows Input/Output/Exits contract
- Exit codes listed at the bottom of top-level help

If clap's built-in formatting can't fully match the spec, consider a custom `--help` handler that prints the exact spec-defined text.

- [ ] **Step 4: Write pipe-mode integration test**

```rust
// Test that extract outputs raw markdown when piped (not TTY)
// In integration tests, stdout is never a TTY (it's captured), so this tests
// the pipe behavior automatically. Add explicit tests for TTY behavior if needed.
```

- [ ] **Step 5: Write end-to-end workflow test**

```rust
// Test the file-mode workflow: extract → edit → replace
#[test]
fn file_mode_workflow() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOriginal content.\n\n## Other\n\nOther content.\n"
    );
    let temp_section = dir.path().join("section.md");

    // Step 1: Extract
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", file.to_str().unwrap(), "Section",
                "--to-file", temp_section.to_str().unwrap()])
        .assert()
        .success();

    // Step 2: Edit the temp file (simulating LLM Edit tool)
    let content = std::fs::read_to_string(&temp_section).unwrap();
    let modified = content.replace("Original", "Modified");
    std::fs::write(&temp_section, modified).unwrap();

    // Step 3: Replace from file
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section",
                "--from-file", temp_section.to_str().unwrap()])
        .assert()
        .success()
        .stdout(predicate::str::contains("REPLACED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Modified content."));
    assert!(result.contains("Other content.")); // other section untouched
}
```

- [ ] **Step 6: Run all tests**

Run: `cd claude-code-only/mdedit && cargo test`
Expected: All tests pass

- [ ] **Step 7: Build release binary**

Run: `cd claude-code-only/mdedit && cargo build --release`
Expected: Binary at `target/release/mdedit`

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(mdedit): help text, end-to-end tests, and release build"
```

---

## Notes for Implementers

### tree-sitter node kinds to verify

The parser implementation depends on exact node kind strings from tree-sitter-md. If any don't match, add a debug helper:

```rust
fn debug_tree(node: tree_sitter::Node, source: &str, depth: usize) {
    let indent = "  ".repeat(depth);
    let text = &source[node.start_byte()..node.end_byte().min(node.start_byte() + 40)];
    eprintln!("{}{}  [{}-{}]  {:?}",
        indent, node.kind(), node.start_byte(), node.end_byte(),
        text.replace('\n', "\\n"));
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        debug_tree(child, source, depth + 1);
    }
}
```

Run with a simple markdown file and verify the node kinds match the code.

### Common pitfalls

1. **Byte ranges vs line numbers**: tree-sitter gives byte offsets and 0-indexed row/column. Always convert to 1-indexed for output.
2. **Trailing newlines**: sections may or may not end with `\n`. Always ensure spliced content has appropriate trailing newlines.
3. **Whitespace normalisation**: must only affect section boundaries, never content within sections. Be careful with regex-based approaches.
4. **Empty sections**: a heading followed immediately by another heading. The `own_content_range` will have `start == end` (empty). Handle gracefully.
5. **The `_preamble` case**: write commands need special handling for `_preamble` since there's no heading to anchor against.
6. **`frontmatter` clap modelling**: the dual interface (`mdedit frontmatter <file>` vs `mdedit frontmatter get <file> <key>`) is tricky with clap's derive API. Consider making the subcommand optional and falling back to "show all" when absent.
