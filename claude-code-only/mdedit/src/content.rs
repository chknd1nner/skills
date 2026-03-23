use crate::error::MdeditError;
use std::io::{self, IsTerminal, Read};

/// Resolve content from --content, --from-file, or stdin (in priority order)
pub fn resolve_content(
    content: Option<&str>,
    from_file: Option<&str>,
) -> Result<String, MdeditError> {
    if let Some(text) = content {
        return Ok(text.to_string());
    }
    if let Some(path) = from_file {
        return std::fs::read_to_string(path)
            .map_err(|e| MdeditError::ContentError(format!("--from-file not found: {} ({})", path, e)));
    }
    // Try stdin if not a TTY
    if !io::stdin().is_terminal() {
        let mut buf = String::new();
        io::stdin().read_to_string(&mut buf)
            .map_err(|e| MdeditError::ContentError(format!("Failed to read stdin: {}", e)))?;
        if !buf.is_empty() {
            return Ok(buf);
        }
    }
    Err(MdeditError::ContentError(
        "No content provided\nUse --content \"...\", --from-file <path>, or pipe to stdin".to_string()
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn content_from_flag() {
        let result = resolve_content(Some("hello world"), None).unwrap();
        assert_eq!(result, "hello world");
    }

    #[test]
    fn content_from_file() {
        let mut f = NamedTempFile::new().unwrap();
        write!(f, "file content").unwrap();
        let result = resolve_content(None, Some(f.path().to_str().unwrap())).unwrap();
        assert_eq!(result, "file content");
    }

    #[test]
    fn content_flag_takes_priority_over_file() {
        let mut f = NamedTempFile::new().unwrap();
        write!(f, "file content").unwrap();
        let result = resolve_content(Some("flag content"), Some(f.path().to_str().unwrap())).unwrap();
        assert_eq!(result, "flag content");
    }

    #[test]
    fn no_content_returns_error() {
        // In test context, stdin is a TTY (or not piped), so this should error
        let result = resolve_content(None, None);
        assert!(result.is_err());
    }
}
