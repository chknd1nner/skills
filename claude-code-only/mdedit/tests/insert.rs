mod common;
use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn insert_after_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## First\n\nFirst content.\n\n## Third\n\nThird content.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--after", "First", "--heading", "## Second", "--content", "Second content."])
        .assert()
        .success()
        .stdout(predicate::str::contains("INSERTED"));

    let result = std::fs::read_to_string(&file).unwrap();
    let first_pos = result.find("## First").unwrap();
    let second_pos = result.find("## Second").unwrap();
    let third_pos = result.find("## Third").unwrap();
    assert!(first_pos < second_pos);
    assert!(second_pos < third_pos);
    drop(dir);
}

#[test]
fn insert_before_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## First\n\nContent.\n\n## Second\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--before", "Second", "--heading", "## Middle", "--content", "Middle content."])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    let first_pos = result.find("## First").unwrap();
    let middle_pos = result.find("## Middle").unwrap();
    let second_pos = result.find("## Second").unwrap();
    assert!(first_pos < middle_pos);
    assert!(middle_pos < second_pos);
    drop(dir);
}

#[test]
fn insert_warns_on_level_mismatch() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## First\n\nContent.\n\n## Second\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--after", "First", "--heading", "### Wrong Level"])
        .assert()
        .success()
        .stdout(predicate::str::contains("\u{26a0}"));
    drop(dir);
}

#[test]
fn insert_without_content_creates_empty_section() {
    let (dir, file) = common::temp_md_file(
        "# Doc\n\n## First\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--after", "First", "--heading", "## Empty New"])
        .assert()
        .success();

    let result = std::fs::read_to_string(&file).unwrap();
    assert!(result.contains("## Empty New"));
    drop(dir);
}

#[test]
fn insert_requires_after_or_before() {
    let (dir, file) = common::temp_md_file("# Doc\n");
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(), "--heading", "## New"])
        .assert()
        .failure(); // clap should enforce this
    drop(dir);
}

#[test]
fn insert_after_preamble() {
    let (dir, file) = common::temp_md_file(
        "---\ntitle: Test\n---\n\nPreamble text.\n\n## First\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--after", "_preamble", "--heading", "## New Section", "--content", "New content."])
        .assert()
        .success()
        .stdout(predicate::str::contains("INSERTED"));

    let result = std::fs::read_to_string(&file).unwrap();
    let preamble_pos = result.find("Preamble text.").unwrap();
    let new_pos = result.find("## New Section").unwrap();
    let first_pos = result.find("## First").unwrap();
    assert!(preamble_pos < new_pos);
    assert!(new_pos < first_pos);
    drop(dir);
}

#[test]
fn insert_before_preamble_is_invalid() {
    let (dir, file) = common::temp_md_file(
        "Preamble.\n\n## Section\n\nContent.\n"
    );
    Command::cargo_bin("mdedit").unwrap()
        .args(&["insert", file.to_str().unwrap(),
                "--before", "_preamble", "--heading", "## New"])
        .assert()
        .failure()
        .stderr(predicate::str::contains("not valid"));
    drop(dir);
}
