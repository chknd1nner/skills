## API quick reference

| Method | Purpose |
|--------|---------|
| `memory.status()` | Repo info, dirty files, recent main log |
| `memory.fetch(path, return_mode, branch)` | `'content'`, `'file'`, or `'both'` |
| `memory.get_template(name)` | Load template by filename |
| `memory.commit(path, message, from_file=)` | Commit from local file to working branch |
| `memory.consolidate(files, message)` | Squash merge working → main |
| `memory.create_entity(name, type, tags, summary)` | New entity from template + manifest |
| `memory.get_manifest()` | Read entity manifest |

`commit(content=...)` exists in the API but is intentionally absent here — use the mdedit workflow for all existing content files.
