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
    };

    // 3. Resolve new content to append
    let append_content_raw = resolve_content(content, from_file)?;

    // Ensure trailing newline on the appended content
    let append_content = format!(
        "{}{}",
        append_content_raw,
        if append_content_raw.ends_with('\n') { "" } else { "\n" }
    );

    // 4. The splice point for append is own_content_range.end
    let splice_point = section.own_content_range.end;

    // 5. Get existing own content for display
    let existing_content = &source[section.own_content_range.clone()];

    // 6. Build combined content for neighborhood display
    let combined_content = format!("{}{}", existing_content, append_content);

    // 7. Line counts for summary
    let existing_lines = existing_content.trim().lines().count();
    let appended_lines = append_content_raw.lines().count();
    let combined_lines = combined_content.trim().lines().count();

    // 8. Build output
    let action_label = if dry_run { "WOULD APPEND" } else { "APPENDED" };

    let mut output = String::new();
    if dry_run {
        output.push_str("DRY RUN \u{2014} no changes written\n\n");
    }

    // Summary line: APPENDED: N lines to "## Section" (was M lines → now P lines)
    output.push_str(&format!(
        "{}: {} lines to \"{}\" (was {} lines \u{2192} now {} lines)\n",
        action_label, appended_lines, section.full_heading(), existing_lines, combined_lines
    ));

    output.push('\n');

    // Previous section
    if let Some(prev) = find_previous_section(&doc, section) {
        output.push_str(&format_section_preview(&doc, prev));
        output.push('\n');
    }

    // Target section with → marker
    output.push_str(&format!("\u{2192} {}\n", section.full_heading()));

    // Show tail of existing content
    let existing_text = doc.slice(&section.own_content_range).trim();
    let existing_non_empty: Vec<&str> = existing_text.lines().filter(|l| !l.trim().is_empty()).collect();
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

    // Appended lines with + prefix (inside target section block)
    for line in append_content_raw.lines() {
        output.push_str(&format!("+ {}\n", line));
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

    // 9. Splice: source[..splice_point] + append_content + source[splice_point..]
    let new_source = format!(
        "{}{}{}",
        &source[..splice_point],
        append_content,
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
