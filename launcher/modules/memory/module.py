"""Memory system module for the Claude Code launcher.

Implements the three-function module interface:
- check_dependencies: validates PAT, MEMORY_REPO, mdedit
- build_tui_section: fetches _config.yaml, returns menu items
- build_prompt: fetches memory files, assembles system prompt fragment
"""

import concurrent.futures
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

# In-process cache for _config.yaml — avoids a redundant fetch between
# build_tui_section() and build_prompt() within the same launcher invocation.
_CONFIG_CACHE: dict[str, str] = {}


def _cache_key(env: dict) -> str:
    return f"{env.get('PAT', '')}:{env.get('MEMORY_REPO', '')}"


def _safe_result(future) -> Optional[object]:
    """Return future.result() or None on any exception."""
    if future is None:
        return None
    try:
        return future.result()
    except Exception:
        return None


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
        _CONFIG_CACHE[_cache_key(env)] = config_yaml  # cache for build_prompt
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


def _get_last_modified(git_working, file_path: str) -> str:
    """Return the last-modified date for file_path on the working branch.

    git_working must be a GitOperations instance with branch pre-set to
    'working' (via __init__, not checkout). This avoids the 2 extra
    get_branch() API calls that checkout() would add.
    """
    try:
        log = git_working.log(path=file_path, limit=1)
        if log:
            return log[0].date
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
    # Separate lightweight connection for log() calls — branch="working" set
    # in __init__, so no checkout() calls are needed (each checkout() adds a
    # get_branch() API call). Keeping this separate from `memory` also avoids
    # any shared-state concerns when log() and fetch() run in parallel threads.
    git_working = _connect_lightweight(env)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache_key = _cache_key(env)

    selected_files = {k: v for k, v in selections.get("selected_files", {}).items() if v}

    # Determine which templates to fetch (derived from memory.config, no network call)
    template_fetches: list[tuple[str, str]] = []  # [(cat_path, template_name), ...]
    if selections.get("templates_enabled"):
        for space_name, space in memory.config.spaces.items():
            if space_name == "entities":
                continue
            for cat in space.categories:
                cat_path = f"{space_name}/{cat['name']}"
                if selected_files.get(cat_path):
                    template_fetches.append((cat_path, cat["template"]))

    # --- Submit all network calls in parallel ---
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        # Config — skip if already cached from build_tui_section()
        f_config = (
            None if cache_key in _CONFIG_CACHE
            else pool.submit(memory.fetch, "_config.yaml", return_mode="content", branch="working")
        )

        # File contents (one per enabled selected file)
        f_files = {
            path: pool.submit(memory.fetch, path, return_mode="both", branch="working")
            for path in selected_files
        }

        # Last-modified dates (one log() call per file, no checkout overhead)
        f_logs = {
            path: pool.submit(_get_last_modified, git_working, path + ".md")
            for path in selected_files
        }

        # Templates
        f_templates = {
            tmpl_name: pool.submit(memory.get_template, tmpl_name)
            for _, tmpl_name in template_fetches
        }

        # Entity manifest (main branch)
        f_manifest = (
            pool.submit(memory.fetch, "_entities_manifest.yaml", return_mode="content", branch="main")
            if selections.get("entity_manifest_enabled") else None
        )

        # Status (recent log + dirty files)
        f_status = pool.submit(memory.status)

    # --- Collect results ---
    config_content = _CONFIG_CACHE.get(cache_key)
    if f_config is not None:
        result = _safe_result(f_config)
        if result:
            config_content = result
            _CONFIG_CACHE[cache_key] = config_content

    file_results = {path: _safe_result(f) for path, f in f_files.items()}
    log_results = {path: _safe_result(f) for path, f in f_logs.items()}
    tmpl_results = {name: _safe_result(f) for name, f in f_templates.items()}
    manifest_content = _safe_result(f_manifest)
    status_info = _safe_result(f_status)

    # --- Assemble prompt (same structure as before) ---
    parts = []
    parts.append("# Continuity Memory System\n")

    if config_content:
        parts.append(f'<memory-system-config retrieved="{now}">')
        parts.append(config_content.strip())
        parts.append("</memory-system-config>\n")

    for file_path in selected_files:
        content = file_results.get(file_path)
        if content is None:
            continue
        last_mod = log_results.get(file_path) or "unknown"
        parts.append(f'<memory file="{file_path}" branch="working" last_modified="{last_mod}">')
        parts.append(content.strip())
        parts.append("</memory>\n")

    if template_fetches:
        for _, tmpl_name in template_fetches:
            tmpl = tmpl_results.get(tmpl_name)
            if tmpl:
                parts.append(f'<memory-template name="{tmpl_name}">')
                parts.append(tmpl.strip())
                parts.append("</memory-template>\n")

    if manifest_content:
        parts.append(f'<memory-entity-manifest retrieved="{now}">')
        parts.append(manifest_content.strip())
        parts.append("</memory-entity-manifest>\n")

    if status_info:
        if status_info.get("recent_log"):
            parts.append("<memory-recent-log>")
            for entry in status_info["recent_log"][:5]:
                parts.append(f'  [{entry["date"]}] {entry["message"][:120]}')
            parts.append("</memory-recent-log>\n")
        if status_info.get("dirty_files"):
            parts.append("<memory-dirty-files>")
            for f in status_info["dirty_files"]:
                parts.append(f"  - {f}")
            parts.append("</memory-dirty-files>\n")

    parts.append("---\n")
    parts.append(_read_prompt_fragments())

    return "\n".join(parts)
