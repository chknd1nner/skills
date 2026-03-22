use strsim::normalized_levenshtein;

use crate::document::{Document, Section};
use crate::error::{MdeditError, SectionRef};

/// Result of resolving a section address
#[derive(Debug)]
pub enum ResolvedSection<'a> {
    Found(&'a Section),
    Preamble,
}

/// Resolve a section query against a document.
///
/// Query formats:
/// - `_preamble` → content before first heading
/// - `## Heading` → match by level + text
/// - `Parent/Child` → match by path through hierarchy
/// - `Heading` → match by text (must be unique)
pub fn resolve<'a>(doc: &'a Document, query: &str) -> Result<ResolvedSection<'a>, MdeditError> {
    // 1. Check for _preamble
    if query == "_preamble" {
        return Ok(ResolvedSection::Preamble);
    }

    // 2. Parse the query
    if query.starts_with('#') {
        resolve_by_level_prefix(doc, query)
    } else if query.contains('/') {
        resolve_by_path(doc, query)
    } else {
        resolve_by_name(doc, query)
    }
}

/// Match by heading text only — must be unique
fn resolve_by_name<'a>(doc: &'a Document, name: &str) -> Result<ResolvedSection<'a>, MdeditError> {
    let all = doc.all_sections();
    let matches: Vec<_> = all
        .iter()
        .filter(|(s, _)| s.heading_text == name)
        .collect();

    match matches.len() {
        1 => Ok(ResolvedSection::Found(matches[0].0)),
        0 => Err(not_found_error(doc, name)),
        _ => Err(ambiguous_error(doc, name, &matches)),
    }
}

/// Match by level prefix, e.g. "## Background"
fn resolve_by_level_prefix<'a>(
    doc: &'a Document,
    query: &str,
) -> Result<ResolvedSection<'a>, MdeditError> {
    // Parse "## Text" → (level=2, text="Text")
    let hashes = query.chars().take_while(|&c| c == '#').count() as u8;
    let text = query[hashes as usize..].trim();

    let all = doc.all_sections();
    let matches: Vec<_> = all
        .iter()
        .filter(|(s, _)| s.level == hashes && s.heading_text == text)
        .collect();

    match matches.len() {
        1 => Ok(ResolvedSection::Found(matches[0].0)),
        0 => Err(not_found_error(doc, query)),
        _ => Err(ambiguous_error(doc, query, &matches)),
    }
}

/// Match by path, e.g. "Background/Notes"
fn resolve_by_path<'a>(
    doc: &'a Document,
    query: &str,
) -> Result<ResolvedSection<'a>, MdeditError> {
    let components: Vec<&str> = query.split('/').collect();
    if components.is_empty() {
        return Err(not_found_error(doc, query));
    }

    // Find the first component among top-level sections (recursively)
    let all = doc.all_sections();
    let first_name = components[0];

    // Start by finding all sections matching the first component
    let mut candidates: Vec<&Section> = all
        .iter()
        .filter(|(s, _)| s.heading_text == first_name)
        .map(|(s, _)| *s)
        .collect();

    // Walk remaining path components
    for &component in &components[1..] {
        let mut next_candidates = Vec::new();
        for candidate in &candidates {
            for child in &candidate.children {
                if child.heading_text == component {
                    next_candidates.push(child);
                }
            }
        }
        candidates = next_candidates;
    }

    match candidates.len() {
        1 => Ok(ResolvedSection::Found(candidates[0])),
        0 => Err(not_found_error(doc, query)),
        _ => {
            // Build matches with parent info for error
            let match_refs: Vec<SectionRef> = candidates
                .iter()
                .map(|s| {
                    let parent = all
                        .iter()
                        .find(|(sec, _)| std::ptr::eq(*sec, *s))
                        .and_then(|(_, p)| *p);
                    section_to_ref(s, parent)
                })
                .collect();
            Err(MdeditError::AmbiguousMatch {
                query: query.to_string(),
                file: String::new(),
                matches: match_refs,
            })
        }
    }
}

