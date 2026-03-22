mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn rename_heading() {
    let (dir, file) = common::temp_md_file("# Doc\n\n## Old Name\n\nContent.\n");
    Command::cargo_bin("mdedit")
        .unwrap()
        .args(&["rename", file.to_str().unwrap(), "Old Name", "New Name"])
        .assert()
        .success()
        .stdout(predicate::str::contains("RENAMED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("## New Name"));
    assert!(!result.contains("## Old Name"));
    assert!(result.contains("Content.")); // content preserved
    drop(dir);
}

#[test]
fn rename_preserves_level() {
    let (dir, file) = common::temp_md_file("# Doc\n\n### Deep Heading\n\nContent.\n");
    Command::cargo_bin("mdedit")
        .unwrap()
        .args(&["rename", file.to_str().unwrap(), "Deep Heading", "New Deep"])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("### New Deep")); // still H3
    drop(dir);
}

#[test]
fn rename_preamble_is_invalid() {
    let (dir, file) = common::temp_md_file(
        "Preamble.\n\n## Section\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["rename", file.to_str().unwrap(), "_preamble", "New Name"])
        .assert()
        .failure()
        .stderr(predicate::str::contains("not valid for _preamble"));
    drop(dir);
}

#[test]
fn rename_noop_same_name() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["rename", file.to_str().unwrap(), "Section", "Section"])
        .assert()
        .failure()
        .code(10); // NoOp exit code
    drop(dir);
}

#[test]
fn rename_dry_run() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Old Name\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["rename", file.to_str().unwrap(), "Old Name", "New Name", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"))
        .stdout(predicate::str::contains("WOULD RENAME"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("## Old Name")); // unchanged
    drop(dir);
}
