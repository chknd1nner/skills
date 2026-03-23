use std::path::Path;

use crate::error::MdeditError;
use crate::parser;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Read the source from disk and parse it, returning both for manipulation.
fn read_and_parse(file: &str) -> Result<(String, crate::document::Document), MdeditError> {
    let source = std::fs::read_to_string(file)
        .map_err(|e| MdeditError::FileError(format!("Cannot read '{}': {}", file, e)))?;
    let doc = parser::parse(&source)
        .map_err(|e| MdeditError::FileError(format!("Parse error in '{}': {}", file, e)))?;
    Ok((source, doc))
}

/// Basename of a file path for display purposes.
fn basename(file: &str) -> &str {
    Path::new(file)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(file)
}

/// Extract the YAML body (the text between the opening and closing `---` lines)
/// from the full frontmatter block (which includes the delimiters).
fn extract_yaml_body(frontmatter_text: &str) -> &str {
    // frontmatter_text looks like "---\n...\n---\n"
    let after_open = frontmatter_text
        .strip_prefix("---")
        .unwrap_or(frontmatter_text);
    let after_newline = after_open.strip_prefix('\n').unwrap_or(after_open);
    // Find closing ---
    if let Some(close_idx) = after_newline.find("\n---") {
        &after_newline[..close_idx]
    } else if let Some(close_idx) = after_newline.find("---") {
        &after_newline[..close_idx]
    } else {
        after_newline
    }
}

/// Parse frontmatter YAML into an ordered map (preserving insertion order via BTreeMap by key).
/// We use serde_yaml::Value so we can handle arbitrary types.
fn parse_frontmatter_map(
    yaml_body: &str,
) -> Result<serde_yaml::Mapping, MdeditError> {
    let value: serde_yaml::Value = serde_yaml::from_str(yaml_body)
        .map_err(|e| MdeditError::ContentError(format!("Invalid YAML frontmatter: {}", e)))?;
    match value {
        serde_yaml::Value::Mapping(m) => Ok(m),
        serde_yaml::Value::Null => Ok(serde_yaml::Mapping::new()),
        _ => Err(MdeditError::ContentError(
            "Frontmatter is not a YAML mapping".to_string(),
        )),
    }
}

/// Serialize a serde_yaml::Mapping back to a YAML string without the trailing newline.
fn serialize_mapping(map: &serde_yaml::Mapping) -> Result<String, MdeditError> {
    let yaml = serde_yaml::to_string(map)
        .map_err(|e| MdeditError::ContentError(format!("Failed to serialize YAML: {}", e)))?;
    // serde_yaml produces a leading "---\n" header — strip it.
    let body = yaml
        .strip_prefix("---\n")
        .unwrap_or(&yaml)
        .trim_end_matches('\n');
    Ok(body.to_string())
}

/// Splice new frontmatter content into the source at the given byte range.
/// Returns the modified document source.
fn splice_frontmatter(
    source: &str,
    fm_range: std::ops::Range<usize>,
    new_yaml_body: &str,
) -> String {
    let before = &source[..fm_range.start];
    let after = &source[fm_range.end..];
    format!("{}---\n{}\n---\n{}", before, new_yaml_body, after)
}

/// Parse a value string: try JSON first (for arrays, numbers, booleans), then
/// fall back to treating the raw string as a plain YAML string scalar.
fn parse_value(raw: &str) -> serde_yaml::Value {
    // Try JSON parse first — this handles arrays, objects, numbers, booleans, and quoted strings.
    if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(raw) {
        return json_to_yaml(json_val);
    }
    // Fall back: treat as a plain string scalar.
    serde_yaml::Value::String(raw.to_string())
}

