use crate::document::{Document, Section};

/// Count words in a byte range of the source.
///
/// Rules (per spec):
/// - Blank lines do not contribute to word counts.
/// - Heading lines (lines starting with `#`) do not contribute to word counts.
/// - Code fence delimiter lines (` ``` ` or `~~~`) do not contribute to word counts.
/// - Content inside code fences counts as words.
/// - "Words" are whitespace-delimited tokens.
pub fn word_count(source: &str, range: &std::ops::Range<usize>) -> usize {
    let text = &source[range.start..range.end];
    let mut in_code_fence = false;
    let mut fence_marker: Option<&str> = None;
    let mut count = 0;

    for line in text.lines() {
        let trimmed = line.trim();

        if in_code_fence {
            // Check if this line closes the fence
            if let Some(marker) = fence_marker {
                if trimmed.starts_with(marker) && trimmed.trim_start_matches(marker).trim().is_empty() {
                    // Closing fence delimiter — skip the line, exit fence mode
                    in_code_fence = false;
                    fence_marker = None;
                    continue;
                }
            }
            // Inside code fence: count content words
            count += line.split_whitespace().count();
        } else {
            // Check for opening code fence
            if trimmed.starts_with("```") || trimmed.starts_with("~~~") {
                in_code_fence = true;
                fence_marker = if trimmed.starts_with("```") { Some("```") } else { Some("~~~") };
                // Opening fence delimiter itself is not counted
                continue;
            }
            // Skip blank lines
            if trimmed.is_empty() {
                continue;
            }
            // Skip heading lines
            if trimmed.starts_with('#') {
                continue;
            }
            // Regular content line
            count += line.split_whitespace().count();
        }
    }

    count
}

/// Count words for a section including all children (full_range)
pub fn section_word_count(doc: &Document, section: &Section) -> usize {
    word_count(&doc.source, &section.full_range)
}

/// Count words for a section's own content only (excluding children)
pub fn section_own_word_count(doc: &Document, section: &Section) -> usize {
    word_count(&doc.source, &section.own_content_range)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser;

    #[test]
    fn word_count_simple_section() {
        let doc = parser::parse("# Title\n\n## Section\n\nOne two three.\nFour five.\n").unwrap();
        let section = &doc.sections[0].children[0];
        // "One two three." = 3 words, "Four five." = 2 words = 5 total
        assert_eq!(section_word_count(&doc, section), 5);
    }

    #[test]
    fn word_count_excludes_heading_line() {
        let doc = parser::parse("# Title\n\n## Section Name\n\nContent here.\n").unwrap();
        let section = &doc.sections[0].children[0];
        // Only "Content here." = 2 words (heading excluded)
        assert_eq!(section_word_count(&doc, section), 2);
    }

    #[test]
    fn word_count_excludes_blank_lines() {
        let doc = parser::parse("# T\n\n## S\n\nLine one.\n\nLine two.\n").unwrap();
        let section = &doc.sections[0].children[0];
        // "Line one." + "Line two." = 4 words
        assert_eq!(section_word_count(&doc, section), 4);
    }

    #[test]
    fn word_count_includes_code_fence_content() {
        let source = "# T\n\n## S\n\n```\ncode word\n```\n";
        let doc = parser::parse(source).unwrap();
        let section = &doc.sections[0].children[0];
        // "code word" = 2 words (code fence content counts, fence delimiters do not)
        assert_eq!(section_word_count(&doc, section), 2);
    }

    #[test]
    fn word_count_with_children() {
        let doc = parser::parse("# T\n\n## Parent\n\nParent text.\n\n### Child\n\nChild text.\n").unwrap();
        let parent = &doc.sections[0].children[0];
        // "Parent text." = 2, "Child text." = 2, total = 4
        assert_eq!(section_word_count(&doc, parent), 4);
        // Own only = 2
        assert_eq!(section_own_word_count(&doc, parent), 2);
    }
}
