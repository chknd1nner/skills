# Launcher CBM Session-Ephemeral Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire session-ephemeral CBM gate hooks into the launcher via a tempfile settings.json passed to `claude --settings`, so the code-discovery nudge activates only when CBM is enabled in the TUI — without touching the user's permanent `~/.claude/settings.json`.

**Architecture:** Add a third output channel alongside `--append-system-prompt-file` and `--mcp-config`. Modules implement an optional `build_hooks(env, selections) -> dict` returning a settings.json fragment. The launcher collects fragments from enabled modules, deep-merges them (lists concatenated, dicts recursed), writes to a tempfile, and passes `--settings <path>` to `claude`. The CBM module contributes a single `PreToolUse` entry pointing at a bundled gate script.

**Tech Stack:** Python 3.11+, bash, pytest, existing launcher module protocol.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `launcher/prompt_builder.py` | Modify | Add `write_settings_config()` and `merge_settings()` |
| `launcher/launcher.py` | Modify | Add `collect_hooks()`, wire `--settings` in `main()` |
| `launcher/modules/codebase_memory_mcp/module.py` | Modify | Add `build_hooks()` |
| `launcher/modules/codebase_memory_mcp/hooks/gate.sh` | Create | Gate script (bundled, absolute path referenced at runtime) |
| `launcher/tests/test_prompt_builder.py` | Modify | Tests for new `merge_settings` + `write_settings_config` |
| `launcher/tests/test_launcher.py` | Modify | Tests for `collect_hooks` |
| `launcher/tests/test_cbm_module.py` | Modify | Tests for `build_hooks` |

---

## Task 1: `write_settings_config` and `merge_settings` in `prompt_builder.py`

**Files:**
- Modify: `launcher/prompt_builder.py`
- Modify: `launcher/tests/test_prompt_builder.py`

- [ ] **Step 1: Write the failing tests**

Append to `launcher/tests/test_prompt_builder.py`:

```python
import json
import os
from launcher.prompt_builder import write_settings_config, merge_settings


def test_write_settings_config_creates_json_file():
    config = {"hooks": {"PreToolUse": [{"matcher": "Grep", "hooks": []}]}}
    path = write_settings_config(config)

    assert path.endswith(".json")
    assert "claude-settings" in path
    assert os.path.exists(path)

    with open(path) as f:
        written = json.load(f)

    assert written == config
    os.unlink(path)


def test_merge_settings_combines_dicts():
    a = {"hooks": {"PreToolUse": [{"matcher": "Grep"}]}}
    b = {"hooks": {"SessionStart": [{"matcher": "startup"}]}}
    result = merge_settings([a, b])

    assert "PreToolUse" in result["hooks"]
    assert "SessionStart" in result["hooks"]


def test_merge_settings_concatenates_lists():
    a = {"hooks": {"PreToolUse": [{"matcher": "Grep"}]}}
    b = {"hooks": {"PreToolUse": [{"matcher": "Glob"}]}}
    result = merge_settings([a, b])

    assert len(result["hooks"]["PreToolUse"]) == 2


def test_merge_settings_empty_list():
    assert merge_settings([]) == {}


def test_merge_settings_single_item():
    config = {"hooks": {"PreToolUse": [{"matcher": "Read"}]}}
    result = merge_settings([config])
    assert result == config
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python -m pytest launcher/tests/test_prompt_builder.py -v 2>&1 | tail -20
```

Expected: `ImportError` — `write_settings_config` and `merge_settings` not defined.

- [ ] **Step 3: Implement the two functions**

Append to `launcher/prompt_builder.py` (after the existing `write_mcp_config` function):

