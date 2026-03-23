use crate::counting::section_word_count;
use crate::document::{Document, Section};
use crate::error::MdeditError;
use crate::parser;

pub fn run(file: &str) -> Result<(), MdeditError> {
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("Cannot read '{}': {}", file, e)))?;

    let doc = parser::parse(&source)
        .map_err(|e| MdeditError::FileError(format!("Parse error in '{}': {}", file, e)))?;

    // Compute total document word count and line count
    let total_words: usize = doc.sections.iter()
        .map(|s| section_word_count(&doc, s))
        .sum();
    let total_lines = doc.source.lines().count();
    let total_sections = doc.all_sections().len();

    // Extract filename from path
    let filename = std::path::Path::new(file)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(file);

    println!(
        "STATS: {} — {} words, {} lines, {} sections",
        filename, total_words, total_lines, total_sections
    );
    println!();

    // Find the top-level sections (direct children of doc, not H1 if it's a single root)
    // Per spec: percentages only for top-level children.
    // We interpret "top-level" as the sections in doc.sections (which may be H1 or H2 depending on doc structure).
    // If the document has a single H1 root, we show its children as the top-level items.
    // To match the spec output, we show sections from doc.sections onward.

    // Determine max word count among top-level sections for "← largest" annotation
    // "Top-level" here means the sections in doc.sections
    let top_level_sections = &doc.sections;

    if top_level_sections.is_empty() {
        return Ok(());
    }

    let max_top_words = top_level_sections.iter()
        .map(|s| section_word_count(&doc, s))
        .max()
        .unwrap_or(0);

    for section in top_level_sections {
        print_stats_section(&doc, section, 0, total_words, max_top_words, true);
    }

    Ok(())
}

fn print_stats_section(
    doc: &Document,
    section: &Section,
    depth: usize,
    total_words: usize,
    max_top_words: usize,
    is_top_level: bool,
) {
    let indent = "  ".repeat(depth + 1); // +1 for leading indent per spec format
    let words = section_word_count(doc, section);
    let heading = section.full_heading();

    let annotation = if words == 0 {
        " ← empty".to_string()
    } else if is_top_level && words == max_top_words && max_top_words > 0 {
        " ← largest".to_string()
    } else {
        String::new()
    };

    if is_top_level && total_words > 0 {
        let pct = ((words as f64 / total_words as f64) * 100.0).round() as usize;
        println!("{}{} — {} words ({}%){}", indent, heading, words, pct, annotation);
    } else if is_top_level {
        println!("{}{} — {} words{}", indent, heading, words, annotation);
    } else {
        // Child sections: no percentage
        let child_annotation = if words == 0 { " ← empty" } else { "" };
        println!("{}{} — {} words{}", indent, heading, words, child_annotation);
    }

    // Recurse into children — they are not top-level
    for child in &section.children {
        print_stats_section(doc, child, depth + 1, total_words, 0, false);
    }
}
