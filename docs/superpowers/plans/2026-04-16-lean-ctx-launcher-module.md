# lean-ctx Launcher Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a launcher module that registers `lean-ctx` as an MCP server with selectable CRP mode, wires its Bash-rewrite PreToolUse hook, injects a strong-language tool-preference system prompt, and sandboxes the lean-ctx subprocess `HOME` to prevent its `inject_all_rules` side effect from modifying the user's real `~/.claude/CLAUDE.md`. Also extend the launcher framework with a reusable `radio` TUI item type.

**Architecture:** Standalone Python module at `launcher/modules/lean_ctx_mcp/` implementing the existing 5-function module interface (`check_dependencies`, `build_tui_section`, `build_prompt`, `build_mcp_entries`, `build_hooks`). Launcher framework extended with a two-phase TUI: existing checkbox stage for toggles + separators, new conditional `inquirer.select` stage for radio items.

**Tech Stack:** Python 3, `shutil.which`, `pathlib`, `InquirerPy` (existing dep), `pytest` (existing dep).

**Spec:** `docs/superpowers/specs/2026-04-16-lean-ctx-launcher-module-design.md`

**Precondition (user-performed, outside this plan):** `brew install lean-ctx` so the binary exists on PATH for the smoke test in Task 9. The implementation tests don't require the binary (they mock `shutil.which`).

---

## File Structure

**Create:**
- `launcher/modules/lean_ctx_mcp/__init__.py` (empty package marker)
- `launcher/modules/lean_ctx_mcp/module.py` (5-function module + sandbox helper)
- `launcher/modules/lean_ctx_mcp/prompts/tool-preference.md` (system prompt fragment)
- `launcher/tests/test_lean_ctx_module.py` (module unit tests)

**Modify:**
- `launcher/launcher.py` — split `run_tui` into checkbox + radio phases; add `_run_checkbox_stage`, `_run_radio_stage`
- `launcher/tests/test_launcher.py` — append tests for radio handling in `run_tui`

---

## Task 1: Radio TUI widget in launcher framework

**Files:**
- Modify: `launcher/launcher.py:138-176` (split `run_tui`, add helpers)
- Modify: `launcher/tests/test_launcher.py` (append radio tests at end)

The current `run_tui` returns `{key: bool}` from a single `inquirer.checkbox`. We need to support a new `radio` item type that runs as a second-stage `inquirer.select` after the checkbox, with a `requires_enabled` gate that skips the prompt when a sibling toggle is unchecked.

- [ ] **Step 1: Write failing tests for radio handling**

Append to `launcher/tests/test_launcher.py`:

```python
from unittest.mock import patch, MagicMock
from launcher.launcher import run_tui


def _toggle_item(key, default=True, label=None):
    return {
        "type": "toggle",
        "key": key,
        "label": label or key,
        "default": default,
        "module_name": "Test",
        "group": "master",
    }


def _radio_item(key, options, default, requires_enabled=None, label="Mode"):
    item = {
        "type": "radio",
        "key": key,
        "label": label,
        "options": options,
        "default": default,
        "group": "settings",
        "module_name": "Test",
    }
    if requires_enabled is not None:
        item["requires_enabled"] = requires_enabled
    return item


@patch("launcher.launcher._run_radio_stage")
@patch("launcher.launcher._run_checkbox_stage")
def test_run_tui_runs_radio_when_gate_true(mock_checkbox, mock_radio):
    mock_checkbox.return_value = {"test:enabled": True}
    mock_radio.return_value = "compact"
    items = [
        _toggle_item("test:enabled"),
        _radio_item(
            "test:mode",
            options=[{"value": "off", "label": "Off"}, {"value": "compact", "label": "Compact"}],
            default="off",
            requires_enabled="test:enabled",
        ),
    ]

    result = run_tui(items)

    assert result["test:enabled"] is True
    assert result["test:mode"] == "compact"
    mock_radio.assert_called_once()


@patch("launcher.launcher._run_radio_stage")
@patch("launcher.launcher._run_checkbox_stage")
def test_run_tui_skips_radio_when_gate_false(mock_checkbox, mock_radio):
    mock_checkbox.return_value = {"test:enabled": False}
    items = [
        _toggle_item("test:enabled", default=False),
        _radio_item(
            "test:mode",
            options=[{"value": "off", "label": "Off"}, {"value": "tdd", "label": "TDD"}],
            default="tdd",
            requires_enabled="test:enabled",
        ),
    ]

    result = run_tui(items)

    assert result["test:enabled"] is False
    assert result["test:mode"] == "tdd"  # falls back to default, not prompted
    mock_radio.assert_not_called()


@patch("launcher.launcher._run_radio_stage")
@patch("launcher.launcher._run_checkbox_stage")
def test_run_tui_runs_radio_when_no_gate(mock_checkbox, mock_radio):
    mock_checkbox.return_value = {}
    mock_radio.return_value = "selected"
    items = [
        _radio_item(
            "test:mode",
            options=[{"value": "selected", "label": "Selected"}],
            default="selected",
        ),
    ]

    result = run_tui(items)

    assert result["test:mode"] == "selected"
    mock_radio.assert_called_once()


@patch("launcher.launcher._run_radio_stage")
@patch("launcher.launcher._run_checkbox_stage")
def test_run_tui_passes_only_non_radio_to_checkbox_stage(mock_checkbox, mock_radio):
    mock_checkbox.return_value = {"a:enabled": True}
    mock_radio.return_value = "x"
    items = [
        _toggle_item("a:enabled"),
        _radio_item(
            "a:mode",
            options=[{"value": "x", "label": "X"}],
            default="x",
            requires_enabled="a:enabled",
        ),
    ]

    run_tui(items)

    forwarded = mock_checkbox.call_args[0][0]
    assert all(i.get("type") != "radio" for i in forwarded)
    assert any(i["key"] == "a:enabled" for i in forwarded)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_launcher.py -k "run_tui" -v`

