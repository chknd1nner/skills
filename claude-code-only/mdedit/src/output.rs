use std::io::IsTerminal;
use crate::document::{Document, Section};

pub fn is_tty() -> bool {
    std::io::stdout().is_terminal()
}

/// Format the neighborhood view for a write operation.
/// Shows previous section, target section, next section.
pub fn format_neighborhood(
    _doc: &Document,
    _target: &Section,
    _marker: &str, // "→" for modified, "✗" for deleted, "+" prefix for added
) -> String {
    todo!() // Implement in Task 8 when write commands need it
}

/// Format a section summary for neighborhood view:
/// "  ## Heading\n  First line of content...\n  [N more lines]\n"
pub fn format_section_preview(doc: &Document, section: &Section) -> String {
    let content = doc.slice(&section.own_content_range).trim();
    let lines: Vec<&str> = content.lines().collect();

    let mut out = format!("  {}\n", section.full_heading());
    let non_empty: Vec<&str> = lines.into_iter().filter(|l| !l.is_empty()).collect();
    if let Some(first) = non_empty.first() {
        out.push_str(&format!("  {}\n", first));
    }
    let remaining = if non_empty.len() > 1 { non_empty.len() - 1 } else { 0 };
    if remaining > 0 {
        out.push_str(&format!("  [{} more lines]\n", remaining));
    }
    out
}
