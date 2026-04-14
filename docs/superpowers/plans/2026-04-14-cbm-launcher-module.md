# CBM Launcher Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a codebase-memory-mcp module to the launcher that toggles CBM on/off, injects code discovery prompts, and dynamically loads the CBM MCP server.

**Architecture:** Extend the launcher's module interface with `build_mcp_entries()` for MCP server contributions. The CBM module implements all four interface functions. The launcher collects MCP entries from enabled modules, writes a temp JSON config, and passes `--mcp-config` to claude.

**Tech Stack:** Python 3.11+, tempfile, shutil, json

---

## File Structure

**Create:**
- `launcher/modules/codebase_memory_mcp/module.py` — four-function module interface
- `launcher/modules/codebase_memory_mcp/prompts/code-discovery.md` — system prompt nudge (~200 tokens)
- `launcher/modules/codebase_memory_mcp/references/workflows.md` — exploration/tracing workflows
- `launcher/modules/codebase_memory_mcp/references/cypher-examples.md` — query_graph examples
- `launcher/modules/codebase_memory_mcp/references/tool-reference.md` — 14 tools, edge types, gotchas

**Modify:**
- `launcher/prompt_builder.py` — add `write_mcp_config()`
- `launcher/launcher.py` — add `collect_mcp_entries()`, expand main() steps 5→8

---

### Task 1: Add write_mcp_config to prompt_builder

**Files:**
- Modify: `launcher/prompt_builder.py`
- Test: `launcher/tests/test_prompt_builder.py`

- [ ] **Step 1: Write the failing test**

Create test file:

```python
"""Tests for prompt_builder module."""

import json
import os
import pytest
from launcher.prompt_builder import write_mcp_config


def test_write_mcp_config_creates_json_file():
    config = {"mcpServers": {"test-server": {"command": "/usr/bin/test"}}}
    path = write_mcp_config(config)
    
    assert path.endswith(".json")
    assert os.path.exists(path)
    
    with open(path) as f:
        written = json.load(f)
    
    assert written == config
    os.unlink(path)


def test_write_mcp_config_with_nested_config():
    config = {
        "mcpServers": {
            "server-a": {"command": "/bin/a", "args": ["--flag"], "env": {"KEY": "val"}},
            "server-b": {"type": "stdio", "command": "/bin/b"},
        }
    }
    path = write_mcp_config(config)
    
    with open(path) as f:
        written = json.load(f)
    
    assert written["mcpServers"]["server-a"]["args"] == ["--flag"]
    assert written["mcpServers"]["server-b"]["type"] == "stdio"
    os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest launcher/tests/test_prompt_builder.py -v`
Expected: FAIL with "cannot import name 'write_mcp_config'"

- [ ] **Step 3: Write minimal implementation**

Add to `launcher/prompt_builder.py` after the imports:

```python
import json


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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest launcher/tests/test_prompt_builder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add launcher/prompt_builder.py launcher/tests/test_prompt_builder.py
git commit -m "$(cat <<'EOF'
feat(launcher): add write_mcp_config for MCP server configuration

Writes MCP server config dict to a temp JSON file for --mcp-config flag.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add collect_mcp_entries to launcher

**Files:**
- Modify: `launcher/launcher.py`
- Test: `launcher/tests/test_launcher.py`

- [ ] **Step 1: Write the failing test**

Create test file:

```python
"""Tests for launcher module."""

import pytest
from launcher.launcher import collect_mcp_entries


class MockModuleWithMCP:
    @staticmethod
    def build_mcp_entries(env, selections):
        return [
            {"name": "test-mcp", "type": "stdio", "command": "/bin/test", "args": [], "env": {}}
        ]


class MockModuleWithoutMCP:
    pass


class MockModuleWithMultipleMCP:
    @staticmethod
    def build_mcp_entries(env, selections):
        return [
            {"name": "mcp-a", "type": "stdio", "command": "/bin/a"},
            {"name": "mcp-b", "type": "http", "command": "http://localhost:8080"},
        ]


def test_collect_mcp_entries_from_enabled_module():
    modules = [{"name": "Test Module", "module": MockModuleWithMCP}]
    module_states = {"test_module": {"enabled": True}}
    
    result = collect_mcp_entries(modules, module_states, {})
    
    assert "test-mcp" in result
    assert result["test-mcp"]["type"] == "stdio"
    assert result["test-mcp"]["command"] == "/bin/test"


