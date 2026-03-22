// tests/append.rs
mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn append_to_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting content.\n\n## Other\n\nOther.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Section", "--content", "Appended line."])
        .assert()
        .success()
        .stdout(predicate::str::contains("APPENDED"))
        .stdout(predicate::str::contains("+"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Existing content."));
    assert!(result.contains("Appended line."));
    // Appended content should come after existing, before ## Other
    let existing_pos = result.find("Existing content.").unwrap();
    let appended_pos = result.find("Appended line.").unwrap();
    let other_pos = result.find("## Other").unwrap();
    assert!(existing_pos < appended_pos);
    assert!(appended_pos < other_pos);
    drop(dir);
}

#[test]
fn append_to_empty_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Empty\n\n## Next\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Empty", "--content", "New content."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New content."));
    drop(dir);
}

#[test]
fn append_shows_plus_prefix() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Section", "--content", "Added."])
        .assert()
        .success()
        .stdout(predicate::str::contains("+ Added."));
    drop(dir);
}

#[test]
fn append_dry_run() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Section", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("New.")); // file unchanged
    drop(dir);
}

#[test]
fn append_from_file() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    let content_file = dir.path().join("content.txt");
    std::fs::write(&content_file, "From file content.").unwrap();

    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Section", "--from-file", content_file.to_str().unwrap()])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("From file content."));
    let existing_pos = result.find("Existing.").unwrap();
    let appended_pos = result.find("From file content.").unwrap();
    assert!(existing_pos < appended_pos);
    drop(dir);
}

#[test]
fn append_multiline_content() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Section", "--content", "Line one.\nLine two."])
        .assert()
        .success()
        .stdout(predicate::str::contains("+ Line one."))
        .stdout(predicate::str::contains("+ Line two."));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Line one.\nLine two."));
    drop(dir);
}
