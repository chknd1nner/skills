use crate::document::{Document, Section};
use std::ops::Range;

/// Parse a markdown string into a Document
pub fn parse(source: &str) -> Result<Document, String> {
    let mut ts_parser = tree_sitter::Parser::new();
    ts_parser
        .set_language(&tree_sitter_md::LANGUAGE.into())
        .map_err(|e| format!("Failed to set language: {e}"))?;

    let tree = ts_parser
        .parse(source.as_bytes(), None)
        .ok_or("tree-sitter parse returned None")?;

    let root = tree.root_node();

    let mut frontmatter: Option<Range<usize>> = None;
    let mut preamble_start: Option<usize> = None;
    let mut preamble_end: Option<usize> = None;
    let mut sections: Vec<Section> = Vec::new();

    let mut cursor = root.walk();
    for child in root.children(&mut cursor) {
        match child.kind() {
            "minus_metadata" => {
                frontmatter = Some(child.start_byte()..child.end_byte());
            }
            "section" => {
                // A section node that contains an atx_heading is a real section.
                // A section node without an atx_heading is preamble content
                // (tree-sitter-md wraps bare paragraphs in section nodes too).
                if section_has_heading(child) {
                    let section = build_section(child, source)?;
                    sections.push(section);
                } else {
                    // Treat as preamble content (if no real sections seen yet)
                    if sections.is_empty() {
                        let text = &source[child.start_byte()..child.end_byte()];
                        if !text.trim().is_empty() {
                            if preamble_start.is_none() {
                                // Skip leading newline that belongs to frontmatter separator
                                let trimmed_start = child.start_byte()
                                    + source[child.start_byte()..]
                                        .chars()
                                        .take_while(|c| *c == '\n')
                                        .map(|c| c.len_utf8())
                                        .sum::<usize>();
                                preamble_start = Some(trimmed_start);
                            }
                            preamble_end = Some(child.end_byte());
                        }
                    }
                }
            }
            _ => {
                // Content before the first section — preamble
                if sections.is_empty() {
                    // Don't include empty/whitespace-only nodes in preamble
                    let text = &source[child.start_byte()..child.end_byte()];
                    if !text.trim().is_empty() {
                        if preamble_start.is_none() {
                            preamble_start = Some(child.start_byte());
                        }
                        preamble_end = Some(child.end_byte());
                    }
                }
            }
        }
    }

    let preamble = match (preamble_start, preamble_end) {
        (Some(s), Some(e)) => Some(s..e),
        _ => None,
    };

    Ok(Document {
        source: source.to_string(),
        frontmatter,
        preamble,
        sections,
    })
}

/// Returns true if the section node contains an atx_heading child
fn section_has_heading(node: tree_sitter::Node) -> bool {
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        if child.kind() == "atx_heading" {
            return true;
        }
    }
    false
}

fn build_section(node: tree_sitter::Node, source: &str) -> Result<Section, String> {
    let full_start = node.start_byte();
    let full_end = node.end_byte();
    let line_start = node.start_position().row + 1;
    let line_end = source[..full_end].matches('\n').count();

    let mut heading_text = String::new();
    let mut level: u8 = 1;
    let mut heading_range: Range<usize> = full_start..full_start;
    let mut own_content_end = full_end;
    let mut children: Vec<Section> = Vec::new();

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        match child.kind() {
            "atx_heading" => {
                heading_range = child.start_byte()..child.end_byte();
                level = extract_heading_level(child, source)?;
                heading_text = extract_heading_text(child, source);
            }
            "section" => {
                if children.is_empty() {
                    // own content ends where child sections begin
                    own_content_end = child.start_byte();
                }
                let child_section = build_section(child, source)?;
                children.push(child_section);
            }
            _ => {}
        }
    }

    let own_content_range = heading_range.end..own_content_end;

    Ok(Section {
        heading_text,
        level,
        heading_range,
        own_content_range,
        full_range: full_start..full_end,
        line_start,
        line_end,
        children,
    })
}

fn extract_heading_level(heading_node: tree_sitter::Node, source: &str) -> Result<u8, String> {
    let mut cursor = heading_node.walk();
    for child in heading_node.children(&mut cursor) {
        let level = match child.kind() {
            "atx_h1_marker" => 1,
            "atx_h2_marker" => 2,
            "atx_h3_marker" => 3,
            "atx_h4_marker" => 4,
            "atx_h5_marker" => 5,
            "atx_h6_marker" => 6,
            _ => continue,
        };
        return Ok(level);
    }
    // Fallback: count # characters
    let text = &source[heading_node.start_byte()..heading_node.end_byte()];
    let count = text.chars().take_while(|&c| c == '#').count();
    Ok(count.min(6) as u8)
}