/// Build a SectionNotFound error with fuzzy suggestions
fn not_found_error(doc: &Document, query: &str) -> MdeditError {
    // Strip level prefix for fuzzy matching if present
    let search_text = if query.starts_with('#') {
        query.trim_start_matches('#').trim()
    } else if query.contains('/') {
        // Use the last path component for fuzzy matching
        query.rsplit('/').next().unwrap_or(query)
    } else {
        query
    };

    let all = doc.all_sections();
    let mut scored: Vec<(f64, &Section, Option<&Section>)> = all
        .iter()
        .map(|(s, p)| {
            let similarity = normalized_levenshtein(
                &search_text.to_lowercase(),
                &s.heading_text.to_lowercase(),
            );
            (similarity, *s, *p)
        })
        .filter(|(score, _, _)| *score >= 0.5)
        .collect();

    scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
    scored.truncate(3);

    let suggestions: Vec<SectionRef> = scored
        .iter()
        .map(|(_, s, p)| section_to_ref(s, *p))
        .collect();

    MdeditError::SectionNotFound {
        query: query.to_string(),
        file: String::new(),
        suggestions,
    }
}

/// Build an AmbiguousMatch error from (Section, Option<parent>) pairs
fn ambiguous_error(
    _doc: &Document,
    query: &str,
    matches: &[&(&Section, Option<&Section>)],
) -> MdeditError {
    let match_refs: Vec<SectionRef> = matches
        .iter()
        .map(|(s, p)| section_to_ref(s, *p))
        .collect();

    MdeditError::AmbiguousMatch {
        query: query.to_string(),
        file: String::new(),
        matches: match_refs,
    }
}

/// Convert a Section + optional parent to a SectionRef for error display
fn section_to_ref(section: &Section, parent: Option<&Section>) -> SectionRef {
    SectionRef {
        heading: section.heading_text.clone(),
        level: section.level,
        line: section.line_start,
        parent: parent.map(|p| p.heading_text.clone()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser;

    fn parse_fixture(name: &str) -> Document {
        let source = std::fs::read_to_string(format!("tests/fixtures/{}", name)).unwrap();
        parser::parse(&source).unwrap()
    }

    #[test]
    fn resolve_by_name() {
        let doc = parse_fixture("simple.md");
        let result = resolve(&doc, "Introduction").unwrap();
        match result {
            ResolvedSection::Found(s) => assert_eq!(s.heading_text, "Introduction"),
            _ => panic!("expected Found"),
        }
    }

    #[test]
    fn resolve_by_level_prefix() {
        let doc = parse_fixture("duplicate_headings.md");
        // "Notes" is ambiguous, but "## Notes" matches only the H2
        let result = resolve(&doc, "## Notes").unwrap();
        match result {
            ResolvedSection::Found(s) => {
                assert_eq!(s.heading_text, "Notes");
                assert_eq!(s.level, 2);
            }
            _ => panic!("expected Found"),
        }
    }

    #[test]
    fn resolve_by_path() {
        let doc = parse_fixture("duplicate_headings.md");
        let result = resolve(&doc, "Background/Notes").unwrap();
        match result {
            ResolvedSection::Found(s) => {
                assert_eq!(s.heading_text, "Notes");
                assert_eq!(s.level, 3); // It's a child of Background
            }
            _ => panic!("expected Found"),
        }
    }

    #[test]
    fn resolve_preamble() {
        let doc = parse_fixture("with_preamble.md");
        let result = resolve(&doc, "_preamble").unwrap();
        assert!(matches!(result, ResolvedSection::Preamble));
    }

    #[test]
    fn resolve_ambiguous_returns_error() {
        let doc = parse_fixture("duplicate_headings.md");
        let result = resolve(&doc, "Notes");
        assert!(result.is_err());
        match result.unwrap_err() {
            MdeditError::AmbiguousMatch { matches, .. } => {
                assert_eq!(matches.len(), 2);
            }
            e => panic!("expected AmbiguousMatch, got {:?}", e),
        }
    }

    #[test]
    fn resolve_not_found_has_fuzzy_suggestions() {
        let doc = parse_fixture("simple.md");
        let result = resolve(&doc, "Introductoin"); // typo
        assert!(result.is_err());
        match result.unwrap_err() {
            MdeditError::SectionNotFound { suggestions, .. } => {
                assert!(!suggestions.is_empty());
                // Should suggest "Introduction"
                assert!(suggestions.iter().any(|s| s.heading.contains("Introduction")));
            }
            e => panic!("expected SectionNotFound, got {:?}", e),
        }
    }

    #[test]
    fn resolve_preamble_when_none_exists() {
        let doc = parse_fixture("simple.md");
        // simple.md has no preamble — _preamble should still resolve,
        // but operations on it will find no content
        assert!(matches!(resolve(&doc, "_preamble").unwrap(), ResolvedSection::Preamble));
    }
}