```python
def write_settings_config(config: dict) -> str:
    """Write settings fragment to temp file, return path.

    Args:
        config: settings.json-shaped dict (e.g. with 'hooks' key)

    Returns:
        Path to temp JSON file
    """
    fd, path = tempfile.mkstemp(suffix=".json", prefix="claude-settings-")
    with os.fdopen(fd, "w") as f:
        json.dump(config, f, indent=2)

    return path


def merge_settings(settings_list: list[dict]) -> dict:
    """Deep merge a list of settings dicts.

    Dicts are recursively merged. Lists are concatenated.
    Scalar conflicts: later value wins.

    Args:
        settings_list: list of settings fragments from modules

    Returns:
        Single merged settings dict
    """
    merged: dict = {}
    for settings in settings_list:
        _deep_merge(merged, settings)
    return merged


def _deep_merge(base: dict, overlay: dict) -> None:
    """Mutate base by merging overlay into it."""
    for key, value in overlay.items():
        if key in base:
            if isinstance(base[key], dict) and isinstance(value, dict):
                _deep_merge(base[key], value)
            elif isinstance(base[key], list) and isinstance(value, list):
                base[key].extend(value)
            else:
                base[key] = value
        else:
            base[key] = value
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python -m pytest launcher/tests/test_prompt_builder.py -v 2>&1 | tail -20
```

Expected: all prompt builder tests pass.

- [ ] **Step 5: Commit**

```bash
git add launcher/prompt_builder.py launcher/tests/test_prompt_builder.py
git commit -m "feat(launcher): add write_settings_config and merge_settings to prompt_builder"
```

---

## Task 2: `collect_hooks` in `launcher.py`

**Files:**
- Modify: `launcher/launcher.py`
- Modify: `launcher/tests/test_launcher.py`

- [ ] **Step 1: Write the failing tests**

Append to `launcher/tests/test_launcher.py`:

```python
from launcher.launcher import collect_hooks


class MockModuleWithHooks:
    @staticmethod
    def build_hooks(env, selections):
        return {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Grep|Glob|Read|Search",
                        "hooks": [{"type": "command", "command": "/path/gate.sh"}],
                    }
                ]
            }
        }


class MockModuleWithEmptyHooks:
    @staticmethod
    def build_hooks(env, selections):
        return {}


def test_collect_hooks_from_enabled_module():
    modules = [{"name": "Test Module", "module": MockModuleWithHooks}]
    module_states = {"test_module": {"enabled": True}}

    result = collect_hooks(modules, module_states, {})

    assert len(result) == 1
    assert "hooks" in result[0]
    assert "PreToolUse" in result[0]["hooks"]


def test_collect_hooks_skips_disabled_module():
    modules = [{"name": "Test Module", "module": MockModuleWithHooks}]
    module_states = {"test_module": {"enabled": False}}

    result = collect_hooks(modules, module_states, {})

    assert result == []


def test_collect_hooks_skips_module_without_build_hooks():
    modules = [{"name": "Legacy Module", "module": MockModuleWithoutMCP}]
    module_states = {"legacy_module": {"enabled": True}}

    result = collect_hooks(modules, module_states, {})

    assert result == []


def test_collect_hooks_skips_empty_fragment():
    modules = [{"name": "Empty Module", "module": MockModuleWithEmptyHooks}]
    module_states = {"empty_module": {"enabled": True}}

    result = collect_hooks(modules, module_states, {})

    assert result == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python -m pytest launcher/tests/test_launcher.py -v 2>&1 | tail -20
```

Expected: `ImportError` — `collect_hooks` not defined.

- [ ] **Step 3: Implement `collect_hooks`**

In `launcher/launcher.py`, add after the `collect_mcp_entries` function (around line 240):

```python
def collect_hooks(modules: list, module_states: dict, env: dict) -> list[dict]:
    """Collect settings fragments from all enabled modules.

    Returns list of settings dicts (one per module), skipping empty ones.
    """
    fragments = []
    for mod_info in modules:
        mod = mod_info["module"]
        mod_key = mod_info["name"].lower().replace(" ", "_")
        mod_state = module_states.get(mod_key, {})

        if not mod_state.get("enabled", False):
            continue

        if hasattr(mod, "build_hooks"):
            try:
                fragment = mod.build_hooks(env, mod_state)
                if fragment:
                    fragments.append(fragment)
            except Exception as e:
                print(f"Warning: {mod_info['name']} failed to build hooks: {e}")

    return fragments
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python -m pytest launcher/tests/test_launcher.py -v 2>&1 | tail -20
```

Expected: all launcher tests pass.

- [ ] **Step 5: Commit**

```bash
git add launcher/launcher.py launcher/tests/test_launcher.py
git commit -m "feat(launcher): add collect_hooks for settings fragment collection"
```

---

## Task 3: Gate script and `build_hooks` in CBM module

