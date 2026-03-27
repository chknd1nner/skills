use crate::addressing::{resolve, ResolvedSection};
use crate::counting::word_count;
use crate::error::MdeditError;
use crate::output::{emit_verification, find_next_section, find_previous_section, format_section_preview};
use crate::parser;
use crate::whitespace::normalise;

pub fn run(file: &str, section_query: &str, dry_run: bool) -> Result<(), MdeditError> {
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("Cannot read '{}': {}", file, e)))?;

    let doc = parser::parse(&source)
        .map_err(|e| MdeditError::FileError(format!("Parse error in '{}': {}", file, e)))?;

    let resolved = resolve(&doc, section_query).map_err(|e| match e {
        MdeditError::SectionNotFound {
            query, suggestions, ..
        } => MdeditError::SectionNotFound {
            query,
            file: file.to_string(),
            suggestions,
        },
        MdeditError::AmbiguousMatch {
            query, matches, ..
        } => MdeditError::AmbiguousMatch {
            query,
            file: file.to_string(),
            matches,
        },
        other => other,
    })?;

    let section = match resolved {
        ResolvedSection::Found(s) => s,
        ResolvedSection::Preamble => {
            // Delete preamble content
            if let Some(ref preamble_range) = doc.preamble {
                let preamble_content = &source[preamble_range.clone()];
                if preamble_content.trim().is_empty() {
                    return Err(MdeditError::NoOp("Preamble is already empty".to_string()));
                }
                let action_label = if dry_run { "WOULD DELETE" } else { "DELETED" };
                let words = word_count(&source, preamble_range);
                let mut output = String::new();
                if dry_run {
                    output.push_str("DRY RUN \u{2014} no changes written\n\n");
                }
                output.push_str(&format!(
                    "{}: \"_preamble\" ({} words)\n",
                    action_label, words
                ));

                // Neighborhood context for preamble delete
                output.push('\n');

                // Deleted preamble with ✗ marker
                output.push_str("\u{2717} _preamble (deleted)\n");
                let preamble_text = preamble_content.trim();
                let preamble_lines: Vec<&str> = preamble_text.lines().filter(|l| !l.trim().is_empty()).collect();
                if !preamble_lines.is_empty() {
                    if let Some(first) = preamble_lines.first() {
                        output.push_str(&format!("  Was: \"{}\"\n", first));
                    }
                    if preamble_lines.len() > 2 {
                        output.push_str(&format!("  [{} more lines]\n", preamble_lines.len() - 2));
                        if let Some(last) = preamble_lines.last() {
                            output.push_str(&format!("  Was: \"{}\"\n", last));
                        }
                    } else if preamble_lines.len() == 2 {
                        output.push_str(&format!("  Was: \"{}\"\n", preamble_lines[1]));
                    }
                }

                // Next section context (first heading after preamble)
                output.push('\n');
                if let Some(first_section) = doc.sections.first() {
                    output.push_str(&format_section_preview(&doc, first_section));
                } else {
                    output.push_str("  [end of document]\n");
                }

                if dry_run {
                    emit_verification(&output, dry_run);
                    return Ok(());
                }

                let new_source = format!(
                    "{}{}",
                    &source[..preamble_range.start],
                    &source[preamble_range.end..]
                );
                let normalised = normalise(&new_source);
                std::fs::write(file, &normalised).map_err(|e| {
                    MdeditError::FileError(format!("Cannot write '{}': {}", file, e))
                })?;
                emit_verification(&output, dry_run);
                return Ok(());
            } else {
                return Err(MdeditError::NoOp("No preamble to delete".to_string()));
            }
        }
    };

    // Delete the section's full range
    let delete_range = section.full_range.clone();

    // Metrics
    let deleted_content = &source[delete_range.clone()];
    let deleted_lines = deleted_content.trim().lines().count();
    let deleted_words = word_count(&source, &delete_range);

    // Warnings
    let mut warnings: Vec<String> = Vec::new();
    if !section.children.is_empty() {
        let child_headings: Vec<String> =
            section.children.iter().map(|c| c.full_heading()).collect();
        warnings.push(format!(
            "{} child section{} also deleted: {}",
            section.children.len(),
            if section.children.len() == 1 {
                ""
            } else {
                "s"
            },
            child_headings.join(", ")
        ));
    }

    // Build output
    let action_label = if dry_run { "WOULD DELETE" } else { "DELETED" };
    // Summary: DELETED: "## Appendix" (8 lines, 145 words removed)
    let summary = format!("({} lines, {} words removed)", deleted_lines, deleted_words);

    let mut output = String::new();
    if dry_run {
        output.push_str("DRY RUN \u{2014} no changes written\n\n");
    }
    output.push_str(&format!(
        "{}: \"{}\" {}\n",
        action_label,
        section.full_heading(),
        summary
    ));
    for w in &warnings {
        output.push_str(&format!("\u{26a0} {}\n", w));
    }

    // Neighborhood context
    output.push('\n');

    // Previous section
    if let Some(prev) = find_previous_section(&doc, section) {
        output.push_str(&format_section_preview(&doc, prev));
        output.push('\n');
    }

    // Deleted section with ✗ marker and (deleted) annotation
    let content_text = doc.slice(&section.own_content_range).trim();
    let content_lines: Vec<&str> = content_text
        .lines()
        .filter(|l| !l.trim().is_empty())
        .collect();

    output.push_str(&format!("\u{2717} {} (deleted)\n", section.full_heading()));
    if !content_lines.is_empty() {
        // First line with Was: prefix
        if let Some(first) = content_lines.first() {
            output.push_str(&format!("  Was: \"{}\"\n", first));
        }
        if content_lines.len() > 2 {
            output.push_str(&format!("  [{} more lines]\n", content_lines.len() - 2));
            // Last line with Was: prefix
            if let Some(last) = content_lines.last() {
                output.push_str(&format!("  Was: \"{}\"\n", last));
            }
        } else if content_lines.len() == 2 {
            output.push_str(&format!("  Was: \"{}\"\n", content_lines[1]));
        }
    }

    // Next section
    output.push('\n');
    if let Some(next) = find_next_section(&doc, section) {
        output.push_str(&format_section_preview(&doc, next));
    } else {
        output.push_str("  [end of document]\n");
    }

    if dry_run {
        emit_verification(&output, dry_run);
        return Ok(());
    }

    // Splice: remove the full range
    let new_source = format!(
        "{}{}",
        &source[..delete_range.start],
        &source[delete_range.end..]
    );

    let normalised = normalise(&new_source);

    std::fs::write(file, &normalised)
        .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

    emit_verification(&output, dry_run);
    Ok(())
}
