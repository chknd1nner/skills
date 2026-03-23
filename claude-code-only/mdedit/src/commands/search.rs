use crate::error::MdeditError;
use crate::parser;

pub fn run(file: &str, query: &str, case_sensitive: bool) -> Result<(), MdeditError> {
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("Cannot read '{}': {}", file, e)))?;

    let doc = parser::parse(&source)
        .map_err(|e| MdeditError::FileError(format!("Parse error in '{}': {}", file, e)))?;

    // Collect all sections with matches
    let all_sections = doc.all_sections();
    let mut total_matches = 0;
    let mut section_results: Vec<SectionResult> = Vec::new();

    let query_lower = if !case_sensitive {
        query.to_lowercase()
    } else {
        query.to_string()
    };

    for (section, _parent) in &all_sections {
        let mut line_matches: Vec<LineMatch> = Vec::new();

        // Search heading text
        let heading_line = section.full_heading();
        let heading_line_num = section.line_start;
        if let Some(matches) = find_matches_in_line(&heading_line, &query_lower, case_sensitive) {
            for highlighted in matches {
                line_matches.push(LineMatch {
                    line_num: heading_line_num,
                    highlighted,
                });
            }
        }

        // Search own_content line by line
        let own_content = doc.slice(&section.own_content_range);
        let content_start_byte = section.own_content_range.start;
        // Compute line number of first byte of own_content
        let content_start_line = doc.byte_to_line(content_start_byte);

        let mut byte_offset = 0usize;
        for (i, line) in own_content.lines().enumerate() {
            // Compute actual line number: content_start_line + i, but we need to handle
            // the first line carefully since byte_to_line gives us the line of the first byte.
            // own_content starts right after the heading newline, so we count newlines from start.
            let line_num = {
                // Count newlines before byte_offset in own_content
                let preceding = &own_content[..byte_offset];
                let newlines = preceding.matches('\n').count();
                content_start_line + newlines
            };

            if let Some(matches) = find_matches_in_line(line, &query_lower, case_sensitive) {
                for highlighted in matches {
                    line_matches.push(LineMatch {
                        line_num,
                        highlighted,
                    });
                }
            }

            byte_offset += line.len() + 1; // +1 for '\n'
            let _ = i; // suppress unused warning
        }

        if !line_matches.is_empty() {
            total_matches += line_matches.len();
            section_results.push(SectionResult {
                heading: section.full_heading(),
                matches: line_matches,
            });
        }
    }

    let section_count = section_results.len();

    // Print header
    let section_word = if section_count == 1 { "section" } else { "sections" };
    let match_word = if total_matches == 1 { "match" } else { "matches" };
    println!(
        "SEARCH: \"{}\" — {} {} in {} {}",
        query, total_matches, match_word, section_count, section_word
    );

    if total_matches == 0 {
        return Ok(());
    }

    println!();
    for sr in &section_results {
        let match_count = sr.matches.len();
        let m_word = if match_count == 1 { "match" } else { "matches" };
        println!("  {} ({} {})", sr.heading, match_count, m_word);
        for lm in &sr.matches {
            println!("    Line {}: {}", lm.line_num, lm.highlighted);
        }
        println!();
    }

    Ok(())
}

struct SectionResult {
    heading: String,
    matches: Vec<LineMatch>,
}

struct LineMatch {
    line_num: usize,
    highlighted: String,
}

/// Find all matches of `query_lower` in `line` (case-insensitive or sensitive).
/// Returns Some(Vec<highlighted_line>) — one entry per match occurrence,
/// but we actually want to return the line with ALL occurrences highlighted as one string.
/// Returns None if no matches found.
fn find_matches_in_line(line: &str, query_lower: &str, case_sensitive: bool) -> Option<Vec<String>> {
    let search_in = if !case_sensitive {
        line.to_lowercase()
    } else {
        line.to_string()
    };

    if !search_in.contains(&query_lower) {
        return None;
    }

    // Build highlighted version: replace all occurrences with |original_text|
    let highlighted = highlight_matches(line, query_lower, case_sensitive);
    Some(vec![highlighted])
}

/// Highlight all occurrences of query in line with pipe delimiters.
/// Preserves original casing of the matched text.
fn highlight_matches(line: &str, query_lower: &str, case_sensitive: bool) -> String {
    let mut result = String::new();
    let mut remaining = line;

    while !remaining.is_empty() {
        let search_in = if !case_sensitive {
            remaining.to_lowercase()
        } else {
            remaining.to_string()
        };

        if let Some(pos) = search_in.find(&query_lower) {
            // Find char boundary: pos is a byte index in search_in which corresponds
            // 1:1 to remaining (both are same length)
            result.push_str(&remaining[..pos]);
            let matched = &remaining[pos..pos + query_lower.len()];
            result.push('|');
            result.push_str(matched);
            result.push('|');
            remaining = &remaining[pos + query_lower.len()..];
        } else {
            result.push_str(remaining);
            break;
        }
    }

    result
}