Expected: 4 failures with `ImportError`/`AttributeError` for `_run_checkbox_stage` or `_run_radio_stage` (they don't exist yet).

- [ ] **Step 3: Implement the refactor in `launcher.py`**

Replace lines 138–176 of `launcher/launcher.py` with:

```python
def _run_checkbox_stage(items: list) -> dict:
    """Run the checkbox prompt for toggle + separator items only.

    Returns: {key: bool} for every non-separator item in `items`.
    """
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator

    choices = []
    for item in items:
        if item.get("type") == "separator":
            choices.append(Separator(f"── {item['label']} ──"))
        else:
            choices.append(
                Choice(
                    value=item["key"],
                    name=item["label"],
                    enabled=item.get("default", True),
                )
            )

    if not choices:
        return {}

    selected = inquirer.checkbox(
        message="Configure launch options (↑↓ navigate, ␣ toggle, ⏎ launch):",
        choices=choices,
        instruction="",
    ).execute()

    all_keys = [item["key"] for item in items if item.get("type") != "separator"]
    return {key: (key in selected) for key in all_keys}


def _run_radio_stage(radio: dict) -> str:
    """Prompt the user to pick one of the radio's options.

    Returns the selected option's `value` (string).
    """
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice

    choices = [
        Choice(value=opt["value"], name=opt["label"])
        for opt in radio["options"]
    ]
    return inquirer.select(
        message=f"{radio['label']}:",
        choices=choices,
        default=radio["default"],
    ).execute()


def run_tui(all_items: list) -> dict:
    """Present the TUI in two phases and return user selections.

    Phase 1: checkbox prompt for toggle + separator items.
    Phase 2: one inquirer.select per radio item whose `requires_enabled`
             gate (if present) resolves True in the phase-1 selections.
             Skipped radios fall back to their `default`.

    Args:
        all_items: list of menu item dicts from build_tui_choices()

    Returns:
        dict mapping every non-separator item key to its value.
        Toggle keys map to bool; radio keys map to str.
    """
    togglable = [i for i in all_items if i.get("type") != "radio"]
    radios = [i for i in all_items if i.get("type") == "radio"]

    selections = _run_checkbox_stage(togglable)

    for radio in radios:
        gate_key = radio.get("requires_enabled")
        if gate_key and not selections.get(gate_key, False):
            selections[radio["key"]] = radio["default"]
            continue
        selections[radio["key"]] = _run_radio_stage(radio)

    return selections
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_launcher.py -v`

Expected: All tests pass (existing tests + 4 new radio tests). No regressions.

- [ ] **Step 5: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add launcher/launcher.py launcher/tests/test_launcher.py
git commit -m "$(cat <<'EOF'
feat(launcher): add radio TUI item type with requires_enabled gate

Splits run_tui into _run_checkbox_stage (existing behavior) and
_run_radio_stage (new inquirer.select). Radio items run as a
second-phase prompt only when their requires_enabled key resolves
True in the checkbox selections; skipped radios fall back to default.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Module skeleton + check_dependencies

**Files:**
- Create: `launcher/modules/lean_ctx_mcp/__init__.py` (empty)
- Create: `launcher/modules/lean_ctx_mcp/module.py` (initial scaffold)
- Create: `launcher/tests/test_lean_ctx_module.py` (initial tests)

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p /Users/martinkuek/Documents/Projects/skills/launcher/modules/lean_ctx_mcp/prompts
touch /Users/martinkuek/Documents/Projects/skills/launcher/modules/lean_ctx_mcp/__init__.py
```

- [ ] **Step 2: Write failing tests for `check_dependencies`**

Create `launcher/tests/test_lean_ctx_module.py`:

```python
"""Tests for lean-ctx MCP launcher module."""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

from launcher.modules.lean_ctx_mcp import module


def test_check_dependencies_binary_found():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.check_dependencies({})

    assert result["available"] is True
    assert result["name"] == "lean-ctx MCP"
    assert result["reason"] is None


def test_check_dependencies_binary_not_found():
    with patch("shutil.which", return_value=None):
        result = module.check_dependencies({})

    assert result["available"] is False
    assert result["name"] == "lean-ctx MCP"
    assert "not found on PATH" in result["reason"]
    assert "brew install lean-ctx" in result["reason"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -v`

Expected: `ModuleNotFoundError: No module named 'launcher.modules.lean_ctx_mcp.module'`.

- [ ] **Step 4: Create the module scaffold**

Create `launcher/modules/lean_ctx_mcp/module.py`:

```python
"""lean-ctx MCP module for the Claude Code launcher."""

import shutil
from pathlib import Path

MODULE_DIR = Path(__file__).parent
PROMPTS_DIR = MODULE_DIR / "prompts"

VALID_CRP_MODES = ("off", "compact", "tdd")
DEFAULT_CRP_MODE = "tdd"

# Sandbox HOME for the MCP subprocess. Prevents lean-ctx's inject_all_rules
# from writing to the real ~/.claude/CLAUDE.md. The .lean-ctx symlink preserves
# lean-ctx's own state (cache, config, knowledge) across sessions.
SANDBOX_HOME = Path.home() / ".cache" / "claude-launcher" / "lean-ctx-home"


def check_dependencies(env: dict) -> dict:
    """Check if lean-ctx binary is available."""
    binary_path = shutil.which("lean-ctx")

    if not binary_path:
        return {
            "available": False,
            "name": "lean-ctx MCP",
            "reason": "lean-ctx not found on PATH (install: brew install lean-ctx)",
        }

    return {
        "available": True,
        "name": "lean-ctx MCP",
        "reason": None,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -v`

Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add launcher/modules/lean_ctx_mcp/__init__.py launcher/modules/lean_ctx_mcp/module.py launcher/tests/test_lean_ctx_module.py
git commit -m "$(cat <<'EOF'
feat(lean-ctx): scaffold module with check_dependencies

Creates the launcher/modules/lean_ctx_mcp/ package and implements
check_dependencies, which probes shutil.which for the lean-ctx binary
and reports availability with a brew install hint on failure.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: build_tui_section (toggle + separator + radio)

**Files:**
- Modify: `launcher/modules/lean_ctx_mcp/module.py` (add `build_tui_section`)
- Modify: `launcher/tests/test_lean_ctx_module.py` (add tests)

- [ ] **Step 1: Append failing tests**

Append to `launcher/tests/test_lean_ctx_module.py`:

```python
def test_build_tui_section_returns_toggle_separator_radio():
    items = module.build_tui_section({}, {})

    assert len(items) == 3
    assert items[0]["type"] == "toggle"
    assert items[0]["label"] == "lean-ctx MCP"
    assert items[0]["key"] == "lean-ctx_mcp:enabled"
    assert items[0]["group"] == "master"

    assert items[1]["type"] == "separator"
    assert items[1]["label"] == "CRP Mode"

    assert items[2]["type"] == "radio"
    assert items[2]["key"] == "lean-ctx_mcp:crp_mode"
    assert items[2]["requires_enabled"] == "lean-ctx_mcp:enabled"
    values = [opt["value"] for opt in items[2]["options"]]
    assert values == ["off", "compact", "tdd"]


def test_build_tui_section_toggle_default_respects_saved_state():
    items_on = module.build_tui_section({}, {"enabled": True})
    items_off = module.build_tui_section({}, {"enabled": False})

    assert items_on[0]["default"] is True
    assert items_off[0]["default"] is False


def test_build_tui_section_toggle_default_true_when_unset():
    items = module.build_tui_section({}, {})
    assert items[0]["default"] is True


def test_build_tui_section_radio_default_respects_saved_state():
    items = module.build_tui_section({}, {"crp_mode": "compact"})
    assert items[2]["default"] == "compact"


def test_build_tui_section_radio_default_falls_back_when_invalid():
    items = module.build_tui_section({}, {"crp_mode": "garbage"})
    assert items[2]["default"] == "tdd"


def test_build_tui_section_radio_default_tdd_when_unset():
    items = module.build_tui_section({}, {})
    assert items[2]["default"] == "tdd"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -k "build_tui" -v`

Expected: 6 failures with `AttributeError: module ... has no attribute 'build_tui_section'`.

- [ ] **Step 3: Implement `build_tui_section`**

Append to `launcher/modules/lean_ctx_mcp/module.py`:

```python
def build_tui_section(env: dict, saved_state: dict) -> list:
    """Return TUI items: master toggle + separator + CRP mode radio."""
    saved_mode = saved_state.get("crp_mode", DEFAULT_CRP_MODE)
    if saved_mode not in VALID_CRP_MODES:
        saved_mode = DEFAULT_CRP_MODE

    return [
        {
            "type": "toggle",
            "label": "lean-ctx MCP",
            "key": "lean-ctx_mcp:enabled",
            "default": saved_state.get("enabled", True),
            "group": "master",
        },
        {
            "type": "separator",
            "label": "CRP Mode",
        },
        {
            "type": "radio",
            "label": "CRP Mode",
            "key": "lean-ctx_mcp:crp_mode",
            "options": [
                {"value": "off",     "label": "Off — standard Claude responses"},
                {"value": "compact", "label": "Compact — ~200 token target, abbreviations"},
                {"value": "tdd",     "label": "TDD — ≤150 tokens, maximum compression"},
            ],
            "default": saved_mode,
            "group": "settings",
            "requires_enabled": "lean-ctx_mcp:enabled",
        },
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -v`

Expected: 8 tests pass total (2 from Task 2 + 6 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add launcher/modules/lean_ctx_mcp/module.py launcher/tests/test_lean_ctx_module.py
git commit -m "$(cat <<'EOF'
feat(lean-ctx): add build_tui_section with toggle + CRP radio

Master enable toggle plus a CRP Mode radio (Off/Compact/TDD, default
TDD) gated on the toggle via requires_enabled. Saved CRP mode
persists across sessions; invalid stored modes fall back to TDD.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: System prompt fragment file

**Files:**
- Create: `launcher/modules/lean_ctx_mcp/prompts/tool-preference.md`

This is a pure file-creation task — no tests. The content matches lean-ctx's `CLAUDE_GLOBAL.md` strong-language directive plus the actionable `ctx_read Modes` and `File Editing` sections from `CLAUDE.md`.

- [ ] **Step 1: Create the prompt file**

Create `launcher/modules/lean_ctx_mcp/prompts/tool-preference.md`:

````markdown
# lean-ctx — Context Engineering Layer (Global)

You have the lean-ctx MCP server available. You MUST use it for ALL file reads, shell commands, and code searches. Using native tools wastes tokens — lean-ctx compresses everything.

## Tool Replacement Rules

| NEVER use | ALWAYS use instead |
|-----------|-------------------|
| `Read` / `View` / `cat` / `head` / `tail` | `ctx_read(path)` — cached, 8 compression modes, re-reads ~13 tokens |
| `Bash` (any shell command) | `ctx_shell(command)` — pattern compression for git/npm/cargo/docker |
| `Grep` / `Search` / `rg` | `ctx_search(pattern, path)` — compact, token-efficient results |
| `ListFiles` / `ListDirectory` / `ls` / `find` | `ctx_tree(path, depth)` — compact directory maps |

## How to Use

```
ctx_read("src/main.rs")              # instead of Read("src/main.rs")
ctx_read("src/lib.rs", mode="map")   # API surface only
ctx_shell("git status")              # instead of Bash("git status")
ctx_search("pub fn", "src/")         # instead of Grep("pub fn", "src/")
ctx_tree(".", 2)                     # instead of ListFiles(".")
```

Write, Edit, and other mutation tools have no lean-ctx equivalent — use them normally.

CRITICAL: Every time you reach for Read, Bash, Grep, or ListFiles — stop and use the lean-ctx MCP equivalent instead. This is not optional.

## ctx_read Modes

- `full` — cached read (use for files you will edit)
- `map` — deps + API signatures (use for context-only files)
- `signatures` — API surface only
- `diff` — changed lines only (after edits)
- `aggressive` — syntax stripped
- `entropy` — Shannon + Jaccard filtering
- `lines:N-M` — specific range

## File Editing

Use native Edit/StrReplace when available. If Edit requires Read and Read is unavailable,
use `ctx_edit(path, old_string, new_string)` — it reads, replaces, and writes in one MCP call.
NEVER loop trying to make Edit work. If it fails, switch to ctx_edit immediately.
Write, Delete have no lean-ctx equivalent — use them normally.
````

- [ ] **Step 2: Verify file exists with expected length**

Run: `wc -l /Users/martinkuek/Documents/Projects/skills/launcher/modules/lean_ctx_mcp/prompts/tool-preference.md`

Expected: ~36 lines.

- [ ] **Step 3: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add launcher/modules/lean_ctx_mcp/prompts/tool-preference.md
git commit -m "$(cat <<'EOF'
feat(lean-ctx): add tool-preference system prompt fragment

Strong-language directive (NEVER/ALWAYS table + CRITICAL reminder)
sourced from upstream CLAUDE_GLOBAL.md, plus ctx_read modes and
file editing nuance from CLAUDE.md. Loaded by build_prompt at
launch and injected via --append-system-prompt-file.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: build_prompt

**Files:**
- Modify: `launcher/modules/lean_ctx_mcp/module.py` (add `build_prompt`)
- Modify: `launcher/tests/test_lean_ctx_module.py` (add tests)

- [ ] **Step 1: Append failing tests**

Append to `launcher/tests/test_lean_ctx_module.py`:

```python
def test_build_prompt_returns_strong_language_when_enabled():
    result = module.build_prompt({}, {"enabled": True})

    assert "NEVER use" in result
    assert "ALWAYS use" in result
    assert "ctx_read" in result
    assert "ctx_shell" in result
    assert "CRITICAL" in result


def test_build_prompt_includes_modes_and_editing_sections():
    result = module.build_prompt({}, {"enabled": True})

    assert "ctx_read Modes" in result
    assert "signatures" in result
    assert "File Editing" in result
    assert "ctx_edit" in result


def test_build_prompt_returns_empty_when_disabled():
    result = module.build_prompt({}, {"enabled": False})
    assert result == ""


def test_build_prompt_defaults_to_enabled_when_key_absent():
    result = module.build_prompt({}, {})
    assert "ctx_read" in result


def test_build_prompt_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "PROMPTS_DIR", tmp_path)
    result = module.build_prompt({}, {"enabled": True})
    assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -k "build_prompt" -v`

Expected: 5 failures with `AttributeError`.

- [ ] **Step 3: Implement `build_prompt`**

Append to `launcher/modules/lean_ctx_mcp/module.py`:

```python
def build_prompt(env: dict, selections: dict) -> str:
    """Return the tool-preference system prompt fragment.

    Returns empty string when the module is disabled or the prompt
    file is missing.
    """
    if not selections.get("enabled", True):
        return ""

    prompt_file = PROMPTS_DIR / "tool-preference.md"
    if not prompt_file.exists():
        return ""
    return prompt_file.read_text()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -v`

Expected: 13 tests pass total (8 prior + 5 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add launcher/modules/lean_ctx_mcp/module.py launcher/tests/test_lean_ctx_module.py
git commit -m "$(cat <<'EOF'
feat(lean-ctx): add build_prompt loading tool-preference fragment

Reads prompts/tool-preference.md and returns it verbatim. Empty
string when the module is disabled or the prompt file is missing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: _ensure_sandbox_home helper

**Files:**
- Modify: `launcher/modules/lean_ctx_mcp/module.py` (add `_ensure_sandbox_home`)
- Modify: `launcher/tests/test_lean_ctx_module.py` (add tests)

The sandbox creates `~/.cache/claude-launcher/lean-ctx-home/` containing a symlink `.lean-ctx → ~/.lean-ctx`. Tests must use `monkeypatch` to redirect `SANDBOX_HOME` to a `tmp_path` so the real cache dir is not touched.

- [ ] **Step 1: Append failing tests**

Append to `launcher/tests/test_lean_ctx_module.py`:

```python
def test_ensure_sandbox_home_creates_dir_and_symlink(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    real_lean_ctx = tmp_path / "fake-home" / ".lean-ctx"
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home"))

    result = module._ensure_sandbox_home()

    assert result == sandbox
    assert sandbox.is_dir()
    link = sandbox / ".lean-ctx"
    assert link.is_symlink()
    assert os.readlink(link) == str(real_lean_ctx)


def test_ensure_sandbox_home_idempotent(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home"))

    module._ensure_sandbox_home()
    result = module._ensure_sandbox_home()  # second call, no-op

    assert result == sandbox
    assert (sandbox / ".lean-ctx").is_symlink()


def test_ensure_sandbox_home_falls_back_when_non_symlink_blocks_path(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True)
    # Pre-place a directory (not a symlink) at .lean-ctx
    (sandbox / ".lean-ctx").mkdir()

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    result = module._ensure_sandbox_home()

    assert result == fake_home  # fallback to real HOME


def test_ensure_sandbox_home_falls_back_when_symlink_creation_fails(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    def raising_symlink(self, target):
        raise OSError("permission denied")

    monkeypatch.setattr(module.Path, "symlink_to", raising_symlink)

    result = module._ensure_sandbox_home()

    assert result == fake_home  # fallback to real HOME


def test_ensure_sandbox_home_falls_back_when_mkdir_fails(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    def raising_mkdir(self, *args, **kwargs):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(module.Path, "mkdir", raising_mkdir)

    result = module._ensure_sandbox_home()

    assert result == fake_home  # fallback to real HOME
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -k "sandbox" -v`

Expected: 5 failures with `AttributeError: module ... has no attribute '_ensure_sandbox_home'`.

- [ ] **Step 3: Implement `_ensure_sandbox_home`**

Append to `launcher/modules/lean_ctx_mcp/module.py`:

```python
def _ensure_sandbox_home() -> Path:
    """Provision the sandbox HOME dir with a .lean-ctx symlink preserving state.

    Returns the sandbox path on success, or real ~ as a fallback if the
    sandbox cannot be prepared (warning printed to stderr). Callers should
    use the returned path as the HOME env var for the MCP subprocess.
    """
    import sys

    try:
        SANDBOX_HOME.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Warning: lean-ctx sandbox HOME creation failed: {e}", file=sys.stderr)
        return Path.home()

    real_lean_ctx = Path.home() / ".lean-ctx"
    link = SANDBOX_HOME / ".lean-ctx"

    if link.is_symlink():
        return SANDBOX_HOME

    if link.exists():
        print(
            f"Warning: {link} is not a symlink; skipping sandbox (state may be split)",
            file=sys.stderr,
        )
        return Path.home()

    try:
        link.symlink_to(real_lean_ctx)
    except OSError as e:
        print(f"Warning: lean-ctx sandbox symlink failed: {e}", file=sys.stderr)
        return Path.home()

    return SANDBOX_HOME
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -v`

Expected: 18 tests pass total (13 prior + 5 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add launcher/modules/lean_ctx_mcp/module.py launcher/tests/test_lean_ctx_module.py
git commit -m "$(cat <<'EOF'
feat(lean-ctx): add _ensure_sandbox_home helper

Provisions ~/.cache/claude-launcher/lean-ctx-home/ with a symlink
to real ~/.lean-ctx so the MCP subprocess sees a clean HOME (no
.claude/ to detect for inject_all_rules) while preserving lean-ctx's
own state. Falls back to real HOME on any provisioning failure with
a stderr warning, so the launcher continues to work.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: build_mcp_entries

**Files:**
- Modify: `launcher/modules/lean_ctx_mcp/module.py` (add `build_mcp_entries`)
- Modify: `launcher/tests/test_lean_ctx_module.py` (add tests)

- [ ] **Step 1: Append failing tests**

Append to `launcher/tests/test_lean_ctx_module.py`:

```python
def test_build_mcp_entries_returns_server_with_env(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SANDBOX_HOME", tmp_path / "sandbox")
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home"))

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {"enabled": True, "crp_mode": "compact"})

    assert len(result) == 1
    entry = result[0]
    assert entry["name"] == "lean-ctx"
    assert entry["type"] == "stdio"
    assert entry["command"] == "/usr/local/bin/lean-ctx"
    assert entry["args"] == []
    assert entry["env"]["LEAN_CTX_CRP_MODE"] == "compact"
    assert entry["env"]["HOME"] == str(tmp_path / "sandbox")


def test_build_mcp_entries_uses_default_crp_mode_when_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SANDBOX_HOME", tmp_path / "sandbox")
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home"))

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {"enabled": True})

    assert result[0]["env"]["LEAN_CTX_CRP_MODE"] == "tdd"


def test_build_mcp_entries_falls_back_when_invalid_crp_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SANDBOX_HOME", tmp_path / "sandbox")
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home"))

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {"enabled": True, "crp_mode": "garbage"})

    assert result[0]["env"]["LEAN_CTX_CRP_MODE"] == "tdd"


def test_build_mcp_entries_returns_empty_when_disabled():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {"enabled": False})

    assert result == []


def test_build_mcp_entries_returns_empty_when_binary_missing():
    with patch("shutil.which", return_value=None):
        result = module.build_mcp_entries({}, {"enabled": True, "crp_mode": "tdd"})

    assert result == []


def test_build_mcp_entries_defaults_to_enabled_when_key_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SANDBOX_HOME", tmp_path / "sandbox")
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home"))

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {})

    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -k "build_mcp" -v`

Expected: 6 failures with `AttributeError`.

- [ ] **Step 3: Implement `build_mcp_entries`**

Append to `launcher/modules/lean_ctx_mcp/module.py`:

```python
def build_mcp_entries(env: dict, selections: dict) -> list[dict]:
    """Return the lean-ctx MCP server entry with CRP mode + sandboxed HOME.

    The HOME override prevents lean-ctx's inject_all_rules from writing to
    the real ~/.claude/CLAUDE.md (it writes to the sandbox dir instead).
    Returns empty list if the module is disabled or the binary is missing.
    """
    if not selections.get("enabled", True):
        return []

    binary_path = shutil.which("lean-ctx")
    if not binary_path:
        return []

    crp_mode = selections.get("crp_mode", DEFAULT_CRP_MODE)
    if crp_mode not in VALID_CRP_MODES:
        crp_mode = DEFAULT_CRP_MODE

    sandbox_home = _ensure_sandbox_home()

    return [
        {
            "name": "lean-ctx",
            "type": "stdio",
            "command": binary_path,
            "args": [],
            "env": {
                "HOME": str(sandbox_home),
                "LEAN_CTX_CRP_MODE": crp_mode,
            },
        }
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -v`

Expected: 24 tests pass total (18 prior + 6 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add launcher/modules/lean_ctx_mcp/module.py launcher/tests/test_lean_ctx_module.py
git commit -m "$(cat <<'EOF'
feat(lean-ctx): add build_mcp_entries with CRP mode and sandbox HOME

Returns the lean-ctx stdio MCP entry wired with LEAN_CTX_CRP_MODE
(from TUI selection, defaulting to TDD) and HOME pointing at the
sandbox dir provisioned by _ensure_sandbox_home. Empty list when
the module is disabled or the binary is missing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: build_hooks

**Files:**
- Modify: `launcher/modules/lean_ctx_mcp/module.py` (add `build_hooks`)
- Modify: `launcher/tests/test_lean_ctx_module.py` (add tests)

The hook registration uses `lean-ctx hook rewrite` directly (the binary subcommand). No shell scripts to write — the binary handles the hook protocol natively, transforming whitelisted Bash commands into `lean-ctx -c "<cmd>"` wrappers via `updatedInput`.

- [ ] **Step 1: Append failing tests**

Append to `launcher/tests/test_lean_ctx_module.py`:

```python
def test_build_hooks_returns_bash_rewrite_entry():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_hooks({}, {"enabled": True})

    assert "hooks" in result
    assert "PreToolUse" in result["hooks"]
    entries = result["hooks"]["PreToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "Bash"
    inner = entries[0]["hooks"]
    assert len(inner) == 1
    assert inner[0]["type"] == "command"
    assert inner[0]["command"] == "/usr/local/bin/lean-ctx hook rewrite"


def test_build_hooks_returns_empty_when_disabled():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_hooks({}, {"enabled": False})

    assert result == {}


def test_build_hooks_returns_empty_when_binary_missing():
    with patch("shutil.which", return_value=None):
        result = module.build_hooks({}, {"enabled": True})

    assert result == {}


def test_build_hooks_defaults_to_enabled_when_key_absent():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_hooks({}, {})

    assert "hooks" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -k "build_hooks" -v`

Expected: 4 failures with `AttributeError`.

- [ ] **Step 3: Implement `build_hooks`**

Append to `launcher/modules/lean_ctx_mcp/module.py`:

```python
def build_hooks(env: dict, selections: dict) -> dict:
    """Register lean-ctx's Bash-rewrite PreToolUse hook.

    The hook invokes `<lean-ctx-binary> hook rewrite` which transforms
    whitelisted Bash commands (git, cargo, npm, docker, etc.) into
    `lean-ctx -c "<cmd>"` wrappers via updatedInput, so output is
    transparently compressed. Returns empty dict when the module is
    disabled or the binary is missing.
    """
    if not selections.get("enabled", True):
        return {}

    binary_path = shutil.which("lean-ctx")
    if not binary_path:
        return {}

    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{binary_path} hook rewrite",
                        }
                    ],
                }
            ]
        }
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m pytest launcher/tests/test_lean_ctx_module.py -v`

Expected: 28 tests pass total (24 prior + 4 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add launcher/modules/lean_ctx_mcp/module.py launcher/tests/test_lean_ctx_module.py
git commit -m "$(cat <<'EOF'
feat(lean-ctx): add build_hooks for Bash-rewrite PreToolUse

Registers `<lean-ctx-binary> hook rewrite` against the Bash matcher.
The lean-ctx binary handles the hook protocol natively — no shell
script needed. Transparently rewrites whitelisted commands (git,
cargo, npm, docker, etc.) to `lean-ctx -c "<cmd>"` for output
compression. Empty dict when disabled or binary missing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: End-to-end smoke verification

**Files:** None (manual verification)

This task confirms the module works end-to-end with a real `lean-ctx` binary. **Requires** `lean-ctx` installed on PATH — install via `brew install lean-ctx` if missing.

If `lean-ctx` is not available locally, skip the runtime steps but still complete Steps 1, 6, and 7 (file/state inspection).

- [ ] **Step 1: Verify pre-test state of `~/.claude/CLAUDE.md`**

```bash
# Record current state for later comparison
if [ -f ~/.claude/CLAUDE.md ]; then
  cp ~/.claude/CLAUDE.md /tmp/claude-md-before.snapshot
  echo "Snapshot saved. SHA256: $(shasum -a 256 ~/.claude/CLAUDE.md | cut -d' ' -f1)"
