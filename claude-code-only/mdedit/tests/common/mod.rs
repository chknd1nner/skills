use std::path::PathBuf;

pub fn fixture_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join(name)
}

pub fn fixture_path_str(name: &str) -> String {
    fixture_path(name).to_string_lossy().to_string()
}

/// Create a temp directory with a markdown file, returning (dir, file_path)
pub fn temp_md_file(content: &str) -> (tempfile::TempDir, PathBuf) {
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("test.md");
    std::fs::write(&file, content).unwrap();
    (dir, file)
}
