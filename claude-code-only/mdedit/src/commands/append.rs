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
                "append does not yet support _preamble".to_string(),
            ));
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
    // The own_content_range starts with a \n (blank line after heading)
    // So combined = existing + appended
    let combined_content = format!("{}{}", existing_content, append_content);

    // 7. Word counts
    let appended_words = word_count(&append_content, &(0..append_content.len()));

    // 8. Summary
    let summary = format!("(+{} words)", appended_words);

    let action_label = if dry_run { "WOULD APPEND" } else { "APPENDED" };

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

    // 10. Build diff-like output showing appended lines with + prefix
    let mut diff_output = String::new();
    for line in append_content_raw.lines() {
        diff_output.push_str(&format!("+ {}\n", line));
    }

    let output = format!("{}{}", neighborhood_output, diff_output);

    if dry_run {
        print!("{}", output);
        return Ok(());
    }

    // 11. Splice: source[..splice_point] + append_content + source[splice_point..]
    let new_source = format!(
        "{}{}{}",
        &source[..splice_point],
        append_content,
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
