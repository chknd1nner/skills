# Continuity-Memory Unit Tests

Pytest tests for pure functions in `common/continuity-memory/scripts/memory_system.py`.

## Running

```bash
python3 -m pytest tests/continuity-memory/unit/ -v
```

## Structure

- `test_section_editing.py` — tests for `_list_sections`, `_find_section`, `_replace_section_content`, `_add_section_entry`, `_remove_section`
- `sample-memories/` — realistic fixture files (positions, methods, profile, etc.) used by tests

## Adding tests

- Use `load_sample('space/file.md')` to load fixtures from `sample-memories/`
- Tests skip automatically if `tree-sitter-markdown` is not installed
- Keep fixtures representative of real memory files — they double as documentation of the expected format
