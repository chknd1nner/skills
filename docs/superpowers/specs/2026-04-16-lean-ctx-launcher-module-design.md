# lean-ctx Launcher Module Design

**Date:** 2026-04-16
**Status:** Approved

## Overview

Integrate the `lean-ctx` MCP server into the modular launcher so sessions can selectively enable lean-ctx via a TUI toggle. When enabled, the launcher:

1. Registers `lean-ctx` as an stdio MCP server with a user-selected CRP mode (`LEAN_CTX_CRP_MODE` env var)
2. Wires a `PreToolUse` hook on `Bash` that invokes `lean-ctx hook rewrite` — transparently rewriting whitelisted shell commands to `lean-ctx -c "<cmd>"` for output compression
3. Injects a strong-language system-prompt fragment steering Claude toward `ctx_read`/`ctx_shell`/`ctx_search`/`ctx_tree`

The module mirrors the `codebase_memory_mcp` pattern and composes cleanly with it — there is no tool-matcher overlap in blocking behavior. CBM gates Grep/Glob/Read (first-call nudge); lean-ctx rewrites Bash (transparent, non-blocking). The read/search side of lean-ctx is steered entirely by the system prompt.

**Critical isolation constraint:** On MCP `initialize`, the lean-ctx server runs `inject_all_rules(&home)` unconditionally (see upstream `server.rs:29-35`), which **appends a rules block to `$HOME/.claude/CLAUDE.md`** if Claude Code is detected. There is no env-var opt-out. To keep the launcher session-ephemeral and leave the user's global Claude config untouched, the module **sandboxes `HOME`** for the MCP subprocess — pointing it at a stable per-user cache dir that contains a symlink to real `~/.lean-ctx/` so lean-ctx's own persistent state (cache, config, knowledge base) is preserved. The `.claude/CLAUDE.md` injection then writes to the sandbox instead of the real config. The Bash-rewrite hook (`lean-ctx hook rewrite`) is a pure stdin filter with no side effects, so it does **not** need the sandbox — only the long-lived MCP subprocess does.

## Goals

1. Toggle lean-ctx on/off per session via launcher TUI
2. Select CRP response mode (Off/Compact/TDD) per session via a new **radio** TUI widget
3. Wire the author-shipped `lean-ctx hook rewrite` Bash rewrite hook so shell command output is automatically compressed
4. Inject a strong-language system prompt preferring `ctx_*` MCP tools over native Read/Bash/Grep/ListFiles
5. Extend the launcher framework with a reusable `radio` TUI item type
6. Isolate lean-ctx's `inject_all_rules` side effect from the user's global `~/.claude/CLAUDE.md` via a sandboxed `HOME` with preserved `.lean-ctx` state

## Non-Goals

- Installing the `lean-ctx` binary (prerequisite: `brew install lean-ctx` or equivalent)
- Managing lean-ctx's own config (`~/.lean-ctx/config.toml`) or shell integration (zsh/bash hooks for interactive shells)
- Writing hook scripts — the module registers `lean-ctx hook rewrite` directly, using the binary's built-in subcommand
- Registering the `lean-ctx hook redirect` hook (currently a no-op in lean-ctx; dropped per YAGNI — add back if upstream gives it behavior)
- Coordinating with CBM's gate — by design, the two modules' tool matchers don't overlap in blocking behavior
- Cleaning up the sandbox `.claude/` directory at `~/.cache/claude-launcher/lean-ctx-home/.claude/` — it accumulates a single idempotent CLAUDE.md that's harmless noise. Add cleanup later if it becomes a concern.
- Upstream fix for `inject_all_rules` opt-out — tracked as a nice-to-have; the sandbox is sufficient locally

## Design

### Module Structure

```
launcher/modules/lean_ctx_mcp/
├── __init__.py                    # empty
├── module.py                      # 5-function module interface
└── prompts/
    └── tool-preference.md         # system prompt fragment
```

No `references/`, no shell scripts — the binary handles the hook behavior natively.

### module.py

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


