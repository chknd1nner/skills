mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn frontmatter_show_all() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "show", &common::fixture_path_str("with_frontmatter.md")])
        .assert()
        .success()
        .stdout(predicate::str::contains("FRONTMATTER:"))
        .stdout(predicate::str::contains("title:"))
        .stdout(predicate::str::contains("tags:"));
}

#[test]
fn frontmatter_get_key() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "get", &common::fixture_path_str("with_frontmatter.md"), "title"])
        .assert()
        .success()
        .stdout(predicate::str::contains("My Document"));
}

#[test]
fn frontmatter_get_missing_key() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "get", &common::fixture_path_str("with_frontmatter.md"), "nonexistent"])
        .assert()
        .code(4)
        .stderr(predicate::str::contains("not found"));
}

#[test]
fn frontmatter_set() {
    let (_dir, file) = common::temp_md_file(
        "---\ntitle: \"Old\"\n---\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "set", file.to_str().unwrap(), "title", "\"New\""])
        .assert()
        .success()
        .stderr(predicate::str::contains("FRONTMATTER SET:"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New"));
}

#[test]
fn frontmatter_delete_key() {
    let (_dir, file) = common::temp_md_file(
        "---\ntitle: \"Doc\"\ndraft: true\n---\n\n# H\n\nC.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "delete", file.to_str().unwrap(), "draft"])
        .assert()
        .success()
        .stderr(predicate::str::contains("FRONTMATTER DELETED:"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("draft"));
    assert!(result.contains("title")); // other keys preserved
}

#[test]
fn frontmatter_no_frontmatter() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "show", &common::fixture_path_str("simple.md")])
        .assert()
        .code(3)
        .stderr(predicate::str::contains("No frontmatter"));
}

#[test]
fn frontmatter_set_dry_run() {
    let (_dir, file) = common::temp_md_file(
        "---\ntitle: \"Old\"\n---\n\n# H\n\nC.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "set", file.to_str().unwrap(), "title", "\"New\"", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    // File should NOT be changed
    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Old"));
}

#[test]
fn frontmatter_bare_invocation() {
    // mdedit frontmatter doc.md should behave like mdedit frontmatter show doc.md
    let show_output = Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", "show", &common::fixture_path_str("with_frontmatter.md")])
        .output()
        .unwrap();

    let bare_output = Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter", &common::fixture_path_str("with_frontmatter.md")])
        .output()
        .unwrap();

    assert!(bare_output.status.success());
    assert_eq!(
        String::from_utf8_lossy(&show_output.stdout),
        String::from_utf8_lossy(&bare_output.stdout)
    );
}

#[test]
fn frontmatter_bare_no_file_errors() {
    Command::cargo_bin("mdedit").unwrap()
        .args(&["frontmatter"])
        .assert()
        .failure();
}
