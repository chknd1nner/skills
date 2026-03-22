// tests/prepend.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn prepend_to_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting content.\n\n## Other\n\nOther.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--content", "Prepended line."])
        .assert()
        .success()
        .stdout(predicate::str::contains("PREPENDED"))
        .stdout(predicate::str::contains("+"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Prepended line."));
    assert!(result.contains("Existing content."));
    // Prepended content should come before existing
    let prepended_pos = result.find("Prepended line.").unwrap();
    let existing_pos = result.find("Existing content.").unwrap();
    assert!(prepended_pos < existing_pos);
    drop(dir);
}

#[test]
fn prepend_goes_after_heading() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--content", "First."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    // Heading should still be before prepended content
    let heading_pos = result.find("## Section").unwrap();
    let prepended_pos = result.find("First.").unwrap();
    assert!(heading_pos < prepended_pos);
    drop(dir);
}

#[test]
fn prepend_to_empty_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Empty\n\n## Next\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Empty", "--content", "Now has content."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Now has content."));
    drop(dir);
}

#[test]
fn prepend_shows_plus_prefix() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--content", "Added."])
        .assert()
        .success()
        .stdout(predicate::str::contains("+ Added."));
    drop(dir);
}

#[test]
fn prepend_dry_run() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("New.")); // unchanged
    drop(dir);
}
