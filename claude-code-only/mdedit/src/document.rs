use std::ops::Range;

/// A parsed markdown document
#[derive(Debug, Clone)]
pub struct Document {
    /// Original source text (owned)
    pub source: String,
    /// Byte range of YAML frontmatter (including --- delimiters), if present
    pub frontmatter: Option<Range<usize>>,
    /// Byte range of content between frontmatter and first heading, if present
    pub preamble: Option<Range<usize>>,
    /// Top-level sections (nested hierarchy)
    pub sections: Vec<Section>,
}

/// A section: heading + content + child sections
#[derive(Debug, Clone)]
pub struct Section {
    /// Heading text without # prefix, trimmed (e.g. "Background")
    pub heading_text: String,
    /// Heading level (1-6)
    pub level: u8,
    /// Byte range of the heading line only
    pub heading_range: Range<usize>,
    /// Byte range of own content (after heading, before first child section)
    pub own_content_range: Range<usize>,
    /// Byte range of entire section (heading + own content + all children)
    pub full_range: Range<usize>,
    /// 1-indexed line number of heading
    pub line_start: usize,
    /// 1-indexed line number of last line in section
    pub line_end: usize,
    /// Nested child sections
    pub children: Vec<Section>,
}

impl Document {
    /// Get the source text for a byte range
    pub fn slice(&self, range: &Range<usize>) -> &str {
        &self.source[range.start..range.end]
    }

    /// All sections flattened (recursive depth-first), with parent info
    pub fn all_sections(&self) -> Vec<(&Section, Option<&Section>)> {
        let mut result = Vec::new();
        for section in &self.sections {
            Self::collect_sections(section, None, &mut result);
        }
        result
    }

    fn collect_sections<'a>(
        section: &'a Section,
        parent: Option<&'a Section>,
        result: &mut Vec<(&'a Section, Option<&'a Section>)>,
    ) {
        result.push((section, parent));
        for child in &section.children {
            Self::collect_sections(child, Some(section), result);
        }
    }

    /// Compute 1-indexed line number from byte offset
    pub fn byte_to_line(&self, byte: usize) -> usize {
        self.source[..byte].matches('\n').count() + 1
    }

    /// Returns the byte range for preamble content, for write operations.
    /// - If preamble exists: returns its range
    /// - If no preamble exists: returns an empty range at the insertion point
    ///   (after frontmatter end, or byte 0 if no frontmatter)
    pub fn preamble_write_range(&self) -> Range<usize> {
        if let Some(ref range) = self.preamble {
            range.clone()
        } else {
            let point = self.frontmatter.as_ref()
                .map(|fm| fm.end)
                .unwrap_or(0);
            point..point
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preamble_write_range_with_preamble() {
        let doc = Document {
            source: "---\ntitle: x\n---\n\nPreamble text.\n\n# Heading\n".to_string(),
            frontmatter: Some(0..17),
            preamble: Some(18..33),
            sections: vec![],
        };
        assert_eq!(doc.preamble_write_range(), 18..33);
    }

    #[test]
    fn preamble_write_range_no_preamble_with_frontmatter() {
        let doc = Document {
            source: "---\ntitle: x\n---\n\n# Heading\n".to_string(),
            frontmatter: Some(0..17),
            preamble: None,
            sections: vec![],
        };
        let range = doc.preamble_write_range();
        assert_eq!(range.start, 17);
        assert_eq!(range.end, 17);
        assert!(range.is_empty());
    }

    #[test]
    fn preamble_write_range_no_preamble_no_frontmatter() {
        let doc = Document {
            source: "# Heading\n".to_string(),
            frontmatter: None,
            preamble: None,
            sections: vec![],
        };
        let range = doc.preamble_write_range();
        assert_eq!(range.start, 0);
        assert_eq!(range.end, 0);
        assert!(range.is_empty());
    }
}

impl Section {
    /// Full heading with # prefix (e.g. "## Background")
    pub fn full_heading(&self) -> String {
        format!("{} {}", "#".repeat(self.level as usize), self.heading_text)
    }

    /// Total number of lines in this section
    pub fn line_count(&self) -> usize {
        if self.line_end >= self.line_start {
            self.line_end - self.line_start + 1
        } else {
            0
        }
    }

    /// All descendant sections (recursive)
    pub fn all_descendants(&self) -> Vec<&Section> {
        let mut result = Vec::new();
        for child in &self.children {
            result.push(child);
            result.extend(child.all_descendants());
        }
        result
    }
}
