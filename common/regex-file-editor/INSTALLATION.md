# Installation and Usage Guide

## Quick Start

This skill is ready to use immediately - no installation required beyond placing it in your `.claude/skills/` directory.

## File Structure

```
.claude/skills/regex-editing/
├── SKILL.md                         # Skill definition (auto-loaded by Claude)
├── README.md                        # Full documentation
├── INSTALLATION.md                  # This file
├── scripts/
│   └── regex_edit.py                # Executable script (chmod +x)
└── references/
    ├── EXAMPLES.md                  # Real-world examples
    └── PATTERNS.md                  # Common regex patterns
    └── backreference-guide.md       # $!N syntax guide
```

## Requirements

**Python 3.7+** (built into Claude Code's Ubuntu sandbox)

**No external dependencies** - uses Python standard library only:
- `re` - Regular expressions
- `os`, `pathlib` - File system operations
- `json` - JSON output
- `argparse` - CLI parsing
- `fnmatch` - Glob pattern matching

## Activation

Once placed in `.claude/skills/regex-editing/`, Claude will automatically:

1. **Detect the skill** via `SKILL.md`
2. **Load instructions** when regex editing is needed
3. **Invoke the script** via the commands in SKILL.md

## Manual Testing

You can test the script directly from the command line:

### Validate a Pattern
```bash
python scripts/regex_edit.py validate "function (.*?)\((.*?)\)"
```

### Search in File
```bash
python scripts/regex_edit.py search myfile.js "console\.log" --context=3
```

### Replace in File
```bash
python scripts/regex_edit.py replace myfile.js \
  "console\.log\((.*?)\)" \
  "logger.info($!1)"
```

### Search Across Files
```bash
python scripts/regex_edit.py search-files "TODO" \
  --include="**/*.py" \
  --exclude="**/test_*"
```

## Expected Output

All commands return JSON:

```json
{
  "status": "success",
  "operation": "replace",
  "file": "myfile.js",
  "matches_count": 1,
  "message": "Replaced 1 occurrence(s) in myfile.js"
}
```

## Usage in Claude Code

When you ask Claude to make file edits, the skill will automatically activate if:

1. The edit involves **regex patterns**
2. The edit is **token-intensive** (large code blocks)
3. You mention **regex**, **pattern**, or **multiple files**

Example prompts that trigger this skill:

- "Replace all `console.error` with `logger.error` in src/"
- "Find all TODO comments in Python files"
- "Update import statements from old-package to new-package"
- "Add async to all function definitions"

## Customization

### Adjusting Default Variables

Edit `SKILL.md` to change defaults:

```yaml
REGEX_MODE: true          # Use regex by default
ALLOW_MULTIPLE_MATCHES: false  # Safer default
CONTEXT_LINES: 3          # Lines of context in search results
ENCODING: utf-8           # File encoding
```

### Adding New Patterns

Add commonly-used patterns to `references/PATTERNS.md` for quick reference.

### Adding Examples

Extend `references/EXAMPLES.md` with project-specific examples.

## Troubleshooting

### Script Not Executable

```bash
chmod +x .claude/skills/regex-editing/scripts/regex_edit.py
```

### Python Version Issues

Check Python version:
```bash
python --version  # Should be 3.7+
```

### Pattern Syntax Errors

Use the validate command:
```bash
python scripts/regex_edit.py validate "your-pattern-here"
```

### File Encoding Issues

Specify encoding explicitly:
```bash
python scripts/regex_edit.py replace file.txt "pattern" "replacement" --encoding=latin-1
```

## Advanced Configuration

### Using Custom Python

If you need a specific Python version:

Edit the shebang in `scripts/regex_edit.py`:
```python
#!/usr/bin/env python3.11
```

### Performance Tuning

For very large codebases, consider:

1. **Use specific glob patterns** to reduce file count
2. **Search before replacing** to validate patterns
3. **Process files in batches** rather than all at once

## Learning Resources

1. **Start here**: `README.md` - Full feature documentation
2. **Learn backreferences**: `references/backreference-guide.md`
3. **See examples**: `references/EXAMPLES.md`
4. **Find patterns**: `references/PATTERNS.md`
5. **Understand cookbook**: `SKILL.md` - Scenario-based guide

## Support

This skill is extracted from [Serena](https://github.com/khulnasoft-lab/serena), an open-source coding agent toolkit.

For issues or questions:
- Check documentation files in this directory
- Review the Serena source code for advanced usage
- Consult regex documentation for pattern syntax

## License

Extracted from Serena, which is open source. Consult the original Serena repository for license information.
