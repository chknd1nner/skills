mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn outline_simple() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("# My Document"))
        .stdout(predicate::str::contains("## Introduction"))
        .stdout(predicate::str::contains("## Background"))
        .stdout(predicate::str::contains("## Conclusion"))
        .stdout(predicate::str::contains("words"));
}

#[test]
fn outline_nested_shows_hierarchy() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", &common::fixture_path_str("nested.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("### Prior Work"))
        .stdout(predicate::str::contains("### Definitions"));
}

#[test]
fn outline_max_depth() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", &common::fixture_path_str("nested.md"), "--max-depth", "2"])
        .assert()
        .success()
        .stdout(predicate::str::contains("## Background"))
        // H3 should NOT appear
        .stdout(predicate::str::contains("### Prior Work").not());
}

#[test]
fn outline_flags_empty_sections() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", &common::fixture_path_str("empty_sections.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("⚠ empty"));
}

#[test]
fn outline_file_not_found() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["outline", "nonexistent.md"])
        .assert()
        .code(3)
        .stderr(predicate::str::contains("ERROR"));
}