def test_collect_mcp_entries_skips_disabled_module():
    modules = [{"name": "Test Module", "module": MockModuleWithMCP}]
    module_states = {"test_module": {"enabled": False}}
    
    result = collect_mcp_entries(modules, module_states, {})
    
    assert result == {}


def test_collect_mcp_entries_skips_module_without_build_mcp_entries():
    modules = [{"name": "Legacy Module", "module": MockModuleWithoutMCP}]
    module_states = {"legacy_module": {"enabled": True}}
    
    result = collect_mcp_entries(modules, module_states, {})
    
    assert result == {}


def test_collect_mcp_entries_handles_multiple_servers():
    modules = [{"name": "Multi MCP", "module": MockModuleWithMultipleMCP}]
    module_states = {"multi_mcp": {"enabled": True}}
    
    result = collect_mcp_entries(modules, module_states, {})
    
    assert "mcp-a" in result
    assert "mcp-b" in result
    assert result["mcp-a"]["command"] == "/bin/a"
    assert result["mcp-b"]["type"] == "http"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest launcher/tests/test_launcher.py -v`
Expected: FAIL with "cannot import name 'collect_mcp_entries'"

- [ ] **Step 3: Write minimal implementation**

Add to `launcher/launcher.py` after `selections_to_module_state`:

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
                    entry = entry.copy()  # Don't mutate original
                    name = entry.pop("name")
                    mcp_servers[name] = entry
            except Exception as e:
                print(f"Warning: {mod_info['name']} failed to build MCP entries: {e}")
    
    return mcp_servers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest launcher/tests/test_launcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add launcher/launcher.py launcher/tests/test_launcher.py
git commit -m "$(cat <<'EOF'
feat(launcher): add collect_mcp_entries for module MCP contributions

Collects MCP server entries from enabled modules that implement
build_mcp_entries(). Backward compatible with modules that don't.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Integrate MCP collection into main()

**Files:**
- Modify: `launcher/launcher.py`

- [ ] **Step 1: Add import for write_mcp_config**

At the top of `launcher/launcher.py`, change:

```python
from launcher.prompt_builder import assemble_prompt
```

to:

```python
from launcher.prompt_builder import assemble_prompt, write_mcp_config
```

- [ ] **Step 2: Expand main() to collect MCP entries and pass --mcp-config**

Replace the section from `# Step 6: Parse user flags` to the end of main() with:

```python
    # Step 6: Collect MCP entries from enabled modules
    mcp_servers = collect_mcp_entries(modules, module_states, env)

    # Step 7: Parse user flags
    args = parse_args(sys.argv[1:])

    # Step 8: Assemble system prompt
    prompt_path = assemble_prompt(fragments, args["user_appends"])

    # Step 9: Write MCP config if any modules contributed servers
    mcp_path = None
    if mcp_servers:
        mcp_path = write_mcp_config({"mcpServers": mcp_servers})

    # Step 10: Launch claude
    claude_args = ["claude"]
    if prompt_path:
        claude_args.extend(["--append-system-prompt-file", prompt_path])
    if mcp_path:
        claude_args.extend(["--mcp-config", mcp_path])
    claude_args.extend(args["passthrough"])

    mcp_count = len(mcp_servers)
    if mcp_count:
        print(f"Launching claude with {len(fragments)} module(s), {mcp_count} MCP server(s)...")
    else:
        print(f"Launching claude with {len(fragments)} module(s)...")
    os.execvp("claude", claude_args)
```

- [ ] **Step 3: Verify launcher still runs**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m launcher.launcher --help`
Expected: Claude help output (launcher passes through --help to claude)

- [ ] **Step 4: Commit**

```bash
git add launcher/launcher.py
git commit -m "$(cat <<'EOF'
feat(launcher): integrate MCP collection into main()

Modules that implement build_mcp_entries() now have their MCP servers
loaded via --mcp-config. Step numbers updated to reflect new flow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Create CBM module skeleton with check_dependencies

**Files:**
- Create: `launcher/modules/codebase_memory_mcp/__init__.py`
- Create: `launcher/modules/codebase_memory_mcp/module.py`
- Test: `launcher/tests/test_cbm_module.py`

