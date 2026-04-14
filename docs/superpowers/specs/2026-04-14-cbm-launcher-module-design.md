# CBM Launcher Module Design

**Date:** 2026-04-14  
**Status:** Approved  

## Overview

Integrate codebase-memory-mcp (CBM) into the modular launcher so sessions can selectively enable CBM via a TUI toggle. When enabled, the launcher injects a code discovery prompt and loads the CBM MCP server via `--mcp-config`.

## Goals

1. Toggle CBM on/off per session via launcher TUI
2. Inject prompt nudges directing agent to use CBM tools before Grep/Glob/Read
3. Dynamically load CBM MCP server only when enabled
4. Establish pattern for future modules that contribute MCP servers

## Non-Goals

- Hook-based enforcement (PreToolUse gate) — relying on prompt nudges only
- Automatic index detection — agent discovers via `index_status` if needed
- Managing CBM installation — assumes binary already on PATH

## Design

### Module Interface Extension

Add a fourth function to the module interface:

```python
def build_mcp_entries(env: dict, selections: dict) -> list[dict]:
    """Return MCP server entries this module contributes.
    
    Each entry is a dict with:
    - name: str — server name (key in mcpServers)
    - type: str — "stdio" | "http" | "sse"
    - command: str — path to binary (for stdio)
    - args: list[str] — command arguments (optional)
    - env: dict — environment variables (optional)
    
    Returns empty list if module is disabled or contributes no MCPs.
    """
```

Existing modules without this function are treated as contributing no MCP entries (backward compatible via `hasattr()` check).

### CBM Module Structure

```
launcher/modules/codebase-memory-mcp/
├── module.py
├── prompts/
│   └── code-discovery.md
└── references/
    ├── workflows.md
    ├── cypher-examples.md
    └── tool-reference.md
```

### module.py

```python
"""Codebase-Memory MCP module for the Claude Code launcher."""

import shutil
from pathlib import Path

MODULE_DIR = Path(__file__).parent
PROMPTS_DIR = MODULE_DIR / "prompts"
REFERENCES_DIR = MODULE_DIR / "references"


def check_dependencies(env: dict) -> dict:
    """Check if codebase-memory-mcp binary is available."""
    binary_path = shutil.which("codebase-memory-mcp")
    
    if not binary_path:
        return {
            "available": False,
            "name": "Codebase-Memory MCP",
            "reason": "codebase-memory-mcp not found on PATH",
        }
    
    return {
        "available": True,
        "name": "Codebase-Memory MCP",
        "reason": None,
        "binary_path": binary_path,  # stash for build_mcp_entries
    }


def build_tui_section(env: dict, saved_state: dict) -> list:
    """Return TUI items — single enable toggle."""
    return [
        {
            "type": "toggle",
            "label": "Codebase-Memory MCP",
            "key": "enabled",
            "default": saved_state.get("enabled", True),
            "group": "master",
        }
    ]


def build_prompt(env: dict, selections: dict) -> str:
    """Return code discovery prompt with absolute path to references."""
    prompt_file = PROMPTS_DIR / "code-discovery.md"
    if not prompt_file.exists():
        return ""
    
    content = prompt_file.read_text()
    # Inject absolute path to references directory
    references_path = str(REFERENCES_DIR.resolve())
    content = content.replace("{{REFERENCES_PATH}}", references_path)
    
    return content


def build_mcp_entries(env: dict, selections: dict) -> list[dict]:
    """Return CBM MCP server entry."""
    binary_path = shutil.which("codebase-memory-mcp")
    if not binary_path:
        return []
    
    return [
        {
            "name": "codebase-memory-mcp",
            "type": "stdio",
            "command": binary_path,
            "args": [],
            "env": {},
        }
    ]
```

### Prompt Content

**prompts/code-discovery.md** (~200 tokens):

