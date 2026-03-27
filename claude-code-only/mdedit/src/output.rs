use std::io::IsTerminal;
use crate::document::{Document, Section};

/// Check if stdout is a terminal, with env var override for testing.
/// MDEDIT_FORCE_TTY=1 forces TTY mode (for testing terminal output paths).
/// MDEDIT_FORCE_TTY=0 forces pipe mode (for testing pipe output paths).
pub fn is_tty() -> bool {
    match std::env::var("MDEDIT_FORCE_TTY").as_deref() {
        Ok("1") => true,
        Ok("0") => false,
        _ => std::io::stdout().is_terminal(),
    }
}

/// Emit verification output for write operations.
/// TTY: prints to stdout. Piped: prints to stderr.
/// Dry-run always goes to stdout (preview IS the requested data).
pub fn emit_verification(output: &str, dry_run: bool) {
    if dry_run || is_tty() {
        print!("{}", output);
    } else {
        eprint!("{}", output);
    }
}

/// Format the neighborhood view for a write operation.
/// Shows previous section, target section (with → marker), next section.
///
/// The marker is placed before the target section heading line.
/// `target_content_preview` is the new content (after the operation).
pub fn format_neighborhood(
    doc: &Document,
    target: &Section,
    action_label: &str,     // "REPLACED", "WOULD REPLACE", etc.
    summary: &str,          // "(was 12 lines → now 8 lines)"
    new_content: &str,      // the new content text (after operation)
    warnings: &[String],
    dry_run: bool,
) -> String {
    let mut out = String::new();

    // Header line
    if dry_run {
        out.push_str("DRY RUN — no changes written\n\n");
    }

    // "REPLACED: "## Background" (was 12 lines, 312 words → now 8 lines, 198 words)"
    out.push_str(&format!("{}: \"{}\" {}\n", action_label, target.full_heading(), summary));

    // Warnings
    for w in warnings {
        out.push_str(&format!("⚠ {}\n", w));
    }

    out.push('\n');

    // Previous section
    if let Some(prev) = find_previous_section(doc, target) {
        out.push_str(&format_section_preview(doc, prev));
        out.push('\n');
    }

    // Target section with → marker
    // Show the new content (after operation)
    let new_lines: Vec<&str> = new_content.lines().collect();
    let non_empty_new: Vec<&str> = new_lines.iter()
        .copied()
        .filter(|l| !l.trim().is_empty())
        .collect();

    out.push_str(&format!("→ {}\n", target.full_heading()));
    if let Some(first) = non_empty_new.first() {
        out.push_str(&format!("  {}\n", first));
    }
    let remaining = if non_empty_new.len() > 1 { non_empty_new.len() - 1 } else { 0 };
    if remaining > 1 {
        out.push_str(&format!("  [{} more lines]\n", remaining - 1));
        // Show last line
        if let Some(last) = non_empty_new.last() {
            if non_empty_new.len() > 1 {
                out.push_str(&format!("  {}\n", last));
            }
        }
    } else if remaining == 1 {
        // Just show the second (last) line directly
        if let Some(last) = non_empty_new.last() {
            out.push_str(&format!("  {}\n", last));
        }
    }

    // Next section
    out.push('\n');
    if let Some(next) = find_next_section(doc, target) {
        out.push_str(&format_section_preview(doc, next));
    } else {
        out.push_str("  [end of document]\n");
    }

    out
}

/// Find the section that immediately precedes `target` in document order.
/// Uses the flat all_sections list and finds the entry just before target.
pub(crate) fn find_previous_section<'a>(doc: &'a Document, target: &Section) -> Option<&'a Section> {
    let all = doc.all_sections();
    let mut prev: Option<&Section> = None;
    for (section, _) in &all {
        if std::ptr::eq(*section, target) {
            return prev;
        }
        prev = Some(section);
    }
    None
}

/// Find the section that immediately follows `target` in document order.
pub(crate) fn find_next_section<'a>(doc: &'a Document, target: &Section) -> Option<&'a Section> {
    let all = doc.all_sections();
    let mut found = false;
    for (section, _) in &all {
        if found {
            return Some(section);
        }
        if std::ptr::eq(*section, target) {
            found = true;
        }
    }
    None
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
