use crate::counting::section_word_count;
use crate::document::{Document, Section};
use crate::error::MdeditError;
use crate::parser;

pub fn run(file: &str, max_depth: Option<u8>) -> Result<(), MdeditError> {
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("Cannot read '{}': {}", file, e)))?;

    let doc = parser::parse(&source)
        .map_err(|e| MdeditError::FileError(format!("Parse error in '{}': {}", file, e)))?;

    print_outline(&doc, max_depth);
    Ok(())
}

fn print_outline(doc: &Document, max_depth: Option<u8>) {
    for section in &doc.sections {
        print_section(doc, section, 0, max_depth);
    }
}

fn print_section(doc: &Document, section: &Section, depth: usize, max_depth: Option<u8>) {
    // Check max_depth — level is 1-indexed, depth is 0-indexed indentation
    if let Some(max) = max_depth {
        if section.level > max {
            return;
        }
    }

    let indent = "  ".repeat(depth);
    let heading = section.full_heading();
    let words = section_word_count(doc, section);
    let line_start = section.line_start;
    let line_end = section.line_end;

    // Determine if section is the root/H1 — show total doc stats differently
    let empty_flag = if words == 0 { " ⚠ empty" } else { "" };

    if depth == 0 && section.level == 1 {
        // Root H1: show total document word count and lines
        let total_lines = doc.source.lines().count();
        println!(
            "{}{} — {} words, {} lines{}",
            indent, heading, words, total_lines, empty_flag
        );
        println!(); // blank line after H1 per spec
    } else {
        // Other sections: show word count and line range
        println!(
            "{}{} — {} words (lines {}–{}){}",
            indent, heading, words, line_start, line_end, empty_flag
        );
    }

    // Recurse into children
    for child in &section.children {
        print_section(doc, child, depth + 1, max_depth);
    }
}
