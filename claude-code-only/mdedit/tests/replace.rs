mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn replace_section_content() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOld content.\n\n## Other\n\nOther content.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "New content."])
        .assert()
        .success()
        .stdout(predicate::str::contains("REPLACED"))
        .stdout(predicate::str::contains("→ ## Section"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New content."));
    assert!(!result.contains("Old content."));
    assert!(result.contains("Other content.")); // other section preserved
    // Verify blank line between heading and content is preserved
    assert!(result.contains("## Section\n\nNew content."));
    drop(dir);
}

#[test]
fn replace_from_file() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOld.\n"
    );
    let content_file = dir.path().join("new_content.md");
    std::fs::write(&content_file, "Replacement text.").unwrap();

    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section",
                "--from-file", content_file.to_str().unwrap()])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Replacement text."));
    drop(dir);
}

#[test]
fn replace_preserve_children() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Parent\n\nParent content.\n\n### Child\n\nChild content.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Parent",
                "--content", "New parent content.", "--preserve-children"])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New parent content."));
    assert!(result.contains("### Child"));
    assert!(result.contains("Child content."));
    drop(dir);
}

#[test]
fn replace_warns_on_large_reduction() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nLine 1.\nLine 2.\nLine 3.\nLine 4.\nLine 5.\nLine 6.\nLine 7.\nLine 8.\nLine 9.\nLine 10.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "Short."])
        .assert()
        .success()
        .stdout(predicate::str::contains("⚠"));
    drop(dir);
}

#[test]
fn replace_no_change() {
    let content = "# Doc\n\n## Section\n\nContent.\n";
    let (dir, file) = common::temp_md_file(content);
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "Content."])
        .assert()
        .code(10)
        .stdout(predicate::str::contains("NO CHANGE"));
    drop(dir);
}

#[test]
fn replace_dry_run() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOld.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"))
        .stdout(predicate::str::contains("WOULD REPLACE"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Old."));
    drop(dir);
}

#[test]
fn replace_section_not_found() {
    let (dir, file) = common::temp_md_file("# Doc\n\n## Section\n\nContent.\n");
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Nonexistent", "--content", "X"])
        .assert()
        .code(1);
    drop(dir);
}

#[test]
fn replace_shows_before_after_metrics() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOld line 1.\nOld line 2.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "New line."])
        .assert()
        .success()
        .stdout(predicate::str::contains("was"))
        .stdout(predicate::str::contains("now"))
        .stdout(predicate::str::contains("lines,"))
        .stdout(predicate::str::contains("words"));
    drop(dir);
}

#[test]
fn replace_without_children_removes_them() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Parent\n\nParent content.\n\n### Child\n\nChild content.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Parent",
                "--content", "New parent content."])
        .assert()
        .success()
        .stdout(predicate::str::contains("⚠")); // warns about removed child

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New parent content."));
    assert!(!result.contains("### Child")); // child was removed
    drop(dir);
}

#[test]
fn replace_normalises_whitespace() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOld.\n\n## Other\n\nOther.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section", "--content", "New."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    // No triple blank lines
    assert!(!result.contains("\n\n\n"));
    // Ends with exactly one newline
    assert!(result.ends_with('\n'));
    assert!(!result.ends_with("\n\n"));
    drop(dir);
}

#[test]
fn replace_preamble_existing() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nOld preamble.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "New preamble."])
        .assert()
        .success()
        .stdout(predicate::str::contains("REPLACED"))
        .stdout(predicate::str::contains("_preamble"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New preamble."));
    assert!(!result.contains("Old preamble."));
    assert!(result.contains("# Heading")); // heading preserved
    assert!(result.contains("Content.")); // section content preserved
    drop(dir);
}

#[test]
fn replace_preamble_creates_when_absent() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "Created preamble."])
        .assert()
        .success()
        .stdout(predicate::str::contains("REPLACED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Created preamble."));
    assert!(result.contains("# Heading"));
    // Preamble should be between frontmatter and heading
    let preamble_pos = result.find("Created preamble.").unwrap();
    let heading_pos = result.find("# Heading").unwrap();
    assert!(preamble_pos < heading_pos);
    drop(dir);
}

#[test]
fn replace_preamble_noop() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nExisting.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "Existing."])
        .assert()
        .code(10)
        .stdout(predicate::str::contains("NO CHANGE"));
    drop(dir);
}

#[test]
fn replace_preamble_dry_run() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nOld.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "New.", "--dry-run"])
        .assert()
        .success()
        .stdout(predicate::str::contains("DRY RUN"))
        .stdout(predicate::str::contains("WOULD REPLACE"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Old.")); // file unchanged
    drop(dir);
}

#[test]
fn replace_preamble_no_frontmatter() {
    let (dir, file) = common::temp_md_file(
        "Old preamble text.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "New preamble."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New preamble."));
    assert!(!result.contains("Old preamble text."));
    drop(dir);
}

#[test]
fn replace_preamble_preserve_children_accepted() {
    // --preserve-children is accepted but has no effect (preamble has no children)
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nOld.\n\n# Heading\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble",
                "--content", "New.", "--preserve-children"])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("New."));
    drop(dir);
}

#[test]
fn replace_preamble_no_headings_document() {
    // Document with no headings — preamble is entire content
    let (dir, file) = common::temp_md_file(
        "Just some text.\nAnother line.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "_preamble", "--content", "Replaced."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Replaced."));
    assert!(!result.contains("Just some text."));
    drop(dir);
}
