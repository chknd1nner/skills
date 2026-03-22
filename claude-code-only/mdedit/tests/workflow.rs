mod common;
use assert_cmd::Command;
use predicates::prelude::*;

/// Test the file-mode workflow: extract -> edit -> replace
#[test]
fn file_mode_workflow() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## Section\n\nOriginal content.\n\n## Other\n\nOther content.\n"
    );
    let temp_section = dir.path().join("section.md");

    // Step 1: Extract
    Command::cargo_bin("mdedit").unwrap()
        .args(&["extract", file.to_str().unwrap(), "Section",
                "--to-file", temp_section.to_str().unwrap()])
        .assert()
        .success();

    // Step 2: Edit the temp file (simulating LLM Edit tool)
    let content = std::fs::read_to_string(&temp_section).unwrap();
    let modified = content.replace("Original", "Modified");
    std::fs::write(&temp_section, modified).unwrap();

    // Step 3: Replace from file
    Command::cargo_bin("mdedit").unwrap()
        .args(&["replace", file.to_str().unwrap(), "Section",
                "--from-file", temp_section.to_str().unwrap()])
        .assert()
        .success()
        .stdout(predicate::str::contains("REPLACED"));

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("Modified content."));
    assert!(result.contains("Other content.")); // other section untouched
    drop(dir);
}

/// Test multi-command workflow: insert -> append -> rename
#[test]
fn multi_command_workflow() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## First\n\nFirst content.\n\n## Last\n\nLast content.\n"
    );

    // Insert a new section
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--after", "First", "--heading", "## Middle", "--content", "Middle content."])
        .assert()
        .success();

    // Append to the new section
    Command::cargo_bin("mdedit").unwrap()
        .args(&["append", file.to_str().unwrap(), "Middle", "--content", "More middle."])
        .assert()
        .success();

    // Rename it
    Command::cargo_bin("mdedit").unwrap()
        .args(&["rename", file.to_str().unwrap(), "Middle", "Central"])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("## Central"));
    assert!(result.contains("Middle content."));
    assert!(result.contains("More middle."));
    // Verify ordering
    let first_pos = result.find("## First").unwrap();
    let central_pos = result.find("## Central").unwrap();
    let last_pos = result.find("## Last").unwrap();
    assert!(first_pos < central_pos);
    assert!(central_pos < last_pos);
    drop(dir);
}