```markdown
# Codebase Memory — Code Discovery Protocol

For code exploration in this repository, use codebase-memory-mcp tools BEFORE 
Grep/Glob/Read. The graph returns precise structural results in ~500 tokens 
vs ~80K for grep.

## Quick Decision Matrix

| Question | Tool |
|----------|------|
| Who calls X? | `trace_path(direction="inbound")` |
| What does X call? | `trace_path(direction="outbound")` |
| Find by name pattern | `search_graph(name_pattern="...")` |
| Dead code | `search_graph(max_degree=0, exclude_entry_points=true)` |
| Read source | `get_code_snippet(qualified_name)` |
| Text/config search | `search_code` or Grep (fallback) |

If the project is not indexed, run `index_repository` first.

For detailed workflows, Cypher examples, and tool reference, see:
{{REFERENCES_PATH}}
```

### Reference Files

Content sourced from the skill section in `launcher/cbm-hooks-reference.md`:

| File | Sections to include |
|------|---------------------|
| `workflows.md` | "Exploration Workflow", "Tracing Workflow", "Quality Analysis" |
| `cypher-examples.md` | "Cypher Examples (for query_graph)" |
| `tool-reference.md` | "14 MCP Tools", "Edge Types", "Gotchas" |

### Launcher Changes

**launcher.py:**

1. Add `collect_mcp_entries()` function:

```python
def collect_mcp_entries(modules: list, module_states: dict, env: dict) -> dict:
    """Collect MCP server entries from all enabled modules.
    
    Returns dict in mcpServers format: {"server-name": {config...}, ...}
    """
    mcp_servers = {}
    for mod_info in modules:
        mod = mod_info["module"]
        mod_key = mod_info["name"].lower().replace(" ", "_")
        mod_state = module_states.get(mod_key, {})
        
        if not mod_state.get("enabled", False):
            continue
            
        if hasattr(mod, "build_mcp_entries"):
            try:
                entries = mod.build_mcp_entries(env, mod_state)
                for entry in entries:
                    name = entry.pop("name")
                    mcp_servers[name] = entry
            except Exception as e:
                print(f"Warning: {mod_info['name']} failed to build MCP entries: {e}")
    
    return mcp_servers
```

2. Expand main() to collect MCP entries after prompt fragments (Step 5)

3. Write MCP config and add `--mcp-config` flag (Steps 7-8):

```python
# After assembling prompt
mcp_servers = collect_mcp_entries(modules, module_states, env)
mcp_path = None
if mcp_servers:
    mcp_path = write_mcp_config({"mcpServers": mcp_servers})

# In claude_args construction
if mcp_path:
    claude_args.extend(["--mcp-config", mcp_path])
```

**prompt_builder.py:**

Add `write_mcp_config()` function:

```python
import json
import os
import tempfile

def write_mcp_config(config: dict) -> str:
    """Write MCP config to temp file, return path.
    
    Args:
        config: dict with mcpServers key
        
    Returns:
        Path to temp JSON file
    """
    fd, path = tempfile.mkstemp(suffix=".json", prefix="claude-mcp-")
    with os.fdopen(fd, "w") as f:
        json.dump(config, f, indent=2)
    
    return path
```

## Post-Implementation

Remove CBM from `~/.claude.json` so launcher fully controls MCP loading:

```bash
# Edit ~/.claude.json and remove codebase-memory-mcp from mcpServers
```

## Files Changed

**Create:**
- `launcher/modules/codebase-memory-mcp/module.py`
- `launcher/modules/codebase-memory-mcp/prompts/code-discovery.md`
- `launcher/modules/codebase-memory-mcp/references/workflows.md`
- `launcher/modules/codebase-memory-mcp/references/cypher-examples.md`
- `launcher/modules/codebase-memory-mcp/references/tool-reference.md`

**Modify:**
- `launcher/launcher.py` — add `collect_mcp_entries()`, expand main()
- `launcher/prompt_builder.py` — add `write_mcp_config()`

## Testing

1. Run launcher with CBM toggle enabled — verify MCP loads and prompt injected
2. Run launcher with CBM toggle disabled — verify no MCP, no prompt
3. Verify backward compatibility — memory module still works (no `build_mcp_entries`)
4. Test in session — verify agent uses CBM tools for code exploration

## Open Questions

None — design approved.