- [ ] **Step 1: Create module directory**

```bash
mkdir -p launcher/modules/codebase_memory_mcp/prompts launcher/modules/codebase_memory_mcp/references
touch launcher/modules/codebase_memory_mcp/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for codebase-memory-mcp module."""

import pytest
from unittest.mock import patch
from launcher.modules.codebase_memory_mcp import module


def test_check_dependencies_binary_found():
    with patch("shutil.which", return_value="/usr/local/bin/codebase-memory-mcp"):
        result = module.check_dependencies({})
    
    assert result["available"] is True
    assert result["name"] == "Codebase-Memory MCP"
    assert result["reason"] is None


def test_check_dependencies_binary_not_found():
    with patch("shutil.which", return_value=None):
        result = module.check_dependencies({})
    
    assert result["available"] is False
    assert result["name"] == "Codebase-Memory MCP"
    assert "not found on PATH" in result["reason"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest launcher/tests/test_cbm_module.py::test_check_dependencies_binary_found -v`
Expected: FAIL with "No module named 'launcher.modules.codebase_memory_mcp'"

- [ ] **Step 4: Write minimal implementation**

Create `launcher/modules/codebase_memory_mcp/module.py`:

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
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest launcher/tests/test_cbm_module.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add launcher/modules/codebase_memory_mcp/ launcher/tests/test_cbm_module.py
git commit -m "$(cat <<'EOF'
feat(launcher): add CBM module skeleton with check_dependencies

Creates codebase_memory_mcp module directory structure and implements
dependency check for the binary.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Add build_tui_section to CBM module

**Files:**
- Modify: `launcher/modules/codebase_memory_mcp/module.py`
- Test: `launcher/tests/test_cbm_module.py`

- [ ] **Step 1: Write the failing test**

Add to `launcher/tests/test_cbm_module.py`:

```python
def test_build_tui_section_returns_toggle():
    result = module.build_tui_section({}, {})
    
    assert len(result) == 1
    assert result[0]["type"] == "toggle"
    assert result[0]["label"] == "Codebase-Memory MCP"
    assert result[0]["key"] == "enabled"
    assert result[0]["group"] == "master"


def test_build_tui_section_respects_saved_state():
    result = module.build_tui_section({}, {"enabled": False})
    
    assert result[0]["default"] is False


def test_build_tui_section_defaults_to_enabled():
    result = module.build_tui_section({}, {})
    
    assert result[0]["default"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest launcher/tests/test_cbm_module.py::test_build_tui_section_returns_toggle -v`
Expected: FAIL with "has no attribute 'build_tui_section'"

- [ ] **Step 3: Write minimal implementation**

Add to `launcher/modules/codebase_memory_mcp/module.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest launcher/tests/test_cbm_module.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add launcher/modules/codebase_memory_mcp/module.py launcher/tests/test_cbm_module.py
git commit -m "$(cat <<'EOF'
feat(launcher): add build_tui_section to CBM module

Single toggle for enabling/disabling CBM integration per session.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Add build_prompt to CBM module

**Files:**
- Modify: `launcher/modules/codebase_memory_mcp/module.py`
- Create: `launcher/modules/codebase_memory_mcp/prompts/code-discovery.md`
- Test: `launcher/tests/test_cbm_module.py`

- [ ] **Step 1: Create the prompt file**

Create `launcher/modules/codebase_memory_mcp/prompts/code-discovery.md`:

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

- [ ] **Step 2: Write the failing test**

Add to `launcher/tests/test_cbm_module.py`:

```python
def test_build_prompt_returns_content_with_references_path():
    result = module.build_prompt({}, {"enabled": True})
    
    assert "Code Discovery Protocol" in result
    assert "Quick Decision Matrix" in result
    assert "{{REFERENCES_PATH}}" not in result  # Should be replaced
    assert "references" in result  # Should have real path


