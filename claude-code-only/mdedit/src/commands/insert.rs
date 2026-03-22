use crate::addressing::{resolve, ResolvedSection};
use crate::content::resolve_content;
use crate::error::MdeditError;
use crate::parser;
use crate::output::format_section_preview;
use crate::whitespace::normalise;

pub fn run(
    file: &str,
    after: Option<&str>,
    before: Option<&str>,
    heading: &str,
    content: Option<&str>,
    from_file: Option<&str>,
    dry_run: bool,
) -> Result<(), MdeditError> {
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("Cannot read '{}': {}", file, e)))?;

    let doc = parser::parse(&source)
        .map_err(|e| MdeditError::FileError(format!("Parse error in '{}': {}", file, e)))?;

    // Parse heading to get level and text
    let (new_level, new_text) = parse_heading(heading);
    let full_heading = format!("{} {}", "#".repeat(new_level as usize), &new_text);

    // Resolve content (optional for insert)
    let section_content = match resolve_content(content, from_file) {
        Ok(c) => Some(c),
        Err(MdeditError::ContentError(_)) => None, // no content is fine for insert
        Err(e) => return Err(e),
    };

    // Build the new section text
    let new_section_text = if let Some(ref c) = section_content {
        let content_with_newline = if c.ends_with('\n') { c.clone() } else { format!("{}\n", c) };
        format!("{}\n\n{}", full_heading, content_with_newline)
    } else {
        format!("{}\n", full_heading)
    };

    // Determine splice point, anchor info for summary and neighborhood
    let (splice_point, anchor_level, anchor_heading, is_after) = if let Some(after_query) = after {
        let resolved = resolve(&doc, after_query).map_err(|e| enrich_error(e, file))?;
        match resolved {
            ResolvedSection::Found(s) => {
                let heading = s.full_heading();
                (s.full_range.end, Some(s.level), Some(heading), true)
            }
            ResolvedSection::Preamble => {
                // Insert after preamble = before first section
                let point = if let Some(first) = doc.sections.first() {
                    first.full_range.start
                } else if let Some(ref p) = doc.preamble {
                    p.end
                } else if let Some(ref fm) = doc.frontmatter {
                    fm.end
                } else {
                    0
                };
                (point, None, Some("_preamble".to_string()), true)
            }
        }
    } else if let Some(before_query) = before {
        if before_query == "_preamble" {
            return Err(MdeditError::InvalidOperation(
                "insert --before _preamble is not valid; use prepend to _preamble instead"
                    .to_string(),
            ));
        }
        let resolved = resolve(&doc, before_query).map_err(|e| enrich_error(e, file))?;
        match resolved {
            ResolvedSection::Found(s) => {
                let heading = s.full_heading();
                (s.full_range.start, Some(s.level), Some(heading), false)
            }
            ResolvedSection::Preamble => {
                return Err(MdeditError::InvalidOperation(
                    "insert --before _preamble is not valid; use prepend to _preamble instead"
                        .to_string(),
                ));
            }
        }
    } else {
        return Err(MdeditError::ContentError(
            "Either --after or --before is required".to_string(),
        ));
    };

    // Warnings
    let mut warnings: Vec<String> = Vec::new();
    if let Some(anchor_lvl) = anchor_level {
        if new_level != anchor_lvl {
            warnings.push(format!(
                "Inserting H{} next to H{} section \u{2014} heading level mismatch",
                new_level, anchor_lvl
            ));
        }
    }

    // Line count of inserted content
    let content_lines = section_content
        .as_ref()
        .map(|c| c.lines().count())
        .unwrap_or(0);

    // Summary: INSERTED: "## Name" (N lines) after "## Anchor"
    let action_label = if dry_run { "WOULD INSERT" } else { "INSERTED" };
    let position_text = if is_after { "after" } else { "before" };
    let anchor_text = anchor_heading.as_deref().unwrap_or("unknown");

    // Build output
    let mut output = String::new();
    if dry_run {
        output.push_str("DRY RUN \u{2014} no changes written\n\n");
    }
    output.push_str(&format!(
        "{}: \"{}\" ({} lines) {} \"{}\"\n",
        action_label, full_heading, content_lines, position_text, anchor_text
    ));
    for w in &warnings {
        output.push_str(&format!("\u{26a0} {}\n", w));
    }

    output.push('\n');

    // Neighborhood context: find previous/next sections relative to the anchor
    // For --after: prev = anchor, target = new section, next = section after anchor
    // For --before: prev = section before anchor, target = new section, next = anchor
    let all_sections = doc.all_sections();
    if is_after {
        // Previous section = the anchor (show it as context)
        if let Some(anchor_ref) = anchor_heading.as_deref() {
            if anchor_ref == "_preamble" {
                // No previous section to show for preamble
            } else {
                // Find the anchor section in the document
                if let Some((anchor_sec, _)) = all_sections.iter().find(|(s, _)| s.full_heading() == anchor_ref) {
                    output.push_str(&format_section_preview(&doc, anchor_sec));
                    output.push('\n');
                }
            }
        }

        // Target: new section
        output.push_str(&format!("\u{2192} {}\n", full_heading));
        if let Some(ref c) = section_content {
            let non_empty: Vec<&str> = c.lines().filter(|l| !l.trim().is_empty()).collect();
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
        }

        // Next section = section after the anchor in original doc
        output.push('\n');
        if let Some(anchor_ref) = anchor_heading.as_deref() {
            if anchor_ref == "_preamble" {
                if let Some(first) = doc.sections.first() {
                    output.push_str(&format_section_preview(&doc, first));
                } else {
                    output.push_str("  [end of document]\n");
                }
            } else {
                let mut found_next = false;
                for i in 0..all_sections.len() {
                    if all_sections[i].0.full_heading() == anchor_ref {
                        if i + 1 < all_sections.len() {
                            output.push_str(&format_section_preview(&doc, all_sections[i + 1].0));
                            found_next = true;
                        }
                        break;
                    }
                }
                if !found_next {
                    output.push_str("  [end of document]\n");
                }
            }
        } else {
            output.push_str("  [end of document]\n");
        }
    } else {
        // --before: prev = section before anchor, target = new, next = anchor
        if let Some(anchor_ref) = anchor_heading.as_deref() {
            // Find the section before the anchor
            for i in 0..all_sections.len() {
                if all_sections[i].0.full_heading() == anchor_ref {
                    if i > 0 {
                        output.push_str(&format_section_preview(&doc, all_sections[i - 1].0));
                        output.push('\n');
                    }
                    break;
                }
            }
        }

        // Target: new section
        output.push_str(&format!("\u{2192} {}\n", full_heading));
        if let Some(ref c) = section_content {
            let non_empty: Vec<&str> = c.lines().filter(|l| !l.trim().is_empty()).collect();
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
        }

        // Next section = the anchor
        output.push('\n');
        if let Some(anchor_ref) = anchor_heading.as_deref() {
            if let Some((anchor_sec, _)) = all_sections.iter().find(|(s, _)| s.full_heading() == anchor_ref) {
                output.push_str(&format_section_preview(&doc, anchor_sec));
            }
        }
    }

    if dry_run {
        print!("{}", output);
        return Ok(());
    }

    // Splice
    let new_source = format!(
        "{}{}{}",
        &source[..splice_point],
        new_section_text,
        &source[splice_point..]
    );

    let normalised = normalise(&new_source);

    std::fs::write(file, &normalised)
        .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

    print!("{}", output);
    Ok(())
}

/// Parse a heading string like "## Name" into (level, text).
/// If no # prefix, defaults to H2.
fn parse_heading(heading: &str) -> (u8, String) {
    if heading.starts_with('#') {
        let hashes = heading.chars().take_while(|&c| c == '#').count() as u8;
        let text = heading[hashes as usize..].trim().to_string();
        (hashes, text)
    } else {
        // No level prefix — default to H2
        (2, heading.to_string())
    }
}

fn enrich_error(e: MdeditError, file: &str) -> MdeditError {
    match e {
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
    }
}