**Files:**
- Create: `launcher/modules/codebase_memory_mcp/hooks/gate.sh`
- Modify: `launcher/modules/codebase_memory_mcp/module.py`
- Modify: `launcher/tests/test_cbm_module.py`

- [ ] **Step 1: Write the failing tests**

Append to `launcher/tests/test_cbm_module.py`:

```python
import os


def test_build_hooks_returns_pretooluse_entry():
    result = module.build_hooks({}, {"enabled": True})

    assert "hooks" in result
    assert "PreToolUse" in result["hooks"]
    entries = result["hooks"]["PreToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "Grep|Glob|Read|Search"
    inner = entries[0]["hooks"]
    assert len(inner) == 1
    assert inner[0]["type"] == "command"
    assert os.path.isabs(inner[0]["command"])


def test_build_hooks_gate_script_is_executable():
    result = module.build_hooks({}, {"enabled": True})
    gate_path = result["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert os.access(gate_path, os.X_OK), f"Gate script not executable: {gate_path}"


def test_build_hooks_returns_empty_when_disabled():
    result = module.build_hooks({}, {"enabled": False})
    assert result == {}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python -m pytest launcher/tests/test_cbm_module.py -v 2>&1 | tail -20
```

Expected: `AttributeError` — `build_hooks` not defined.

- [ ] **Step 3: Create the gate script**

Create `launcher/modules/codebase_memory_mcp/hooks/gate.sh`:

```bash
#!/bin/bash
# CBM code-discovery gate — bundled with skills launcher.
# Nudges Claude toward codebase-memory-mcp for code discovery.
# First Grep/Glob/Read per session -> block with nudge, marker created.
# Subsequent calls in the same session -> allow through.
GATE=/tmp/cbm-code-discovery-gate-$PPID
find /tmp -name 'cbm-code-discovery-gate-*' -mtime +1 -delete 2>/dev/null
if [ -f "$GATE" ]; then
    exit 0
fi
touch "$GATE"
echo 'BLOCKED: For code discovery, use codebase-memory-mcp tools first: search_graph(name_pattern) to find functions/classes, trace_path() for call chains, get_code_snippet(qualified_name) to read source. If not indexed, call index_repository first. Fall back to Grep/Glob/Read/Search for text/config content only. To proceed with Grep/Search, retry.' >&2
exit 2
```

Make it executable:

```bash
chmod +x launcher/modules/codebase_memory_mcp/hooks/gate.sh
```

- [ ] **Step 4: Add `build_hooks` to the CBM module**

In `launcher/modules/codebase_memory_mcp/module.py`, add after the imports block (add `import os` to imports, add `HOOKS_DIR` constant, add the function):

```python
import os
import shutil
from pathlib import Path

MODULE_DIR = Path(__file__).parent
PROMPTS_DIR = MODULE_DIR / "prompts"
REFERENCES_DIR = MODULE_DIR / "references"
HOOKS_DIR = MODULE_DIR / "hooks"
```

Then add `build_hooks` after `build_mcp_entries`:

```python
def build_hooks(env: dict, selections: dict) -> dict:
    """Return settings fragment with PreToolUse gate hook."""
    if not selections.get("enabled", True):
        return {}

    gate_script = HOOKS_DIR / "gate.sh"
    if not gate_script.exists():
        return {}

    # Ensure executable bit is set (git may not preserve it)
    os.chmod(gate_script, 0o755)

    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Grep|Glob|Read|Search",
                    "hooks": [
                        {"type": "command", "command": str(gate_script.resolve())}
                    ],
                }
            ]
        }
    }
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python -m pytest launcher/tests/test_cbm_module.py -v 2>&1 | tail -20
```

Expected: all CBM module tests pass.

- [ ] **Step 6: Commit**

```bash
git add launcher/modules/codebase_memory_mcp/hooks/gate.sh \
        launcher/modules/codebase_memory_mcp/module.py \
        launcher/tests/test_cbm_module.py
git commit -m "feat(cbm): add gate.sh hook script and build_hooks to CBM module"
```

---

## Task 4: Wire `--settings` into `main()`

**Files:**
- Modify: `launcher/launcher.py`

This task has no new tests — the behaviour is an integration of three already-tested pieces. Manual verification (dry-run inspection) is the validation.