def test_build_prompt_returns_empty_when_no_prompt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "PROMPTS_DIR", tmp_path)
    result = module.build_prompt({}, {"enabled": True})
    
    assert result == ""
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest launcher/tests/test_cbm_module.py::test_build_prompt_returns_content_with_references_path -v`
Expected: FAIL with "has no attribute 'build_prompt'"

- [ ] **Step 4: Write minimal implementation**

Add to `launcher/modules/codebase_memory_mcp/module.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest launcher/tests/test_cbm_module.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add launcher/modules/codebase_memory_mcp/ launcher/tests/test_cbm_module.py
git commit -m "$(cat <<'EOF'
feat(launcher): add build_prompt to CBM module

Injects code discovery protocol prompt with reference path for
detailed workflows and Cypher examples.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Add build_mcp_entries to CBM module

**Files:**
- Modify: `launcher/modules/codebase_memory_mcp/module.py`
- Test: `launcher/tests/test_cbm_module.py`

- [ ] **Step 1: Write the failing test**

Add to `launcher/tests/test_cbm_module.py`:

```python
def test_build_mcp_entries_returns_server_config():
    with patch("shutil.which", return_value="/usr/local/bin/codebase-memory-mcp"):
        result = module.build_mcp_entries({}, {"enabled": True})
    
    assert len(result) == 1
    assert result[0]["name"] == "codebase-memory-mcp"
    assert result[0]["type"] == "stdio"
    assert result[0]["command"] == "/usr/local/bin/codebase-memory-mcp"
    assert result[0]["args"] == []
    assert result[0]["env"] == {}


def test_build_mcp_entries_returns_empty_when_binary_missing():
    with patch("shutil.which", return_value=None):
        result = module.build_mcp_entries({}, {"enabled": True})
    
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest launcher/tests/test_cbm_module.py::test_build_mcp_entries_returns_server_config -v`
Expected: FAIL with "has no attribute 'build_mcp_entries'"

- [ ] **Step 3: Write minimal implementation**

Add to `launcher/modules/codebase_memory_mcp/module.py`:

```python
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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest launcher/tests/test_cbm_module.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add launcher/modules/codebase_memory_mcp/module.py launcher/tests/test_cbm_module.py
git commit -m "$(cat <<'EOF'
feat(launcher): add build_mcp_entries to CBM module

Returns MCP server configuration for dynamic loading via --mcp-config.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Create reference files

**Files:**
- Create: `launcher/modules/codebase_memory_mcp/references/workflows.md`
- Create: `launcher/modules/codebase_memory_mcp/references/cypher-examples.md`
- Create: `launcher/modules/codebase_memory_mcp/references/tool-reference.md`

- [ ] **Step 1: Create workflows.md**

Create `launcher/modules/codebase_memory_mcp/references/workflows.md`:

```markdown
# CBM Workflows

## Exploration Workflow
1. `list_projects` — check if project is indexed
2. `get_graph_schema` — understand node/edge types
3. `search_graph(label="Function", name_pattern=".*Pattern.*")` — find code
4. `get_code_snippet(qualified_name="project.path.FuncName")` — read source

## Tracing Workflow
1. `search_graph(name_pattern=".*FuncName.*")` — discover exact name
2. `trace_path(function_name="FuncName", direction="both", depth=3)` — trace
3. `detect_changes()` — map git diff to affected symbols

## Quality Analysis
- Dead code: `search_graph(max_degree=0, exclude_entry_points=true)`
- High fan-out: `search_graph(min_degree=10, relationship="CALLS", direction="outbound")`
- High fan-in: `search_graph(min_degree=10, relationship="CALLS", direction="inbound")`
```

- [ ] **Step 2: Create cypher-examples.md**

Create `launcher/modules/codebase_memory_mcp/references/cypher-examples.md`:

```markdown
# Cypher Examples (for query_graph)

```cypher
# Find HTTP call edges
MATCH (a)-[r:HTTP_CALLS]->(b) 
RETURN a.name, b.name, r.url_path, r.confidence 
LIMIT 20

# Find functions matching pattern
MATCH (f:Function) WHERE f.name =~ '.*Handler.*' 
RETURN f.name, f.file_path

# Find what main calls
MATCH (a)-[r:CALLS]->(b) WHERE a.name = 'main' 
RETURN b.name

# Find cross-service dependencies
MATCH (a)-[r:HTTP_CALLS|ASYNC_CALLS]->(b) 
WHERE a.project <> b.project 
RETURN a.name, type(r), b.name

# Find functions with high complexity
MATCH (f:Function) 
WHERE f.cyclomatic_complexity > 10 
RETURN f.name, f.file_path, f.cyclomatic_complexity 
ORDER BY f.cyclomatic_complexity DESC
```
```

- [ ] **Step 3: Create tool-reference.md**

Create `launcher/modules/codebase_memory_mcp/references/tool-reference.md`:

```markdown
# CBM Tool Reference

