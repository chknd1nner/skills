/// Normalise whitespace at section boundaries:
/// - Exactly one blank line between sections (before headings outside code fences)
/// - Exactly one trailing newline at EOF
/// - Whitespace within section content is never modified
pub fn normalise(source: &str) -> String {
    let lines: Vec<&str> = source.lines().collect();
    let mut result: Vec<&str> = Vec::with_capacity(lines.len());
    let mut in_code_fence = false;
    let mut fence_marker: Option<&str> = None;

    // We process line by line. When we encounter a heading line (not in a code
    // fence), we ensure exactly one blank line precedes it by trimming any
    // trailing blank lines in `result` and inserting exactly one blank line.
    for line in &lines {
        let trimmed = line.trim();

        // Track code fence state
        if in_code_fence {
            if let Some(marker) = fence_marker {
                if trimmed.starts_with(marker)
                    && trimmed.trim_start_matches(marker).trim().is_empty()
                {
                    in_code_fence = false;
                    fence_marker = None;
                }
            }
            result.push(line);
            continue;
        }

        // Check for opening code fence
        if trimmed.starts_with("```") || trimmed.starts_with("~~~") {
            in_code_fence = true;
            fence_marker = if trimmed.starts_with("```") {
                Some("```")
            } else {
                Some("~~~")
            };
            result.push(line);
            continue;
        }

        // Is this a heading line?
        if trimmed.starts_with('#') {
            // Remove all trailing blank lines before this heading
            while result.last().map(|l: &&str| l.trim().is_empty()).unwrap_or(false) {
                result.pop();
            }
            // Insert exactly one blank line before the heading (unless result is
            // empty — i.e., the heading is the very first content)
            if !result.is_empty() {
                result.push("");
            }
            result.push(line);
        } else {
            result.push(line);
        }
    }

    // Trim trailing blank lines and add exactly one trailing newline
    while result.last().map(|l: &&str| l.trim().is_empty()).unwrap_or(false) {
        result.pop();
    }

    if result.is_empty() {
        return "\n".to_string();
    }

    let mut out = result.join("\n");
    out.push('\n');
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalise_double_blank_lines() {
        let input = "# Title\n\n\n\n## Section\n\nContent.\n";
        let result = normalise(input);
        assert!(!result.contains("\n\n\n"));
    }

    #[test]
    fn normalise_trailing_newline() {
        let input = "# Title\n\nContent.\n\n\n";
        let result = normalise(input);
        assert!(result.ends_with('\n'));
        assert!(!result.ends_with("\n\n"));
    }

    #[test]
    fn normalise_preserves_internal_whitespace() {
        let input = "# Title\n\n## Section\n\nLine one.\n\nLine two.\n";
        let result = normalise(input);
        assert!(result.contains("Line one.\n\nLine two."));
    }

    #[test]
    fn normalise_single_blank_line_unchanged() {
        let input = "# Title\n\n## Section\n\nContent.\n";
        let result = normalise(input);
        assert_eq!(result, input);
    }

    #[test]
    fn normalise_no_extra_blank_before_first_heading() {
        // First heading should not get a leading blank line
        let input = "# Title\n\nContent.\n";
        let result = normalise(input);
        assert!(!result.starts_with('\n'));
        assert!(result.starts_with("# Title"));
    }

    #[test]
    fn normalise_code_fence_heading_not_affected() {
        let input = "# Title\n\n```\n# not a heading\n```\n\n## Real\n\nContent.\n";
        let result = normalise(input);
        // The fake heading inside code fence should not cause extra blank line manipulation
        assert!(result.contains("# not a heading"));
        // There should be exactly one blank line before ## Real
        assert!(result.contains("```\n\n## Real"));
    }
}
