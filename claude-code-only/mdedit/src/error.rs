use std::fmt;

/// Exit codes per spec
#[derive(Debug, Clone, Copy)]
pub enum ExitCode {
    Success = 0,
    SectionNotFound = 1,
    AmbiguousMatch = 2,
    FileError = 3,
    ContentError = 4,
    ValidationFailure = 5,
    NoOp = 10,
}

/// A matched section for error messages
#[derive(Debug, Clone)]
pub struct SectionRef {
    pub heading: String,
    pub level: u8,
    pub line: usize,
    pub parent: Option<String>,
}

impl fmt::Display for SectionRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{} (H{}, line {})", self.heading, self.level, self.line)?;
        if let Some(parent) = &self.parent {
            write!(f, ", under \"{}\"", parent)?;
        }
        Ok(())
    }
}

#[derive(Debug)]
pub enum MdeditError {
    SectionNotFound {
        query: String,
        file: String,
        suggestions: Vec<SectionRef>,
    },
    AmbiguousMatch {
        query: String,
        file: String,
        matches: Vec<SectionRef>,
    },
    FileError(String),
    ContentError(String),
    ValidationFailures(Vec<ValidationIssue>),
    NoOp(String),
    InvalidOperation(String),
}

#[derive(Debug, Clone)]
pub enum Severity {
    Warning,
    Info,
}

#[derive(Debug, Clone)]
pub struct ValidationIssue {
    pub severity: Severity,
    pub line: usize,
    pub message: String,
}

impl MdeditError {
    pub fn exit_code(&self) -> i32 {
        match self {
            MdeditError::SectionNotFound { .. } => ExitCode::SectionNotFound as i32,
            MdeditError::AmbiguousMatch { .. } => ExitCode::AmbiguousMatch as i32,
            MdeditError::FileError(_) => ExitCode::FileError as i32,
            MdeditError::ContentError(_) => ExitCode::ContentError as i32,
            MdeditError::ValidationFailures(_) => ExitCode::ValidationFailure as i32,
            MdeditError::NoOp(_) => ExitCode::NoOp as i32,
            MdeditError::InvalidOperation(_) => ExitCode::ContentError as i32,
        }
    }
}

impl fmt::Display for MdeditError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            MdeditError::SectionNotFound { query, file, suggestions } => {
                writeln!(f, "ERROR: Section \"{}\" not found in {}", query, file)?;
                if !suggestions.is_empty() {
                    writeln!(f, "Did you mean?")?;
                    for s in suggestions {
                        writeln!(f, "  → {}", s)?;
                    }
                }
                Ok(())
            }
            MdeditError::AmbiguousMatch { query, file, matches } => {
                writeln!(f, "ERROR: \"{}\" matches {} sections in {}",
                    query, matches.len(), file)?;
                for m in matches {
                    writeln!(f, "  → {}", m)?;
                }
                writeln!(f, "Disambiguate with level prefix or path syntax")
            }
            MdeditError::FileError(msg) => write!(f, "ERROR: {}", msg),
            MdeditError::ContentError(msg) => write!(f, "ERROR: {}", msg),
            MdeditError::ValidationFailures(issues) => {
                let total = issues.len();
                writeln!(f, "INVALID: {} issues", total)?;
                for issue in issues {
                    let marker = match issue.severity {
                        Severity::Warning => "⚠",
                        Severity::Info => "ℹ",
                    };
                    writeln!(f, "  {} Line {}: {}", marker, issue.line, issue.message)?;
                }
                Ok(())
            }
            MdeditError::NoOp(msg) => write!(f, "NO CHANGE: {}", msg),
            MdeditError::InvalidOperation(msg) => write!(f, "ERROR: {}", msg),
        }
    }
}