def build_tui_section(env: dict, saved_state: dict) -> list:
    """Return TUI items — master toggle + CRP mode radio."""
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
            # Condition: only prompt if this module's master toggle is enabled.
            # Framework reads this from the sibling "enabled" key.
            "requires_enabled": "lean-ctx_mcp:enabled",
        },
    ]


def build_prompt(env: dict, selections: dict) -> str:
    """Return the tool-preference prompt. Empty if disabled."""
    if not selections.get("enabled", True):
        return ""

    prompt_file = PROMPTS_DIR / "tool-preference.md"
    if not prompt_file.exists():
        return ""
    return prompt_file.read_text()


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
        # Already set up — verify target (harmless if broken; lean-ctx creates it)
        return SANDBOX_HOME

    if link.exists():
        # Unexpected: non-symlink at the sandbox .lean-ctx path
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


def build_mcp_entries(env: dict, selections: dict) -> list[dict]:
    """Return lean-ctx MCP server entry with CRP mode + sandboxed HOME."""
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


def build_hooks(env: dict, selections: dict) -> dict:
    """Register lean-ctx's Bash rewrite PreToolUse hook."""
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

### System Prompt Content

**`prompts/tool-preference.md`** — combines lean-ctx's `CLAUDE_GLOBAL.md` strong-language directive with the actionable detail sections from `CLAUDE.md`:

```markdown
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
```

### Launcher Framework Changes

#### 1. New `radio` TUI item type

Radio items are processed in a **second-stage prompt** after the main checkbox stage. The checkbox handles all `toggle` items; then `inquirer.select` runs once per radio item whose `requires_enabled` key resolves to `True` in the checkbox output (or whose `requires_enabled` is unset).

**Radio item schema:**
```python
{
    "type": "radio",
    "label": str,                # label shown at the prompt
    "key": str,                  # single key (not per-option)
    "options": [
        {"value": str, "label": str},
        ...
    ],
    "default": str,              # value (string), not bool
    "group": str,                # display grouping (ignored by TUI for radio)
    "requires_enabled": str,     # optional — key name that must be True
                                 # for this radio to be prompted
}
```

#### 2. `launcher.py::run_tui()` changes

Split into two phases:

```python
def run_tui(all_items: list) -> dict:
    # Phase 1: split items by type
    togglable = [i for i in all_items if i.get("type") != "radio"]
    radios   = [i for i in all_items if i.get("type") == "radio"]

    # Phase 2: existing checkbox flow for toggles + separators
    selections = _run_checkbox_stage(togglable)

    # Phase 3: radio stage — one select prompt per eligible radio
    for radio in radios:
        gate_key = radio.get("requires_enabled")
        if gate_key and not selections.get(gate_key, False):
            # Skip this radio; still record the saved default so state persists
            selections[radio["key"]] = radio["default"]
            continue
        selections[radio["key"]] = _run_radio_stage(radio)

    return selections
```

`_run_checkbox_stage` is a pure extraction of the existing `run_tui` body (lines 149–176 in the current file) — same `Choice`/`Separator` construction, same `inquirer.checkbox` call, same return shape `{key: bool for key in all_keys}`. No behavior change for callers that only use toggles. `_run_radio_stage` uses `inquirer.select`:

```python
def _run_radio_stage(radio: dict) -> str:
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
```

`all_keys` in the existing return statement must include radio keys too, so selections are serialized into saved state.

#### 3. `selections_to_module_state()` changes

Today, values in `selections` are always `bool`. After the radio extension, they can also be `str`. The existing unflatten logic still works — radio values fall through to the final `else` branch (`module_states[mod_key][key] = selected`) or to the `module_name:key` branch which preserves the string value. The only change is the docstring and type hint for `selections`.

```python
def selections_to_module_state(selections: dict, all_items: list) -> dict:
    """Convert flat TUI selections back to per-module state dicts.

    Values may be bool (from toggle) or str (from radio).
    """
    # ... existing body unchanged ...
```

#### 4. `build_tui_choices()` — no changes

It already passes through arbitrary item dicts with `module_name` attached. Radio items flow through unmodified.

### Saved State Format

```json
{
  "lean_ctx_mcp": {
    "enabled": true,
    "crp_mode": "tdd"
  }
}
```