else
  echo "ABSENT" > /tmp/claude-md-before.snapshot
  echo "~/.claude/CLAUDE.md does not exist"
fi
```

Expected: prints either the SHA or "absent".

- [ ] **Step 2: Confirm lean-ctx binary present**

Run: `which lean-ctx && lean-ctx --version`

Expected: prints binary path and version. If absent: `brew install lean-ctx`, then re-run.

- [ ] **Step 3: Launch the launcher and enable lean-ctx with TDD CRP mode**

Run: `cd /Users/martinkuek/Documents/Projects/skills && python -m launcher.launcher`

In the TUI:
- Confirm "lean-ctx MCP" appears as a checkbox option
- Confirm a "── CRP Mode ──" separator appears
- Tick "lean-ctx MCP", press Enter
- A second prompt should appear: "CRP Mode:" with three options (Off / Compact / TDD)
- Select "TDD" and press Enter

Claude Code launches.

- [ ] **Step 4: Verify MCP server loaded**

Inside the Claude Code session, run: `/mcp` (or check the tool list)

Expected: `lean-ctx` server listed; tools like `ctx_read`, `ctx_shell`, `ctx_search`, `ctx_tree` available.

- [ ] **Step 5: Verify Bash hook fires**

In the Claude Code session, ask Claude to run a `Bash` command (e.g., `git status`). Inspect the output.

Expected: output is compressed/shortened — visibly distinct from a raw `git status`. (The hook rewrites the command to `lean-ctx -c "git status"` transparently.)

- [ ] **Step 6: Verify the sandbox HOME isolation worked**

Exit Claude Code (Ctrl-D or `/exit`). Then:

```bash
# Real ~/.claude/CLAUDE.md must be unchanged
if [ "$(cat /tmp/claude-md-before.snapshot)" = "ABSENT" ]; then
  if [ -f ~/.claude/CLAUDE.md ]; then
    echo "FAIL: ~/.claude/CLAUDE.md was created (sandbox failed)"
  else
    echo "OK: ~/.claude/CLAUDE.md still absent"
  fi
