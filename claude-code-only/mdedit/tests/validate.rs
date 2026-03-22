mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn validate_clean_document() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["validate", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("VALID"));
}

#[test]
fn validate_finds_empty_sections() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["validate", &common::fixture_path_str("empty_sections.md")])
        .assert()
        .code(5)
        .stdout(predicate::str::contains("⚠"))
        .stdout(predicate::str::contains("empty"));
}

#[test]
fn validate_finds_duplicate_headings() {
    // Create a doc with same-level duplicate headings
    let (_dir, path) = common::temp_md_file(
        "# Doc\n\n## Notes\n\nSome notes.\n\n## Background\n\nContext.\n\n## Notes\n\nMore notes.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["validate", path.to_str().unwrap()])
        .assert()
        .success() // ℹ only, not ⚠, so exit 0
        .stdout(predicate::str::contains("ℹ"))
        .stdout(predicate::str::contains("Duplicate"));
}

#[test]
fn validate_cross_level_duplicates_not_flagged() {
    // duplicate_headings.md has "Notes" at H2 and H3 (different levels) — should NOT be flagged
    Command::cargo_bin("mdedit").unwrap()
        .args(&["validate", &common::fixture_path_str("duplicate_headings.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("VALID"));
}