`crp_mode` is always persisted, even when the module is disabled, so toggling back on remembers the last selected mode.

### Coordination With Other Modules

**CBM (`codebase_memory_mcp`):**
- CBM hook matcher: `Grep|Glob|Read|Search` — first-call blocking nudge
- lean-ctx hook matcher: `Bash` only — transparent rewrite, non-blocking
- **Zero matcher overlap in blocking behavior.** No coordination required.

**Memory module:**
- Different subsystem (system-prompt memory injection). No interaction.

When both CBM and lean-ctx are enabled, Claude sees:
- Two MCP servers in `--mcp-config` (`codebase-memory-mcp` + `lean-ctx`)
- One `PreToolUse.Bash` hook (rewrite)
- One `PreToolUse.(Grep|Glob|Read|Search)` hook (CBM's first-call gate)
- System prompt containing both the CBM code-discovery protocol and the lean-ctx tool-preference directive

## Files Changed

**Create:**
- `launcher/modules/lean_ctx_mcp/__init__.py` (empty)
- `launcher/modules/lean_ctx_mcp/module.py`
- `launcher/modules/lean_ctx_mcp/prompts/tool-preference.md`
- `launcher/tests/test_lean_ctx_module.py`

**Modify:**
- `launcher/launcher.py` — split `run_tui()` into toggle + radio phases; add `_run_radio_stage()`; include radio keys in returned `all_keys`
- `launcher/tests/test_launcher.py` — add tests for radio-phase skipping when `requires_enabled` gate is False

**Precondition (user-performed, outside the module):**
- Install `lean-ctx` binary: `brew install lean-ctx`

## Testing

### Module tests (`test_lean_ctx_module.py`)

Mirror the CBM test file structure:

1. `check_dependencies` — binary found vs missing
2. `build_tui_section` — returns toggle + separator + radio; radio options have correct values; defaults respect saved state; invalid saved `crp_mode` falls back to `tdd`
3. `build_prompt` — reads file, contains "NEVER use" strong-language; empty when disabled; empty when file missing
4. `build_mcp_entries` — returns single entry with `LEAN_CTX_CRP_MODE` + `HOME` in env; HOME points at sandbox dir; uses saved `crp_mode`; empty when disabled; empty when binary missing; invalid `crp_mode` falls back to `tdd`
5. `build_hooks` — returns `PreToolUse.Bash` hook with absolute binary path + `hook rewrite` subcommand; empty when disabled; empty when binary missing
6. `_ensure_sandbox_home` — creates `~/.cache/claude-launcher/lean-ctx-home/` and `.lean-ctx` symlink on first call; idempotent on subsequent calls; falls back to real HOME on symlink failure; falls back to real HOME when non-symlink already at sandbox `.lean-ctx` path

### Launcher framework tests (`test_launcher.py`)

1. `run_tui` with radio item — select stage runs when `requires_enabled` key is True
2. `run_tui` with radio item — select stage skipped when `requires_enabled` key is False; saved default persisted
3. `run_tui` with radio item — select stage runs when `requires_enabled` is absent
4. `selections_to_module_state` — radio string values round-trip to module state correctly

### End-to-end verification

1. Enable lean-ctx in launcher TUI, pick each CRP mode → launch Claude → verify MCP server loads and `ctx_read` tool is available
2. Run `Bash("git status")` in session → verify output appears compressed (hook fired)
3. Verify saved state persists across launcher invocations (disable, re-enable, confirm mode preserved)
4. Enable both CBM and lean-ctx → verify no hook conflict; both MCP servers present
5. **Sandbox HOME verification:** before first launch, record the content of `~/.claude/CLAUDE.md` (or note its absence). After launching Claude with lean-ctx enabled and allowing the MCP server to initialize, re-check `~/.claude/CLAUDE.md` — it must be **unchanged**. Confirm the injection landed in `~/.cache/claude-launcher/lean-ctx-home/.claude/CLAUDE.md` instead. Confirm `~/.cache/claude-launcher/lean-ctx-home/.lean-ctx` is a symlink resolving to `~/.lean-ctx`.

## Open Questions

None — design approved.
