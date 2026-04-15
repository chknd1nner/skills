"""Codebase-Memory MCP module for the Claude Code launcher."""

import os
import shutil
from pathlib import Path

MODULE_DIR = Path(__file__).parent
PROMPTS_DIR = MODULE_DIR / "prompts"
REFERENCES_DIR = MODULE_DIR / "references"
HOOKS_DIR = MODULE_DIR / "hooks"


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


def build_mcp_entries(env: dict, selections: dict) -> list[dict]:
    """Return CBM MCP server entry."""
    if not selections.get("enabled", True):
        return []

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


def build_prompt(env: dict, selections: dict) -> str:
    """Return code discovery prompt with absolute path to references."""
    prompt_file = PROMPTS_DIR / "code-discovery.md"
    if not prompt_file.exists():
        return ""

    content = prompt_file.read_text()
    references_path = str(REFERENCES_DIR.resolve())
    content = content.replace("{{REFERENCES_PATH}}", references_path)

    return content


def build_tui_section(env: dict, saved_state: dict) -> list:
    """Return TUI items — single enable toggle."""
    return [
        {
            "type": "toggle",
            "label": "Codebase-Memory MCP",
            "key": "codebase-memory_mcp:enabled",
            "default": saved_state.get("enabled", True),
            "group": "master",
        }
    ]