- [ ] **Step 1: Update imports in `launcher.py`**

In `launcher/launcher.py`, change the import line:

```python
# Before:
from launcher.prompt_builder import assemble_prompt, write_mcp_config

# After:
from launcher.prompt_builder import assemble_prompt, write_mcp_config, write_settings_config, merge_settings
```

- [ ] **Step 2: Wire the new step into `main()`**

In `launcher/launcher.py`, in the `main()` function, insert a new step between Step 6 and Step 7 and update Step 9/10. The full modified section of `main()` (from Step 6 onward):

```python
    # Step 6: Collect MCP entries from enabled modules
    mcp_servers = collect_mcp_entries(modules, module_states, env)

    # Step 6b: Collect hooks fragments from enabled modules
    hooks_fragments = collect_hooks(modules, module_states, env)

    # Step 7: Parse user flags
    args = parse_args(sys.argv[1:])

    # Step 8: Assemble system prompt
    prompt_path = assemble_prompt(fragments, args["user_appends"])

    # Step 9: Write MCP config if any modules contributed servers
    mcp_path = None
    if mcp_servers:
        mcp_path = write_mcp_config({"mcpServers": mcp_servers})

    # Step 9b: Write settings config if any modules contributed hooks
    settings_path = None
    if hooks_fragments:
        settings_config = merge_settings(hooks_fragments)
        settings_path = write_settings_config(settings_config)

    # Step 10: Launch claude
    claude_args = ["claude"]
    if prompt_path:
        claude_args.extend(["--append-system-prompt-file", prompt_path])
    if mcp_path:
        claude_args.extend(["--mcp-config", mcp_path])
    if settings_path:
        claude_args.extend(["--settings", settings_path])
    claude_args.extend(args["passthrough"])

    mcp_count = len(mcp_servers)
    hook_count = len(hooks_fragments)
    if mcp_count or hook_count:
        print(
            f"Launching claude with {len(fragments)} module(s), "
            f"{mcp_count} MCP server(s), {hook_count} hook fragment(s)..."
        )
    else:
        print(f"Launching claude with {len(fragments)} module(s)...")
    os.execvp("claude", claude_args)
```

- [ ] **Step 3: Run the full test suite to confirm nothing is broken**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python -m pytest launcher/tests/ -v 2>&1 | tail -30
```

Expected: all tests pass, no failures.

- [ ] **Step 4: Smoke-test the launcher (CBM enabled)**

```bash
cd /Users/martinkuek/Documents/Projects/skills
# Dry run — inspect the printed args without launching claude
python -c "
import sys, os
sys.argv = ['launcher']

# Patch execvp to print instead of launch
import os as _os
_os.execvp = lambda cmd, args: print('Would launch:', args)

from launcher.launcher import main
" 2>&1
```

With CBM enabled in TUI, expected output should include `--settings /tmp/claude-settings-XXXXX.json` in the printed args.

- [ ] **Step 5: Commit**

```bash
git add launcher/launcher.py
git commit -m "feat(launcher): wire --settings channel for session-ephemeral hooks"
```

---

## Self-Review

**Spec coverage check:**
- ✅ `--settings` tempfile channel added
- ✅ Module protocol: `build_hooks(env, selections)` → dict
- ✅ CBM module implements `build_hooks` with gate script
- ✅ Gate script bundled in module directory, absolute path injected at runtime
- ✅ Session-ephemeral: tempfile, no mutation of `~/.claude/settings.json`
- ✅ Enabled/disabled: `build_hooks` returns `{}` when not enabled, skipped by `collect_hooks`
- ✅ Multi-module merge: `merge_settings` handles list concatenation for multiple modules contributing `PreToolUse` entries
- ✅ Executable bit: `build_hooks` calls `os.chmod` to guarantee gate is runnable
- ✅ Gate matcher: `Grep|Glob|Read|Search` — `Search` is a real Claude Code tool (file glob + content search), confirmed via screenshot

**Placeholder scan:** No TBDs, all code blocks complete.

**Type consistency:**
- `collect_hooks` returns `list[dict]`
- `merge_settings` accepts `list[dict]`, returns `dict`
- `write_settings_config` accepts `dict`, returns `str` (path)
- `build_hooks` returns `dict` — consistent across all tasks ✅
