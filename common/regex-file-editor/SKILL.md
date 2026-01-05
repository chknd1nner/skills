---
name: regex-file-editor
description: Advanced token-efficient regex-based file editing with custom backreferences, ambiguity detection, and multi-file search. Use when you need to edit files using regex patterns, especially for large multi-line replacements where quoting the entire content would waste tokens.
---

# Regex File Editor

Token-efficient file editing using advanced regex patterns.

This skill enables you to perform sophisticated file edits using regex patterns with minimal token usage. Instead of quoting large sections of text/markdown/code to replace, you can use concise regex patterns with wildcards.

## Key Features

- **Token Efficiency**: Replace large multi-line sections using `.*?` wildcards instead of quoting entire blocks
- **Custom Backreference Syntax**: Use `$!1`, `$!2`, `$!3` instead of `\1`, `\2` to avoid conflicts with dollar signs in code
- **Ambiguity Detection**: Automatically detects when regex patterns match overlapping content
- **Multi-file Search**: Search across files with glob pattern filtering
- **Safe Replacements**: Validates match counts before applying changes

## Variables

```
REGEX_MODE: true
ALLOW_MULTIPLE_MATCHES: false
CONTEXT_LINES: 3
ENCODING: utf-8
```

## Instructions

1. **Before Any Replacement**:
   - ALWAYS run a search first to preview matches
   - Verify the pattern matches exactly what you intend to replace
   - Check for ambiguity warnings

2. **Using Custom Backreferences**:
   - In replacement strings, use `$!1`, `$!2`, `$!3` for capture groups
   - If backreferences behave unexpectedly, consult `references/edge-cases.md`

3. **Working with Large Code Blocks**:
   - Use non-greedy wildcards `.*?` to match sections you don't need to quote
   - Example: `function foo\(.*?\).*?\{.*?return.*?\}` matches an entire function body

4. **Multi-file Operations**:
   - Use glob patterns to filter files: `--include="**/*.py"` or `--exclude="**/test_*"`
   - Brace expansion supported: `--include="**/*.{js,ts,jsx,tsx}"`

## Workflow

Sequential steps for safe regex-based file editing:

1. **Understand the edit requirement** - Identify what needs to be changed
2. **Validate the regex pattern** - Run `python scripts/regex_edit.py validate <pattern>` to check syntax
3. **Search before replacing** - Preview matches with the search command
4. **Review ambiguity warnings** - If pattern is ambiguous, make it more specific
5. **Execute replacement** - Run replace command with validated pattern
6. **Verify via diff** - The response includes a unified diff showing exactly what changed. Trust it.

> **Do not re-read the file after a successful replacement.** The `diff` field in the response shows the exact changes made. Re-reading the file negates the token savings this tool provides.

## Cookbook

### Scenario 1: Simple Single-File Replacement

- **IF**: User wants to replace a pattern in one file AND the pattern has a single unique match
- **THEN**: Follow this approach:
  1. Search to preview: `python scripts/regex_edit.py search <file> "<pattern>" --context=3`
  2. Review the matches to ensure they're correct
  3. Replace: `python scripts/regex_edit.py replace <file> "<pattern>" "<replacement>"`
- **EXAMPLES**:
  - "Replace `console.error` with `console.log` in main.js"
  - "Change variable name from `oldName` to `newName` in utils.py"
  - "Update import statement from `old-package` to `new-package`"

### Scenario 2: Multi-Line Replacement with Wildcards (Token Saver!)

- **IF**: User needs to replace a large code block AND quoting the entire block would waste tokens
- **THEN**: Follow this approach:
  1. Construct a regex with `.*?` wildcards for sections you don't need to quote
  2. Use capture groups `(...)` for parts you want to preserve
  3. Search first: `python scripts/regex_edit.py search <file> "<pattern>"`
  4. Replace using `$!1`, `$!2` backreferences: `python scripts/regex_edit.py replace <file> "<pattern>" "<replacement with $!1>"`
- **EXAMPLES**:
  - "Replace try-catch block keeping the variable name: `catch \(($!1)\) \{.*?\}` → `catch ($!1) { logger.error($!1); }`"
  - "Update function signature preserving the name: `function ($!1)\(x\)` → `function $!1(x, y)`"
  - "Modify class definition keeping class name: `class ($!1).*?\{.*?constructor.*?\}` → new implementation"

### Scenario 3: Replace Multiple Occurrences

- **IF**: User wants to replace a pattern that appears multiple times in a file
- **THEN**: Follow this approach:
  1. Search to see all matches: `python scripts/regex_edit.py search <file> "<pattern>"`
  2. Count matches and verify they're all intended targets
  3. Replace with `--allow-multiple`: `python scripts/regex_edit.py replace <file> "<pattern>" "<replacement>" --allow-multiple`
