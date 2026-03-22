use crate::addressing::{resolve, ResolvedSection};
use crate::error::MdeditError;
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
    output.push_str(&format!(
        "{}: \"{}\" \u{2192} \"{}\"\n",
        action_label, old_heading, new_heading_line
    ));

    if dry_run {
        print!("{}", output);
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

    print!("{}", output);
    Ok(())
}
