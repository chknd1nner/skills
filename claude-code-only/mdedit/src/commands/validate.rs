use crate::counting::section_own_word_count;
use crate::error::{MdeditError, Severity, ValidationIssue};
use crate::parser;

pub fn run(file: &str) -> Result<(), MdeditError> {
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("Cannot read '{}': {}", file, e)))?;

    let doc = parser::parse(&source)
        .map_err(|e| MdeditError::FileError(format!("Parse error in '{}': {}", file, e)))?;

    let mut issues: Vec<ValidationIssue> = Vec::new();
    let all_sections = doc.all_sections();
    let total_sections = all_sections.len();

    // Collect flat list of all sections for duplicate detection
    // We need: (level, heading_text, line_start) for each section
    let flat: Vec<(u8, &str, usize)> = all_sections.iter()
        .map(|(s, _)| (s.level, s.heading_text.as_str(), s.line_start))
        .collect();

    // Check 1: Skipped heading levels
    // Compare each section to its parent level.
    for (section, parent) in &all_sections {
        // A skipped level means section.level > expected_min_level + some gap
        // Specifically: if parent is H2, children should be H3. If child is H4, that's skipped.
        if let Some(p) = parent {
            if section.level > p.level + 1 {
                issues.push(ValidationIssue {
                    severity: Severity::Warning,
                    line: section.line_start,
                    message: format!(
                        "H{} \"{}\" has no H{} parent (skipped level)",
                        section.level,
                        section.full_heading(),
                        section.level - 1,
                    ),
                });
            }
        }
    }

    // Check 2: Empty sections (heading with no own content lines)
    for (section, _parent) in &all_sections {
        let own_words = section_own_word_count(&doc, section);
        // Also check if own_content_range is empty (no content text at all)
        let own_content = doc.slice(&section.own_content_range);
        let has_content = own_content.lines().any(|l| !l.trim().is_empty());
        if !has_content && section.children.is_empty() {
            // Leaf section with no content
            issues.push(ValidationIssue {
                severity: Severity::Warning,
                line: section.line_start,
                message: format!(
                    "Section \"{}\" is empty (0 content lines)",
                    section.full_heading(),
                ),
            });
        } else if !has_content && own_words == 0 && section.children.is_empty() {
            // Covered above
        }
        let _ = own_words; // suppress unused warning
    }

    // Check 3: Duplicate heading text (regardless of level — same text is ambiguous for LLMs)
    // For each section, check if any earlier section has the same heading_text
    let mut seen: Vec<(u8, &str, usize)> = Vec::new();
    let mut reported_dupes: std::collections::HashSet<String> = std::collections::HashSet::new();

    for &(level, text, line) in &flat {
        if let Some(&(prev_level, _, prev_line)) = seen.iter().find(|&&(_, t, _)| t == text) {
            let key = text.to_string();
            if !reported_dupes.contains(&key) {
                issues.push(ValidationIssue {
                    severity: Severity::Info,
                    line,
                    message: format!(
                        "Duplicate heading text \"{}\" (also at line {} as H{})",
                        format!("{} {}", "#".repeat(level as usize), text),
                        prev_line,
                        prev_level,
                    ),
                });
                reported_dupes.insert(key);
            }
        }
        seen.push((level, text, line));
    }

    // Sort issues by line number
    issues.sort_by_key(|i| i.line);

    // Determine if there are any warnings
    let has_warnings = issues.iter().any(|i| matches!(i.severity, Severity::Warning));

    if issues.is_empty() {
        // Compute max depth
        let max_depth = all_sections.iter()
            .map(|(s, _)| s.level as usize)
            .max()
            .unwrap_or(0);
        let filename = std::path::Path::new(file)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or(file);
        println!(
            "VALID: {} — {} sections, max depth {}, no issues",
            filename, total_sections, max_depth
        );
        return Ok(());
    }

    // Print issues to stdout (not stderr) per spec
    let filename = std::path::Path::new(file)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(file);
    let issue_word = if issues.len() == 1 { "issue" } else { "issues" };

    if has_warnings {
        // Return as ValidationFailures error so main.rs exits with code 5
        // But we need to print to stdout first — the error Display goes to stderr in main.
        // Per spec: output goes to stdout with INVALID: prefix.
        // We must print to stdout here, then signal via exit code.
        // The error handler in main.rs will eprintln! the error, but we also print here.
        // Actually: let's print to stdout and return the error to get exit code 5.
        println!("INVALID: {} — {} {}", filename, issues.len(), issue_word);
        println!();
        for issue in &issues {
            let marker = match issue.severity {
                Severity::Warning => "⚠",
                Severity::Info => "ℹ",
            };
            println!("  {} Line {}: {}", marker, issue.line, issue.message);
        }
        // Return validation error to get exit code 5 (main.rs will also eprintln!, that's ok)
        Err(MdeditError::ValidationFailures(issues))
    } else {
        // Info-only: print to stdout and exit 0
        println!("INVALID: {} — {} {}", filename, issues.len(), issue_word);
        println!();
        for issue in &issues {
            let marker = match issue.severity {
                Severity::Warning => "⚠",
                Severity::Info => "ℹ",
            };
            println!("  {} Line {}: {}", marker, issue.line, issue.message);
        }
        Ok(())
    }
}
