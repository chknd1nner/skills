mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn stats_shows_word_counts() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("STATS:"))
        .stdout(predicate::str::contains("words"));
}

#[test]
fn stats_shows_percentages() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("%"));
}

#[test]
fn stats_annotates_largest_section() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("simple.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("← largest"));
}

#[test]
fn stats_annotates_empty_sections() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("empty_sections.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("← empty"));
}

#[test]
fn stats_shows_hierarchy() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["stats", &common::fixture_path_str("nested.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("### Prior Work"));
}
