mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn extract_section_shows_content() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("simple.md"), "Introduction"])
        .assert()
        .success()
        .stdout(predicate::str::contains("SECTION:"))
        .stdout(predicate::str::contains("introduction section"));
}

#[test]
fn extract_with_children() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("nested.md"), "Background"])
        .assert()
        .success()
        .stdout(predicate::str::contains("Prior Work"))
        .stdout(predicate::str::contains("Definitions"));
}

#[test]
fn extract_no_children() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("nested.md"), "Background", "--no-children"])
        .assert()
        .success()
        .stdout(predicate::str::contains("children excluded"))
        .stdout(predicate::str::contains("Prior Work").not());
}

#[test]
fn extract_to_file() {
    let dir = tempfile::tempdir().unwrap();
    let out_path = dir.path().join("section.md");
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("simple.md"), "Introduction",
                "--to-file", out_path.to_str().unwrap()])
        .assert()
        .success()
        .stdout(predicate::str::contains("EXTRACTED:"))
        .stdout(predicate::str::contains("→"));

    // Verify file was written
    let content = std::fs::read_to_string(&out_path).unwrap();
    assert!(content.contains("introduction section"));
    // Should NOT contain SECTION: header
    assert!(!content.contains("SECTION:"));
}

#[test]
fn extract_preamble() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("with_preamble.md"), "_preamble"])
        .assert()
        .success()
        .stdout(predicate::str::contains("preamble text"));
}

#[test]
fn extract_not_found() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("simple.md"), "Nonexistent"])
        .assert()
        .code(1)
        .stderr(predicate::str::contains("not found"));
}

#[test]
fn extract_empty_section() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", &common::fixture_path_str("empty_sections.md"), "Empty Section"])
        .assert()
        .success()
        .stdout(predicate::str::contains("[no content]"));
}
