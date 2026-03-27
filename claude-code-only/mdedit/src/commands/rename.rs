use crate::addressing::{resolve, ResolvedSection};
use crate::error::MdeditError;
use crate::output::{emit_verification, find_next_section, find_previous_section, format_section_preview};
use crate::parser;
use crate::whitespace::normalise;

pub fn run(
    file: &str,
    section_query: &str,
    new_name: &str,
    dry_run: bool,
) -> Result<(), MdeditError> {
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
            return Err(MdeditError::InvalidOperation(
                "rename is not valid for _preamble (no heading to rename)".to_string(),
            ));
        }
    };

    // Check for no-op
    if section.heading_text == new_name {
        return Err(MdeditError::NoOp(format!(
            "Heading is already \"{}\"",
            new_name
        )));
    }

    let old_heading = section.full_heading();
    let new_heading_line = format!("{} {}", "#".repeat(section.level as usize), new_name);

    // Build output
    let action_label = if dry_run { "WOULD RENAME" } else { "RENAMED" };
    let mut output = String::new();
    if dry_run {
        output.push_str("DRY RUN \u{2014} no changes written\n\n");
    }

    // Summary: RENAMED: "## Old" → "## New" (line N)
    output.push_str(&format!(
        "{}: \"{}\" \u{2192} \"{}\" (line {})\n",
        action_label, old_heading, new_heading_line, section.line_start
    ));

    output.push('\n');

    // Previous section
    if let Some(prev) = find_previous_section(&doc, section) {
        output.push_str(&format_section_preview(&doc, prev));
        output.push('\n');
    }

    // Target section with → marker — show with new heading
    output.push_str(&format!("\u{2192} {}\n", new_heading_line));
    let content = doc.slice(&section.own_content_range).trim();
    let non_empty: Vec<&str> = content.lines().filter(|l| !l.trim().is_empty()).collect();
    if let Some(first) = non_empty.first() {
        output.push_str(&format!("  {}\n", first));
    }
    if non_empty.len() > 2 {
        output.push_str(&format!("  [{} more lines]\n", non_empty.len() - 2));
        if let Some(last) = non_empty.last() {
            output.push_str(&format!("  {}\n", last));
        }
    } else if non_empty.len() == 2 {
        output.push_str(&format!("  {}\n", non_empty[1]));
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

    // Splice: replace heading_range with new heading line
    // heading_range includes the trailing \n, so we must include \n in the replacement
    let new_source = format!(
        "{}{}\n{}",
        &source[..section.heading_range.start],
        new_heading_line,
        &source[section.heading_range.end..]
    );

    let normalised = normalise(&new_source);

    std::fs::write(file, &normalised)
        .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

    emit_verification(&output, dry_run);
    Ok(())
}
