use crate::addressing::{resolve, ResolvedSection};
use crate::content::resolve_content;
use crate::error::MdeditError;
use crate::output::{find_next_section, find_previous_section, format_section_preview};
use crate::parser;
use crate::whitespace::normalise;

pub fn run(
    file: &str,
    section_query: &str,
    content: Option<&str>,
    from_file: Option<&str>,
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
                "prepend does not yet support _preamble".to_string(),
            ));
        }
    };

    // 3. Resolve new content to prepend
    let prepend_content_raw = resolve_content(content, from_file)?;

    // Ensure trailing newline on the prepended content
    let prepend_content_with_newline = format!(
        "{}{}",
        prepend_content_raw,
        if prepend_content_raw.ends_with('\n') { "" } else { "\n" }
    );

    // 4. CRITICAL: Splice point is own_content_range.start.
    // own_content_range.start sits right after the heading's trailing newline —
    // the blank line separator between heading and content is INSIDE the range.
    // So we must prepend \n to restore the heading separator.
    let splice_point = section.own_content_range.start;

    // Build the content to insert: \n + prepended content
    // This adds a blank line before the prepended content; the doubled separator
    // (original \n at own_content_range.start + this new \n) is corrected by normalise()
    let prepend_content = format!("\n{}", prepend_content_with_newline);

    // 5. Get existing own content for display
    let existing_content = &source[section.own_content_range.clone()];

    // 6. Build combined content for neighborhood display
    // Combined = new blank line + prepended + existing (minus the leading \n which is the separator)
    let combined_content = format!("{}{}", prepend_content, existing_content.trim_start_matches('\n'));

    // 7. Line counts for summary
    let existing_lines = existing_content.trim().lines().count();
    let prepended_lines = prepend_content_raw.lines().count();
    let combined_lines = combined_content.trim().lines().count();

    // 8. Build output
    let action_label = if dry_run { "WOULD PREPEND" } else { "PREPENDED" };

    let mut output = String::new();
    if dry_run {
        output.push_str("DRY RUN \u{2014} no changes written\n\n");
    }

    // Summary line: PREPENDED: N lines to "## Section" (was M lines → now P lines)
    output.push_str(&format!(
        "{}: {} lines to \"{}\" (was {} lines \u{2192} now {} lines)\n",
        action_label, prepended_lines, section.full_heading(), existing_lines, combined_lines
    ));

    output.push('\n');

    // Previous section
    if let Some(prev) = find_previous_section(&doc, section) {
        output.push_str(&format_section_preview(&doc, prev));
        output.push('\n');
    }

    // Target section with → marker
    output.push_str(&format!("\u{2192} {}\n", section.full_heading()));

    // Prepended lines with + prefix (right after heading)
    for line in prepend_content_raw.lines() {
        output.push_str(&format!("+ {}\n", line));
    }

    // Show head of existing content
    let existing_text = doc.slice(&section.own_content_range).trim();
    let existing_non_empty: Vec<&str> = existing_text.lines().filter(|l| !l.trim().is_empty()).collect();
    if let Some(first) = existing_non_empty.first() {
        output.push_str(&format!("  {}\n", first));
    }
    if existing_non_empty.len() > 1 {
        output.push_str(&format!("  [{} more lines]\n", existing_non_empty.len() - 1));
    }

    // Next section
    output.push('\n');
    if let Some(next) = find_next_section(&doc, section) {
        output.push_str(&format_section_preview(&doc, next));
    } else {
        output.push_str("  [end of document]\n");
    }

    if dry_run {
        print!("{}", output);
        return Ok(());
    }

    // 9. Splice: source[..splice_point] + prepend_content + source[splice_point..]
    let new_source = format!(
        "{}{}{}",
        &source[..splice_point],
        prepend_content,
        &source[splice_point..]
    );

    // 10. Normalise whitespace
    let normalised = normalise(&new_source);

    // 11. Write the file
    std::fs::write(file, &normalised)
        .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

    // 12. Print the formatted output
    print!("{}", output);

    Ok(())
}