fn json_to_yaml(v: serde_json::Value) -> serde_yaml::Value {
    match v {
        serde_json::Value::Null => serde_yaml::Value::Null,
        serde_json::Value::Bool(b) => serde_yaml::Value::Bool(b),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                serde_yaml::Value::Number(serde_yaml::Number::from(i))
            } else if let Some(f) = n.as_f64() {
                serde_yaml::Value::Number(serde_yaml::Number::from(f))
            } else {
                serde_yaml::Value::String(n.to_string())
            }
        }
        serde_json::Value::String(s) => serde_yaml::Value::String(s),
        serde_json::Value::Array(arr) => {
            serde_yaml::Value::Sequence(arr.into_iter().map(json_to_yaml).collect())
        }
        serde_json::Value::Object(obj) => {
            let mut mapping = serde_yaml::Mapping::new();
            for (k, v) in obj {
                mapping.insert(serde_yaml::Value::String(k), json_to_yaml(v));
            }
            serde_yaml::Value::Mapping(mapping)
        }
    }
}

/// Render a YAML key (plain string keys are displayed without quotes).
fn key_display(val: &serde_yaml::Value) -> String {
    match val {
        serde_yaml::Value::String(s) => s.clone(),
        other => display_value(other),
    }
}

/// Render a serde_yaml::Value as a compact JSON-like string for display.
fn display_value(val: &serde_yaml::Value) -> String {
    match val {
        serde_yaml::Value::String(s) => format!("\"{}\"", s),
        serde_yaml::Value::Bool(b) => b.to_string(),
        serde_yaml::Value::Number(n) => n.to_string(),
        serde_yaml::Value::Null => "null".to_string(),
        serde_yaml::Value::Sequence(seq) => {
            let items: Vec<String> = seq.iter().map(display_value).collect();
            format!("[{}]", items.join(", "))
        }
        serde_yaml::Value::Mapping(m) => {
            let items: Vec<String> = m
                .iter()
                .map(|(k, v)| format!("{}: {}", display_value(k), display_value(v)))
                .collect();
            format!("{{{}}}", items.join(", "))
        }
        _ => format!("{:?}", val),
    }
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// `frontmatter show <file>` — display all fields
pub fn run_show(file: &str) -> Result<(), MdeditError> {
    let (source, doc) = read_and_parse(file)?;

    let fm_range = doc.frontmatter.as_ref().ok_or_else(|| {
        MdeditError::FileError(format!("No frontmatter found in {}", basename(file)))
    })?;

    let fm_text = &source[fm_range.start..fm_range.end];
    let yaml_body = extract_yaml_body(fm_text);
    let map = parse_frontmatter_map(yaml_body)?;

    println!("FRONTMATTER: {} — {} fields", basename(file), map.len());
    println!();
    for (k, v) in &map {
        let key_str = key_display(k);
        println!("  {}: {}", key_str, display_value(v));
    }

    Ok(())
}

/// `frontmatter get <file> <key>` — print the raw value of a single key
pub fn run_get(file: &str, key: &str) -> Result<(), MdeditError> {
    let (source, doc) = read_and_parse(file)?;

    let fm_range = doc.frontmatter.as_ref().ok_or_else(|| {
        MdeditError::FileError(format!("No frontmatter found in {}", basename(file)))
    })?;

    let fm_text = &source[fm_range.start..fm_range.end];
    let yaml_body = extract_yaml_body(fm_text);
    let map = parse_frontmatter_map(yaml_body)?;

    let yaml_key = serde_yaml::Value::String(key.to_string());
    match map.get(&yaml_key) {
        Some(val) => {
            // Pure value output for get — no quotes on strings, suitable for piping
            match val {
                serde_yaml::Value::String(s) => println!("{}", s),
                _ => println!("{}", display_value(val)),
            }
            Ok(())
        }
        None => {
            let available: Vec<String> = map
                .iter()
                .filter_map(|(k, _)| {
                    if let serde_yaml::Value::String(s) = k {
                        Some(s.clone())
                    } else {
                        None
                    }
                })
                .collect();
            Err(MdeditError::ContentError(format!(
                "Key \"{}\" not found in frontmatter. Available keys: {}",
                key,
                available.join(", ")
            )))
        }
    }
}

/// `frontmatter set <file> <key> <value> [--dry-run]`
pub fn run_set(file: &str, key: &str, value: &str, dry_run: bool) -> Result<(), MdeditError> {
    let (source, doc) = read_and_parse(file)?;

    let fm_range = doc.frontmatter.as_ref().ok_or_else(|| {
        MdeditError::FileError(format!("No frontmatter found in {}", basename(file)))
    })?;

    let fm_text = &source[fm_range.start..fm_range.end];
    let yaml_body = extract_yaml_body(fm_text);
    let mut map = parse_frontmatter_map(yaml_body)?;

    let yaml_key = serde_yaml::Value::String(key.to_string());
    let new_val = parse_value(value);

    let old_val = map.get(&yaml_key).cloned();
    map.insert(yaml_key, new_val.clone());

    let new_yaml_body = serialize_mapping(&map)?;

    // Build output display
    let old_display = old_val
        .as_ref()
        .map(display_value)
        .unwrap_or_else(|| "(not set)".to_string());
    let new_display = display_value(&new_val);

    if dry_run {
        println!("DRY RUN — no changes written");
        println!();
        println!("WOULD SET: {} (was {} → would be {})", key, old_display, new_display);
        println!();
        println!("---");
        for (k, v) in &map {
            let k_str = if let serde_yaml::Value::String(s) = k { s.as_str() } else { continue };
            if k_str == key {
                println!("→ {}: {}", k_str, display_value(v));
            } else {
                println!("  {}: {}", k_str, display_value(v));
            }
        }
        println!("---");
    } else {
        let new_source = splice_frontmatter(&source, fm_range.clone(), &new_yaml_body);
        std::fs::write(file, &new_source)
            .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

        println!("FRONTMATTER SET: {} (was {} → now {})", key, old_display, new_display);
        println!();
        println!("---");
        for (k, v) in &map {
            let k_str = if let serde_yaml::Value::String(s) = k { s.as_str() } else { continue };
            if k_str == key {
                println!("→ {}: {}", k_str, display_value(v));
            } else {
                println!("  {}: {}", k_str, display_value(v));
            }
        }
        println!("---");
    }

    Ok(())
}

/// `frontmatter delete <file> <key> [--dry-run]`
pub fn run_delete(file: &str, key: &str, dry_run: bool) -> Result<(), MdeditError> {
    let (source, doc) = read_and_parse(file)?;

    let fm_range = doc.frontmatter.as_ref().ok_or_else(|| {
        MdeditError::FileError(format!("No frontmatter found in {}", basename(file)))
    })?;

    let fm_text = &source[fm_range.start..fm_range.end];
    let yaml_body = extract_yaml_body(fm_text);
    let mut map = parse_frontmatter_map(yaml_body)?;

    let yaml_key = serde_yaml::Value::String(key.to_string());
    if !map.contains_key(&yaml_key) {
        let available: Vec<String> = map
            .iter()
            .filter_map(|(k, _)| {
                if let serde_yaml::Value::String(s) = k {
                    Some(s.clone())
                } else {
                    None
                }
            })
            .collect();
        return Err(MdeditError::ContentError(format!(
            "Key \"{}\" not found in frontmatter. Available keys: {}",
            key,
            available.join(", ")
        )));
    }

    map.remove(&yaml_key);
    let new_yaml_body = serialize_mapping(&map)?;

    if dry_run {
        println!("DRY RUN — no changes written");
        println!();
        println!("WOULD DELETE: {}", key);
        println!();
        println!("---");
        for (k, v) in &map {
            let k_str = if let serde_yaml::Value::String(s) = k { s.as_str() } else { continue };
            println!("  {}: {}", k_str, display_value(v));
        }
        println!("---");
    } else {
        let new_source = splice_frontmatter(&source, fm_range.clone(), &new_yaml_body);
        std::fs::write(file, &new_source)
            .map_err(|e| MdeditError::FileError(format!("Cannot write '{}': {}", file, e)))?;

        println!("FRONTMATTER DELETED: {}", key);
        println!();
        println!("---");
        for (k, v) in &map {
            let k_str = if let serde_yaml::Value::String(s) = k { s.as_str() } else { continue };
            println!("  {}: {}", k_str, display_value(v));
        }
        println!("---");
    }

    Ok(())
}