else
  if [ "$(shasum -a 256 ~/.claude/CLAUDE.md | cut -d' ' -f1)" = "$(shasum -a 256 /tmp/claude-md-before.snapshot | cut -d' ' -f1)" ]; then
    echo "OK: ~/.claude/CLAUDE.md unchanged"
  else
    echo "FAIL: ~/.claude/CLAUDE.md was modified"
  fi
fi

# The injection should have landed in the sandbox
ls -la ~/.cache/claude-launcher/lean-ctx-home/
ls -la ~/.cache/claude-launcher/lean-ctx-home/.lean-ctx
test -f ~/.cache/claude-launcher/lean-ctx-home/.claude/CLAUDE.md && \
  echo "OK: sandbox CLAUDE.md exists" || \
  echo "NOTE: sandbox CLAUDE.md not present (lean-ctx may have skipped if claude not detected)"
```

Expected:
- "OK: ~/.claude/CLAUDE.md unchanged" (or still absent)
- `~/.cache/claude-launcher/lean-ctx-home/.lean-ctx` is a symlink to `~/.lean-ctx`
- `~/.cache/claude-launcher/lean-ctx-home/.claude/CLAUDE.md` exists (the injection landed in the sandbox)

- [ ] **Step 7: Verify state persistence**

Re-run the launcher: `python -m launcher.launcher`

Expected: the lean-ctx toggle is checked by default (last state preserved); the CRP mode prompt re-appears with TDD highlighted as the default.

Cancel out of the TUI (Ctrl-C).

Inspect saved state:

```bash
cat .claude-launcher-state.json | python3 -c "import sys, json; print(json.dumps(json.load(sys.stdin).get('lean-ctx_mcp', {}), indent=2))"
```

Expected output:
```json
{
  "enabled": true,
  "crp_mode": "tdd"
}
```

- [ ] **Step 8: Cleanup snapshot**

```bash
rm -f /tmp/claude-md-before.snapshot
```

- [ ] **Step 9: Document end-to-end success**

If all prior steps passed, no further action — feature is verified. Optionally update the spec status to "Implemented" (`docs/superpowers/specs/2026-04-16-lean-ctx-launcher-module-design.md`).

---

## Verification Summary

After completing all tasks, you should have:

| Artifact | Path |
|----------|------|
| Module package | `launcher/modules/lean_ctx_mcp/__init__.py` |
| Module code | `launcher/modules/lean_ctx_mcp/module.py` |
| System prompt | `launcher/modules/lean_ctx_mcp/prompts/tool-preference.md` |
| Module tests | `launcher/tests/test_lean_ctx_module.py` (28 tests) |
| Launcher framework | `launcher/launcher.py` (split `run_tui` + `_run_radio_stage`) |
| Framework tests | `launcher/tests/test_launcher.py` (4 new radio tests) |
| 8 commits | One per implementation task (tasks 1–8) |

Total test count delta: launcher framework +4, lean-ctx module +28 = **+32 tests**.
