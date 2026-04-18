"""lean-ctx MCP module for the Claude Code launcher."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

VALID_CRP_MODES = ("off", "compact", "tdd")
DEFAULT_CRP_MODE = "tdd"

# Sandbox HOME for the MCP subprocess. Prevents lean-ctx's inject_all_rules
# from writing to the real ~/.claude/CLAUDE.md. The .lean-ctx symlink preserves
# lean-ctx's own state (cache, config, knowledge) across sessions.
SANDBOX_HOME = Path.home() / ".cache" / "claude-launcher" / "lean-ctx-home"

# Paths lean-ctx setup writes into (relative to HOME)
_RULES_REL = Path(".claude") / "rules" / "lean-ctx.md"
_SETTINGS_REL = Path(".claude") / "settings.json"

# Module-level flag: run setup at most once per launcher invocation.
_setup_done = False


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
                {"value": "off", "label": "Off — standard Claude responses"},
                {
                    "value": "compact",
                    "label": "Compact — ~200 token target, abbreviations",
                },
                {"value": "tdd", "label": "TDD — ≤150 tokens, maximum compression"},
            ],
            "default": saved_mode,
            "group": "settings",
            "requires_enabled": "lean-ctx_mcp:enabled",
        },
    ]


def build_prompt(env: dict, selections: dict) -> str:
    """Return the tool-preference system prompt fragment.

    Runs lean-ctx setup in the sandbox to generate rules, then reads the
    generated rules file.  Returns empty string (with a warning) when
    the module is disabled, setup fails, or the rules file is absent.
    """
    if not selections.get("enabled", True):
        return ""

    binary_path = shutil.which("lean-ctx")
    if not binary_path:
        return ""

    sandbox_home = _ensure_sandbox_home()
    if sandbox_home == Path.home():
        # Sandbox creation failed — don't run setup against real HOME.
        print(
            "Warning: lean-ctx sandbox unavailable; skipping prompt extraction",
            file=sys.stderr,
        )
        return ""

    _ensure_lean_ctx_setup(sandbox_home, binary_path)

    rules_file = sandbox_home / _RULES_REL
    if not rules_file.is_file():
        print(
            "Warning: lean-ctx setup did not produce a rules file; "
            "no prompt fragment injected",
            file=sys.stderr,
        )
        return ""
    try:
        return rules_file.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Warning: could not read lean-ctx rules file: {e}", file=sys.stderr)
        return ""


def _run_lean_ctx_setup(sandbox_home: Path, binary_path: str) -> bool:
    """Run ``lean-ctx init --agent claude`` non-interactively in the sandbox.

    `lean-ctx setup` only installs shell aliases in non-interactive mode;
    the agent-install step (which writes `.claude/rules/lean-ctx.md`,
    `.claude/settings.json`, and the hook scripts) is skipped. `init
    --agent claude` performs that step directly and is the command we
    actually need.

    Returns True on success, False (with a warning) on failure.
    """
    env = {**os.environ, "HOME": str(sandbox_home)}
    try:
        subprocess.run(
            [binary_path, "init", "--agent", "claude"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=str(sandbox_home),
            timeout=30,
        )
        return True
    except subprocess.TimeoutExpired:
        print("Warning: lean-ctx setup timed out", file=sys.stderr)
        return False
    except OSError as e:
        print(f"Warning: lean-ctx setup failed: {e}", file=sys.stderr)
        return False


def _ensure_lean_ctx_setup(sandbox_home: Path, binary_path: str) -> None:
    """Run lean-ctx setup at most once per launcher invocation."""
    global _setup_done
    if _setup_done:
        return
    _run_lean_ctx_setup(sandbox_home, binary_path)
    _setup_done = True


def _ensure_sandbox_home() -> Path:
    """Provision the sandbox HOME dir with a .lean-ctx symlink preserving state.

    Returns the sandbox path on success, or real ~ as a fallback if the
    sandbox cannot be prepared (warning printed to stderr). Callers should
    use the returned path as the HOME env var for the MCP subprocess.
    """
    try:
        SANDBOX_HOME.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Warning: lean-ctx sandbox HOME creation failed: {e}", file=sys.stderr)
        return Path.home()

    real_lean_ctx = Path.home() / ".lean-ctx"
    link = SANDBOX_HOME / ".lean-ctx"

    if link.is_symlink():
        try:
            current_target = Path(os.readlink(link))
        except OSError as e:
            print(f"Warning: failed to read symlink {link}: {e}", file=sys.stderr)
            return Path.home()
        if current_target == real_lean_ctx:
            return SANDBOX_HOME
        print(
            f"Warning: {link} points to {current_target}, expected {real_lean_ctx}; "
            "skipping sandbox (state may be split)",
            file=sys.stderr,
        )
        return Path.home()

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


def build_hooks(env: dict, selections: dict) -> dict:
    """Return hooks configuration extracted from lean-ctx setup output.

    Runs lean-ctx setup in the sandbox (if not already done) and reads
    the generated settings.json for hook definitions.  Returns empty
    dict when the module is disabled, setup fails, or no hooks found.
    """
    if not selections.get("enabled", True):
        return {}

    binary_path = shutil.which("lean-ctx")
    if not binary_path:
        return {}

    sandbox_home = _ensure_sandbox_home()
    if sandbox_home == Path.home():
        print(
            "Warning: lean-ctx sandbox unavailable; skipping hooks extraction",
            file=sys.stderr,
        )
        return {}

    _ensure_lean_ctx_setup(sandbox_home, binary_path)

    settings_file = sandbox_home / _SETTINGS_REL
    if not settings_file.is_file():
        print(
            "Warning: lean-ctx setup did not produce a settings file; "
            "no hooks injected",
            file=sys.stderr,
        )
        return {}
    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: could not read lean-ctx settings: {e}", file=sys.stderr)
        return {}

    hooks = data.get("hooks")
    if not hooks:
        return {}
    return {"hooks": hooks}
