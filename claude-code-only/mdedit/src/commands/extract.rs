use crate::addressing::{resolve, ResolvedSection};
use crate::counting::{self, section_own_word_count, section_word_count};
use crate::document::Section;
use crate::error::MdeditError;
use crate::output::{is_tty, emit_verification};
use crate::parser;

pub fn run(
    file: &str,
    section_query: &str,
    no_children: bool,
    to_file: Option<&str>,
) -> Result<(), MdeditError> {
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("Cannot read '{}': {}", file, e)))?;

    let doc = parser::parse(&source)
        .map_err(|e| MdeditError::FileError(format!("Parse error in '{}': {}", file, e)))?;

    let resolved = resolve(&doc, section_query).map_err(|e| match e {
        MdeditError::SectionNotFound { query, suggestions, .. } => {
            MdeditError::SectionNotFound { query, file: file.to_string(), suggestions }
        }
        MdeditError::AmbiguousMatch { query, matches, .. } => {
            MdeditError::AmbiguousMatch { query, file: file.to_string(), matches }
        }
        other => other,
    })?;

    match resolved {
        ResolvedSection::Preamble => {
            extract_preamble(&doc, to_file)
        }
        ResolvedSection::Found(section) => {
            extract_section(&doc, section, no_children, to_file)
        }
    }
}

fn extract_preamble(
    doc: &crate::document::Document,
    to_file: Option<&str>,
) -> Result<(), MdeditError> {
    let content = if let Some(range) = &doc.preamble {
        doc.slice(range).trim().to_string()
    } else {
        String::new()
    };

    if let Some(out_path) = to_file {
        std::fs::write(out_path, &content)
            .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", out_path, e)))?;
        let lines = content.lines().count();
        let words = counting::word_count(&content, &(0..content.len()));
        let confirmation = format!("EXTRACTED: \"_preamble\" ({} lines, {} words) → {}\n", lines, words, out_path);
        emit_verification(&confirmation, false);
    } else {
        if content.is_empty() {
            if is_tty() {
                println!("SECTION: \"_preamble\" — 0 words\n\n[no content]");
            } else {
                eprintln!("SECTION: \"_preamble\" — 0 words");
            }
        } else {
            let words = counting::word_count(&content, &(0..content.len()));
            if is_tty() {
                println!("SECTION: \"_preamble\" — {} words\n\n{}", words, content);
            } else {
                eprintln!("SECTION: \"_preamble\" — {} words", words);
                println!("{}", content);
            }
        }
    }

    Ok(())
}

fn extract_section(
    doc: &crate::document::Document,
    section: &Section,
    no_children: bool,
    to_file: Option<&str>,
) -> Result<(), MdeditError> {
    let heading = section.full_heading();
    let children_count = section.children.len();

    let (content, words, line_start, line_end) = if no_children {
        let own_content = doc.slice(&section.own_content_range).trim_end().to_string();
        let own_words = section_own_word_count(doc, section);
        let lstart = section.line_start;
        // line_end for own content: last line before children start
        let lend = if section.children.is_empty() {
            section.line_end
        } else {
            section.children[0].line_start - 1
        };
        (own_content, own_words, lstart, lend)
    } else {
        let full_content = doc.slice(&section.full_range);
        // Strip the heading line from the content for display
        let content_start = section.heading_range.end - section.full_range.start;
        let after_heading = full_content[content_start..].trim_end().to_string();
        let full_words = section_word_count(doc, section);
        (after_heading, full_words, section.line_start, section.line_end)
    };

    let is_empty = words == 0 && content.trim().is_empty();

    if let Some(out_path) = to_file {
        // Write raw content to file (no header)
        std::fs::write(out_path, &content)
            .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", out_path, e)))?;
        let line_count = content.lines().count();
        let confirmation = format!(
            "EXTRACTED: \"{}\" ({} lines, {} words) → {}\n",
            heading, line_count, words, out_path
        );
        emit_verification(&confirmation, false);
    } else {
        // Build the metadata header
        let header = if no_children && children_count > 0 {
            format!(
                "SECTION: \"{}\" — {} words, lines {}–{} ({} children excluded)",
                heading, words, line_start, line_end, children_count
            )
        } else if children_count > 0 {
            format!(
                "SECTION: \"{}\" — {} words, lines {}–{}, {} children",
                heading, words, line_start, line_end, children_count
            )
        } else {
            format!(
                "SECTION: \"{}\" — {} words, lines {}–{}",
                heading, words, line_start, line_end
            )
        };

        if is_tty() {
            println!("{}", header);
            println!();
            if is_empty {
                println!("[no content]");
            } else {
                println!("{}", content);
            }
        } else {
            // Piped: metadata header to stderr, raw content to stdout
            eprintln!("{}", header);
            if !is_empty {
                println!("{}", content);
            }
            // When empty and piped: nothing on stdout (empty string per spec)
        }
    }

    Ok(())
}