- **EXAMPLES**:
  - "Replace all `var` declarations with `let` in legacy.js"
  - "Update all API endpoints from `http://` to `https://`"
  - "Change all `console.log` statements to use a logger"

### Scenario 4: Multi-File Pattern Search

- **IF**: User needs to find a pattern across multiple files
- **THEN**: Follow this approach:
  1. Determine appropriate glob filters for the file types
  2. Run: `python scripts/regex_edit.py search-files "<pattern>" --include="<glob>" --exclude="<exclude-glob>"`
  3. Review matches across files
  4. For replacements, process files individually using Scenario 1 or 2
- **EXAMPLES**:
  - "Find all TODO comments in Python files: `search-files 'TODO:.*' --include='**/*.py'`"
  - "Locate all API endpoints in TypeScript: `search-files 'app\.(get|post|put|delete)' --include='**/*.{ts,tsx}'`"
  - "Find hardcoded credentials: `search-files 'API_KEY\s*=\s*[\"'].*?[\"']' --exclude='**/test_*'`"

### Scenario 5: Complex Pattern with Backreferences

- **IF**: User needs to preserve parts of matched text AND reorder or reuse them in replacement
- **THEN**: Follow this approach:
  1. Design pattern with capture groups `(...)` for each part to preserve
  2. Use `$!1`, `$!2`, etc. in replacement to reference captured groups
  3. Search first to validate captures
  4. Replace with backreference-enabled replacement string
- **EXAMPLES**:
  - "Swap function parameters: `function foo\((.*?), (.*?)\)` → `function foo($!2, $!1)`"
  - "Reformat date strings: `(\d{2})/(\d{2})/(\d{4})` → `$!3-$!1-$!2`"
  - "Extract and reuse class names: `class (.*?) extends (.*?) \{` → `class $!1 /* formerly extended $!2 */ {`"
- **ON ERROR**: Consult `references/edge-cases.md` for group numbering and troubleshooting

### Scenario 6: Literal String Replacement (No Regex)

- **IF**: User wants exact string matching without regex interpretation
- **THEN**: Follow this approach:
  1. Use `--mode=literal` to escape regex special characters automatically
  2. Run: `python scripts/regex_edit.py replace <file> "<exact-string>" "<replacement>" --mode=literal`
- **EXAMPLES**:
  - "Replace exact string with special chars: `$price = $10.00` → `$price = $15.00`"
  - "Update literal regex pattern in docs: `pattern: .*?` → `pattern: .+?`"
  - "Change exact URL with query params: `api.com/v1?key=123&type=json` → new URL"

### Scenario 7: Validate Pattern Before Use

- **IF**: User has a complex regex pattern AND wants to ensure it's syntactically valid
- **THEN**: Follow this approach:
  1. Run: `python scripts/regex_edit.py validate "<pattern>"`
  2. Check JSON output for validation status
  3. If invalid, review error message and fix pattern
  4. Once valid, proceed with search or replace
- **EXAMPLES**:
  - "Validate complex pattern: `validate 'catch \(error\) \{.*?console\.error\(.*?\);.*?\}'`"
  - "Check lookahead syntax: `validate '(?<=function ).*?(?=\()'`"
  - "Verify backreference pattern: `validate '([\"']).*?\1'`"

## Tips for Token Efficiency

1. **Use Wildcards**: Replace `function foo() { [100 lines of code] }` with `function foo\(\).*?\}` (saves hundreds of tokens!)
2. **Non-Greedy Matching**: Always use `.*?` instead of `.*` for better control
3. **Preview First**: The search command helps you avoid costly retry iterations
4. **Specific Patterns**: More specific patterns = fewer ambiguity errors = fewer retries
5. **Backreferences**: Preserve existing content instead of re-typing it

## Output Format
All commands return JSON for easy parsing:

```json{
  "status": "success",
  "operation": "replace",
  "file": "path/to/file.py",
  "matches_count": 1,
  "message": "Replaced 1 occurrence(s) in path/to/file.py",
  "diff": "--- a/path/to/file.py\n+++ b/path/to/file.py\n@@ -1,3 +1,3 @@\n-old line\n+new line\n context\n"
}
```

## Error Handling

The script provides clear error messages for common issues:

- **No matches found**: Pattern didn't match anything in the file
- **Multiple matches**: Pattern matched more than once (use `--allow-multiple` if intended)
- **Ambiguous pattern**: Pattern matches overlapping content (refine the pattern)
- **Invalid regex**: Pattern syntax error (use `validate` command to test)
- **Backreference issues**: Consult `references/edge-cases.md` for group numbering and troubleshooting

## Reference Materials

- **`references/patterns.md`**: Regex patterns by language (lookup table)
- **`references/edge-cases.md`**: Troubleshooting backreferences and errors