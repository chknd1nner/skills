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

#[test]
fn append_to_preamble_existing() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "Appended line."])
        .assert()
        .success()
        .stdout(predicate::str::contains("APPENDED"))
        .stdout(predicate::str::contains("_preamble"))
        .stdout(predicate::str::contains("+ Appended line."));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Existing preamble."));
    assert!(result.contains("Appended line."));
    let existing_pos = result.find("Existing preamble.").unwrap();
    let appended_pos = result.find("Appended line.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(existing_pos < appended_pos);
    assert!(appended_pos < heading_pos);
    drop(dir);
}

#[test]
fn append_to_preamble_creates_when_absent() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "New preamble."])
        .assert()
        .success()
        .stdout(predicate::str::contains("APPENDED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New preamble."));
    let preamble_pos = result.find("New preamble.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(preamble_pos < heading_pos);
    drop(dir);
}

#[test]
fn append_to_preamble_dry_run() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("New.")); // file unchanged
    drop(dir);
}

#[test]
fn append_to_preamble_no_frontmatter() {
    let (dir, file) = common::temp_md_file(
        "Existing preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "Appended."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Existing preamble."));
    assert!(result.contains("Appended."));
    let existing_pos = result.find("Existing preamble.").unwrap();
    let appended_pos = result.find("Appended.").unwrap();
    assert!(existing_pos < appended_pos);
    drop(dir);
}

#[test]
fn append_to_preamble_no_headings_document() {
    // Document with no headings — preamble is entire content
    let (dir, file) = common::temp_md_file(
        "Just some text.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "_preamble", "--content", "Appended."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Just some text."));
    assert!(result.contains("Appended."));
    let existing_pos = result.find("Just some text.").unwrap();
    let appended_pos = result.find("Appended.").unwrap();
    assert!(existing_pos < appended_pos);
    drop(dir);
}
