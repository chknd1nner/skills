mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn search_finds_matches_grouped_by_section() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["search", &common::fixture_path_str("simple.md"), "content"])
        .assert()
        .success()
        .stdout(predicate::str::contains("SEARCH:"))
        .stdout(predicate::str::contains("## Introduction"));
}

#[test]
fn search_case_insensitive_by_default() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["search", &common::fixture_path_str("simple.md"), "INTRODUCTION"])
        .assert()
        .success()
        .stdout(predicate::str::contains("match"));
}

#[test]
fn search_case_sensitive_flag() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["search", &common::fixture_path_str("simple.md"), "INTRODUCTION", "--case-sensitive"])
        .assert()
        .success()
        // Should find 0 matches since source uses lowercase
        .stdout(predicate::str::contains("0 matches"));
}

#[test]
fn search_highlights_with_pipes() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["search", &common::fixture_path_str("simple.md"), "constraints"])
        .assert()
        .success()
        .stdout(predicate::str::contains("|constraints|"));
}
