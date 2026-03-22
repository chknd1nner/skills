use std::process;

use crate::addressing::{resolve, ResolvedSection};
use crate::content::resolve_content;
use crate::counting::word_count;
use crate::error::MdeditError;
use crate::output::format_neighborhood;
use crate::parser;
use crate::whitespace::normalise;

pub fn run(
    file: &str,
    section_query: &str,
    content: Option<&str>,
    from_file: Option<&str>,
    preserve_children: bool,
    dry_run: bool,
) -> Result<(), MdeditError> {
    // 1. Read and parse the file
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("Cannot read '{}': {}", file, e)))?;

    let doc = parser::parse(&source)
        .map_err(|e| MdeditError::FileError(format!("Parse error in '{}': {}", file, e)))?;

    // 2. Resolve section
    let resolved = resolve(&doc, section_query).map_err(|e| match e {
        MdeditError::SectionNotFound { query, suggestions, .. } => {
            MdeditError::SectionNotFound { query, file: file.to_string(), suggestions }
        }
        MdeditError::AmbiguousMatch { query, matches, .. } => {
            MdeditError::AmbiguousMatch { query, file: file.to_string(), matches }
        }
        other => other,
    })?;

    let section = match resolved {
        ResolvedSection::Found(s) => s,
        ResolvedSection::Preamble => {
            return Err(MdeditError::InvalidOperation(
                "replace does not support _preamble; use a section heading".to_string(),
            ));
        }
    };

    // 3. Resolve new content
    let new_content_raw = resolve_content(content, from_file)?;

    // Normalise the new content: ensure it ends with a newline
    let new_content = if new_content_raw.ends_with('\n') {
        new_content_raw.clone()
    } else {
        format!("{}\n", new_content_raw)
    };

    // 4. Determine byte range to replace
    // Default: replace own content + children (own_content_range.start..full_range.end)
    // With --preserve-children: replace only own content (own_content_range)
    let replace_range = if preserve_children {
        section.own_content_range.clone()
    } else {
        section.own_content_range.start..section.full_range.end
    };

    // 5. Get the old content at that range
    let old_content = &source[replace_range.clone()];

    // 6. Check for no-op: if new content matches old content exactly
    // Compare by trimming all surrounding whitespace from both sides, since
    // own_content_range starts with a leading newline (blank line after heading).
    let old_trimmed = old_content.trim();
    let new_trimmed = new_content.trim();
    if old_trimmed == new_trimmed {
        println!("NO CHANGE: Section content is identical to replacement");
        process::exit(10);
    }

    // 7. Calculate metrics for display
    // Use trimmed content for line counting to exclude leading blank line from own_content_range
    let old_line_count = old_content.trim().lines().count();
    let new_line_count = new_content.trim().lines().count();

    // Word counts
    let old_words = word_count(&source, &replace_range);
    let new_words = word_count(&new_content, &(0..new_content.len()));

    // 8. Build warnings
    let mut warnings: Vec<String> = Vec::new();

    // Large reduction warning: >50% reduction in lines
    if old_line_count > 0 && new_line_count < old_line_count {
        let reduction_pct = ((old_line_count - new_line_count) * 100) / old_line_count;
        if reduction_pct > 50 {
            warnings.push(format!(
                "Large reduction: {} lines → {} lines",
                old_line_count, new_line_count
            ));
        }
    }

    // Children removed warning (only when not preserving children)
    if !preserve_children && !section.children.is_empty() {
        let child_headings: Vec<String> = section.children.iter()
            .map(|c| c.full_heading())
            .collect();
        warnings.push(format!(
            "{} child section{} removed: {}",
            section.children.len(),
            if section.children.len() == 1 { "" } else { "s" },
            child_headings.join(", ")
        ));
    }

    // 9. Build the summary string
    let summary = format!(
        "(was {} lines, {} words → now {} lines, {} words)",
        old_line_count, old_words, new_line_count, new_words
    );

    // Determine action label
    let action_label = if dry_run { "WOULD REPLACE" } else { "REPLACED" };

    // 10. If preserve_children, we need a doc with merged content for neighbourhood display.
    // For dry-run, we don't actually write. We format neighbourhood using the new content preview.
    let output = format_neighborhood(
        &doc,
        section,
        action_label,
        &summary,
        &new_content,
        &warnings,
        dry_run,
    );

    if dry_run {
        print!("{}", output);
        return Ok(());
    }

    // 11. Splice: source[..range.start] + new_content + source[range.end..]
    let new_source = format!(
        "{}{}{}",
        &source[..replace_range.start],
        new_content,
        &source[replace_range.end..]
    );

    // 12. Normalise whitespace
    let normalised = normalise(&new_source);

    // 13. Write the file
    std::fs::write(file, &normalised)
        .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

    // 14. Print the formatted output
    print!("{}", output);

    Ok(())
}
