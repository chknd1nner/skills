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
        .stderr(predicate::str::contains("PREPENDED"))
        .stderr(predicate::str::contains("+"));

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
        .stderr(predicate::str::contains("+ Added."));
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

#[test]
fn prepend_from_file() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    let content_file = dir.path().join("content.txt");
    std::fs::write(&content_file, "From file content.").unwrap();

    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--from-file", content_file.to_str().unwrap()])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("From file content."));
    let prepended_pos = result.find("From file content.").unwrap();
    let existing_pos = result.find("Existing.").unwrap();
    assert!(prepended_pos < existing_pos);
    drop(dir);
}

#[test]
fn prepend_multiline_content() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nExisting.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "Section", "--content", "Line one.\nLine two."])
        .assert()
        .success()
        .stderr(predicate::str::contains("+ Line one."))
        .stderr(predicate::str::contains("+ Line two."));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Line one.\nLine two."));
    let multiline_pos = result.find("Line one.").unwrap();
    let existing_pos = result.find("Existing.").unwrap();
    assert!(multiline_pos < existing_pos);
    drop(dir);
}

#[test]
fn prepend_to_preamble_existing() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "_preamble", "--content", "Prepended line."])
        .assert()
        .success()
        .stderr(predicate::str::contains("PREPENDED"))
        .stderr(predicate::str::contains("_preamble"))
        .stderr(predicate::str::contains("+ Prepended line."));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Prepended line."));
    assert!(result.contains("Existing preamble."));
    let prepended_pos = result.find("Prepended line.").unwrap();
    let existing_pos = result.find("Existing preamble.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(prepended_pos < existing_pos);
    assert!(existing_pos < heading_pos);
    drop(dir);
}

#[test]
fn prepend_to_preamble_creates_when_absent() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "_preamble", "--content", "New preamble."])
        .assert()
        .success()
        .stderr(predicate::str::contains("PREPENDED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New preamble."));
    let preamble_pos = result.find("New preamble.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(preamble_pos < heading_pos);
    drop(dir);
}

#[test]
fn prepend_to_preamble_dry_run() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "_preamble", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(!result.contains("New.")); // file unchanged
    drop(dir);
}

#[test]
fn prepend_to_preamble_no_frontmatter() {
    let (dir, file) = common::temp_md_file(
        "Existing preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["prepend", file.to_str().unwrap(), "_preamble", "--content", "Prepended."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Prepended."));
    assert!(result.contains("Existing preamble."));
    let prepended_pos = result.find("Prepended.").unwrap();
    let existing_pos = result.find("Existing preamble.").unwrap();
    assert!(prepended_pos < existing_pos);
    drop(dir);
}
