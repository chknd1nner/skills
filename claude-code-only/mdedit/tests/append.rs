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
