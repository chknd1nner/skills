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


def _connect_full(env: dict):
    if _GITHUB_API_SCRIPTS not in sys.path:
        sys.path.insert(0, _GITHUB_API_SCRIPTS)
    if _MEMORY_SCRIPTS not in sys.path:
        sys.path.insert(0, _MEMORY_SCRIPTS)
    from memory_system import connect as memory_connect
    env_path = os.path.join(os.getcwd(), ".env")
    memory = memory_connect(env_path=env_path)
    repo_short = memory.git.repo_name.split("/")[-1]
    memory.LOCAL_ROOT = f"/tmp/{repo_short}"
    return memory


def _get_last_modified(memory, file_path: str) -> str:
    try:
        original_branch = memory.git.branch
        try:
            memory.git.checkout("working")
            log = memory.git.log(path=file_path, limit=1)
            if log:
                return log[0].date
        finally:
            memory.git.checkout(original_branch)
    except Exception:
        pass
    return "unknown"


def _read_prompt_fragments() -> str:
    fragment_order = ["header.md", "per-response-loop.md", "api-reference.md", "forbidden-phrases.md"]
    parts = []
    for filename in fragment_order:
        path = PROMPTS_DIR / filename
        if path.exists():
            parts.append(path.read_text().strip())
    return "\n\n".join(parts)


def build_prompt(env: dict, selections: dict) -> str:
    memory = _connect_full(env)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    parts = []
    parts.append("# Continuity Memory System\n")

    try:
        config_content = memory.fetch("_config.yaml", return_mode="content", branch="working")
        parts.append(f'<memory-system-config retrieved="{now}">')
        parts.append(config_content.strip())
        parts.append("</memory-system-config>\n")
    except Exception:
        pass

    selected_files = selections.get("selected_files", {})
    for file_path, enabled in selected_files.items():
        if not enabled:
            continue
        try:
            content = memory.fetch(file_path, return_mode="both", branch="working")
            last_mod = _get_last_modified(memory, file_path + ".md")
            parts.append(f'<memory file="{file_path}" branch="working" last_modified="{last_mod}">')
            parts.append(content.strip())
            parts.append("</memory>\n")
        except Exception:
            pass

    if selections.get("templates_enabled"):
        for space_name, space in memory.config.spaces.items():
            if space_name == "entities":
                continue
            for cat in space.categories:
                cat_path = f"{space_name}/{cat['name']}"
                if cat_path not in selected_files or not selected_files.get(cat_path):
                    continue
                try:
                    tmpl = memory.get_template(cat["template"])
                    parts.append(f'<memory-template name="{cat["template"]}">')
                    parts.append(tmpl.strip())
                    parts.append("</memory-template>\n")
                except Exception:
                    pass

    if selections.get("entity_manifest_enabled"):
        try:
            manifest = memory.fetch("_entities_manifest.yaml", return_mode="content", branch="main")
            parts.append(f'<memory-entity-manifest retrieved="{now}">')
            parts.append(manifest.strip())
            parts.append("</memory-entity-manifest>\n")
        except Exception:
            pass

    try:
        info = memory.status()
        if info.get("recent_log"):
            parts.append("<memory-recent-log>")
            for entry in info["recent_log"][:5]:
                parts.append(f'  [{entry["date"]}] {entry["message"][:120]}')
            parts.append("</memory-recent-log>\n")
        if info.get("dirty_files"):
            parts.append("<memory-dirty-files>")
            for f in info["dirty_files"]:
                parts.append(f"  - {f}")
            parts.append("</memory-dirty-files>\n")
    except Exception:
        pass

    parts.append("---\n")
    parts.append(_read_prompt_fragments())

    return "\n".join(parts)
