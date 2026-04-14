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
