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

    // 7. Word counts
    let prepended_words = word_count(&prepend_content_with_newline, &(0..prepend_content_with_newline.len()));

    // 8. Summary
    let summary = format!("(+{} words)", prepended_words);

    let action_label = if dry_run { "WOULD PREPEND" } else { "PREPENDED" };

    // 9. Format neighborhood output
    let neighborhood_output = format_neighborhood(
        &doc,
        section,
        action_label,
        &summary,
        &combined_content,
        &[],
        dry_run,
    );

    // 10. Build diff-like output showing prepended lines with + prefix
    let mut diff_output = String::new();
    for line in prepend_content_raw.lines() {
        diff_output.push_str(&format!("+ {}\n", line));
    }

    let output = format!("{}{}", neighborhood_output, diff_output);

    if dry_run {
        print!("{}", output);
        return Ok(());
    }

    // 11. Splice: source[..splice_point] + prepend_content + source[splice_point..]
    let new_source = format!(
        "{}{}{}",
        &source[..splice_point],
        prepend_content,
        &source[splice_point..]
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