## 14 MCP Tools
`index_repository`, `index_status`, `list_projects`, `delete_project`,
`search_graph`, `search_code`, `trace_path`, `detect_changes`,
`query_graph`, `get_graph_schema`, `get_code_snippet`, `get_architecture`,
`manage_adr`, `ingest_traces`

## Edge Types
CALLS, HTTP_CALLS, ASYNC_CALLS, IMPORTS, DEFINES, DEFINES_METHOD,
HANDLES, IMPLEMENTS, OVERRIDE, USAGE, FILE_CHANGES_WITH,
CONTAINS_FILE, CONTAINS_FOLDER, CONTAINS_PACKAGE

## Gotchas
1. `search_graph(relationship="HTTP_CALLS")` filters nodes by degree — use `query_graph` with Cypher to see actual edges.
2. `query_graph` has a 200-row cap — use `search_graph` with degree filters for counting.
3. `trace_path` needs exact names — use `search_graph(name_pattern=...)` first.
4. `direction="outbound"` misses cross-service callers — use `direction="both"`.
5. Results default to 10 per page — check `has_more` and use `offset`.
```

- [ ] **Step 4: Verify files exist**

Run: `ls -la launcher/modules/codebase_memory_mcp/references/`
Expected: Three .md files listed

- [ ] **Step 5: Commit**

```bash
git add launcher/modules/codebase_memory_mcp/references/
git commit -m "$(cat <<'EOF'
docs(launcher): add CBM reference files

Workflows, Cypher examples, and tool reference for detailed
code discovery guidance.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Integration test

**Files:**
- Test: Manual verification

- [ ] **Step 1: Verify module discovery**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -c "from launcher.launcher import discover_modules; from launcher.config import parse_env; env = parse_env('.env'); mods = discover_modules(env); print([m['name'] for m in mods])"`
Expected: List includes "Codebase-Memory MCP" (if binary is on PATH)

- [ ] **Step 2: Verify MCP collection**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -c "
from launcher.launcher import discover_modules, collect_mcp_entries
from launcher.config import parse_env
env = parse_env('.env')
mods = discover_modules(env)
states = {'codebase-memory_mcp': {'enabled': True}, 'memory_system': {'enabled': True}}
entries = collect_mcp_entries(mods, states, env)
print('MCP entries:', list(entries.keys()))
"`
Expected: `MCP entries: ['codebase-memory-mcp']` (if binary on PATH)

- [ ] **Step 3: Run full launcher (dry-run inspection)**

Run launcher, toggle CBM on, let it launch claude, then immediately `/quit`.
Verify:
- TUI shows "Codebase-Memory MCP" toggle
- Launch message shows MCP server count
- CBM tools appear in `/mcp` listing

- [ ] **Step 4: Run all tests**

Run: `python -m pytest launcher/tests/ -v`
Expected: All tests pass

- [ ] **Step 5: Commit any test fixes**

If any tests needed adjustment:

```bash
git add launcher/tests/
git commit -m "$(cat <<'EOF'
test(launcher): fix integration test issues

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Post-implementation cleanup

**Files:**
- Modify: `~/.claude.json` (user's global config)

- [ ] **Step 1: Remove CBM from global MCP config**

The launcher now controls CBM loading dynamically. Remove the static entry:

```bash
# Edit ~/.claude.json and remove codebase-memory-mcp from mcpServers
# Before: "mcpServers": {"codebase-memory-mcp": {"command": "..."}, ...}
# After:  "mcpServers": {...} (without codebase-memory-mcp)
```

- [ ] **Step 2: Verify launcher-controlled loading works**

Run launcher with CBM enabled, verify `/mcp` shows codebase-memory-mcp.
Run launcher with CBM disabled, verify `/mcp` does NOT show codebase-memory-mcp.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(launcher): complete CBM module integration

Codebase-Memory MCP is now dynamically loaded via launcher toggle.
Removed static MCP entry from global config.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
