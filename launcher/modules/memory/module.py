"""Memory system module for the Claude Code launcher.

Implements the three-function module interface:
- check_dependencies: validates PAT, MEMORY_REPO, mdedit
- build_tui_section: fetches _config.yaml, returns menu items
- build_prompt: fetches memory files, assembles system prompt fragment
"""

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Resolve paths to memory system dependencies
_SKILLS_ROOT = Path(__file__).resolve().parents[3]  # launcher/modules/memory -> skills/
_GITHUB_API_SCRIPTS = str(_SKILLS_ROOT / "common" / "github-api" / "scripts")
_MEMORY_SCRIPTS = str(_SKILLS_ROOT / "common" / "continuity-memory" / "scripts")

MODULE_DIR = Path(__file__).parent
PROMPTS_DIR = MODULE_DIR / "prompts"


def check_dependencies(env: dict) -> dict:
    missing = []
    if not env.get("PAT"):
        missing.append("PAT")
    if not env.get("MEMORY_REPO"):
        missing.append("MEMORY_REPO")

    if missing:
        return {
            "available": False,
            "name": "Memory System",
            "reason": f"Missing in .env: {', '.join(missing)}",
        }

    if not shutil.which("mdedit"):
        return {
            "available": False,
            "name": "Memory System",
            "reason": "mdedit not found on PATH",
        }

    return {
        "available": True,
        "name": "Memory System",
        "reason": None,
    }
