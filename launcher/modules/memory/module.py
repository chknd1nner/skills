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


def _connect_lightweight(env: dict):
    if _GITHUB_API_SCRIPTS not in sys.path:
        sys.path.insert(0, _GITHUB_API_SCRIPTS)
    from git_operations import GitOperations
    return GitOperations(token=env["PAT"], repo_name=env["MEMORY_REPO"], branch="working")


def _parse_config_categories(config_yaml: str) -> list:
    if _GITHUB_API_SCRIPTS not in sys.path:
        sys.path.insert(0, _GITHUB_API_SCRIPTS)
    if _MEMORY_SCRIPTS not in sys.path:
        sys.path.insert(0, _MEMORY_SCRIPTS)
    from memory_system import MemoryConfig
    config = MemoryConfig.from_yaml(config_yaml)
    categories = []
    for space_name, space in config.spaces.items():
        if space_name == "entities":
            continue
        for cat in space.categories:
            categories.append(f"{space_name}/{cat['name']}")
    return categories


def build_tui_section(env: dict, saved_state: dict) -> list:
    categories = []
    try:
        git = _connect_lightweight(env)
        config_yaml = git.get("_config.yaml")
        categories = _parse_config_categories(config_yaml)
    except Exception:
        if saved_state.get("selected_files"):
            categories = list(saved_state["selected_files"].keys())

    if not categories:
        return [{
            "type": "toggle", "label": "Enable memory system",
            "key": "enabled", "default": saved_state.get("enabled", True), "group": "master",
        }]

    items = []
    items.append({"type": "toggle", "label": "Enable memory system", "key": "enabled",
                   "default": saved_state.get("enabled", True), "group": "master"})
    items.append({"type": "separator", "label": "Core Files"})

    saved_files = saved_state.get("selected_files", {})
    for cat_path in categories:
        items.append({"type": "toggle", "label": cat_path, "key": f"file:{cat_path}",
                       "default": saved_files.get(cat_path, True), "group": "files"})

    items.append({"type": "separator", "label": "Extras"})
    items.append({"type": "toggle", "label": "Templates", "key": "templates_enabled",
                   "default": saved_state.get("templates_enabled", True), "group": "extras"})
    items.append({"type": "toggle", "label": "Entity manifest", "key": "entity_manifest_enabled",
                   "default": saved_state.get("entity_manifest_enabled", True), "group": "extras"})
    return items
