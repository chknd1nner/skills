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
    Command::cargo_bin("mdedit").unwrap()
        .args(&["validate", &common::fixture_path_str("duplicate_headings.md")])
        .assert()
        .success() // ℹ only, not ⚠, so exit 0
        .stdout(predicate::str::contains("ℹ"))
        .stdout(predicate::str::contains("Duplicate"));
}
