"""lean-ctx MCP module for the Claude Code launcher."""

import os
import shlex
import shutil
import sys
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

    Returns empty string when the module is disabled or the prompt
    file is missing, not a regular file, or unreadable.
    """
    if not selections.get("enabled", True):
        return ""

    prompt_file = PROMPTS_DIR / "tool-preference.md"
    if not prompt_file.is_file():
        return ""
    try:
        return prompt_file.read_text(encoding="utf-8")
    except OSError:
        return ""


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
                            "command": f"{shlex.quote(binary_path)} hook rewrite",
                        }
                    ],
                }
            ]
        }
    }