fn extract_heading_text(heading_node: tree_sitter::Node, source: &str) -> String {
    let mut cursor = heading_node.walk();
    for child in heading_node.children(&mut cursor) {
        match child.kind() {
            "inline" | "heading_content" => {
                return source[child.start_byte()..child.end_byte()]
                    .trim()
                    .to_string();
            }
            _ => {}
        }
    }
    // Fallback: strip leading # and trim
    let text = &source[heading_node.start_byte()..heading_node.end_byte()];
    text.trim_start_matches('#').trim().trim_end_matches('\n').trim().to_string()
}

#[allow(dead_code)]
fn debug_tree(node: tree_sitter::Node, source: &str, depth: usize) {
    let indent = "  ".repeat(depth);
    let end = (node.start_byte() + 50).min(node.end_byte());
    let text_preview = &source[node.start_byte()..end];
    eprintln!(
        "{}{}  [{}-{}]  {:?}",
        indent,
        node.kind(),
        node.start_byte(),
        node.end_byte(),
        text_preview.replace('\n', "\\n")
    );
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        debug_tree(child, source, depth + 1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_simple_document() {
        let source = std::fs::read_to_string("tests/fixtures/simple.md").unwrap();
        let doc = parse(&source).unwrap();

        assert!(doc.frontmatter.is_none());
        assert!(doc.preamble.is_none());

        // H1 wraps everything in one top-level section
        assert_eq!(doc.sections.len(), 1);
        let root = &doc.sections[0];
        assert_eq!(root.heading_text, "My Document");
        assert_eq!(root.level, 1);

        // Three H2 children
        assert_eq!(root.children.len(), 3);
        assert_eq!(root.children[0].heading_text, "Introduction");
        assert_eq!(root.children[0].level, 2);
        assert_eq!(root.children[1].heading_text, "Background");
        assert_eq!(root.children[2].heading_text, "Conclusion");
        assert!(root.children[0].children.is_empty());
    }

    #[test]
    fn parse_nested_document() {
        let source = std::fs::read_to_string("tests/fixtures/nested.md").unwrap();
        let doc = parse(&source).unwrap();

        let root = &doc.sections[0];
        assert_eq!(root.heading_text, "Research Paper");
        assert_eq!(root.children.len(), 5);

        let bg = &root.children[1];
        assert_eq!(bg.heading_text, "Background");
        assert_eq!(bg.children.len(), 2);
        assert_eq!(bg.children[0].heading_text, "Prior Work");
        assert_eq!(bg.children[1].heading_text, "Definitions");

        let methods = &root.children[2];
        assert_eq!(methods.children.len(), 2);
    }

    #[test]
    fn parse_frontmatter() {
        let source = std::fs::read_to_string("tests/fixtures/with_frontmatter.md").unwrap();
        let doc = parse(&source).unwrap();

        assert!(doc.frontmatter.is_some());
        let fm_range = doc.frontmatter.as_ref().unwrap();
        let fm_text = &source[fm_range.start..fm_range.end];
        assert!(fm_text.contains("title:"));
        assert!(fm_text.contains("tags:"));
    }

    #[test]
    fn parse_preamble() {
        let source = std::fs::read_to_string("tests/fixtures/with_preamble.md").unwrap();
        let doc = parse(&source).unwrap();

        assert!(doc.frontmatter.is_some());
        assert!(doc.preamble.is_some());
        let pre_text = doc.slice(doc.preamble.as_ref().unwrap());
        assert!(pre_text.contains("preamble text"));
    }

    #[test]
    fn parse_code_fences_ignores_fake_headings() {
        let source = std::fs::read_to_string("tests/fixtures/code_fences.md").unwrap();
        let doc = parse(&source).unwrap();

        let all = doc.all_sections();
        let heading_texts: Vec<&str> = all.iter().map(|(s, _)| s.heading_text.as_str()).collect();
        assert!(heading_texts.contains(&"Real Heading"));
        assert!(heading_texts.contains(&"Another Real Heading"));
        assert!(heading_texts.contains(&"Final Real Heading"));
        assert!(!heading_texts.contains(&"This is not a heading"));
    }

    #[test]
    fn parse_no_headings() {
        let source = std::fs::read_to_string("tests/fixtures/no_headings.md").unwrap();
        let doc = parse(&source).unwrap();

        assert!(doc.sections.is_empty());
        assert!(doc.preamble.is_some());
    }

    #[test]
    fn parse_byte_ranges_are_correct() {
        let source = "# Title\n\nContent line.\n\n## Section\n\nSection content.\n";
        let doc = parse(source).unwrap();

        let root = &doc.sections[0];
        assert_eq!(&source[root.heading_range.clone()], "# Title\n");
        assert_eq!(root.full_range.start, 0);
        assert_eq!(root.full_range.end, source.len());
    }

    #[test]
    fn parse_line_numbers_are_one_indexed() {
        let source = "# Title\n\n## Second\n\nContent.\n";
        let doc = parse(source).unwrap();

        let root = &doc.sections[0];
        assert_eq!(root.line_start, 1);
        let second = &root.children[0];
        assert_eq!(second.line_start, 3);
    }
}
