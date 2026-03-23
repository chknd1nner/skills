mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn delete_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Keep\n\nKeep content.\n\n## Remove\n\nRemove content.\n\n## Also Keep\n\nAlso keep.\n",
    );
    Command::cargo_bin("mdedit")
        .unwrap()
        .args(&["delete", file.to_str().unwrap(), "Remove"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DELETED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("Remove content."));
    assert!(result.contains("Keep content."));
    assert!(result.contains("Also keep."));
    drop(dir);
}

#[test]
fn delete_shows_removed_content() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nFirst line.\nLast line.\n",
    );
    Command::cargo_bin("mdedit")
        .unwrap()
        .args(&["delete", file.to_str().unwrap(), "Section"])
        .assert()
        .success()
        .stdout(predicate::str::contains("First line."));
    drop(dir);
}

#[test]
fn delete_warns_about_children() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Parent\n\nContent.\n\n### Child\n\nChild content.\n",
    );
    Command::cargo_bin("mdedit")
        .unwrap()
        .args(&["delete", file.to_str().unwrap(), "Parent"])
        .assert()
        .success()
        .stdout(predicate::str::contains("\u{26a0}"))
        .stdout(predicate::str::contains("child"));
    drop(dir);
}

#[test]
fn delete_dry_run() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nContent.\n",
    );
    Command::cargo_bin("mdedit")
        .unwrap()
        .args(&["delete", file.to_str().unwrap(), "Section", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Content.")); // not deleted
    drop(dir);
}

#[test]
fn delete_preamble() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nPreamble text here.\n\n## Section\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["delete", file.to_str().unwrap(), "_preamble"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DELETED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("Preamble text here."));
    assert!(result.contains("## Section")); // sections preserved
    drop(dir);
}

#[test]
fn delete_empty_preamble_is_noop() {
    let (dir, file) = common::temp_md_file(
        "## Section\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["delete", file.to_str().unwrap(), "_preamble"])
        .assert()
        .failure()
        .code(10); // NoOp exit code
    drop(dir);
}
