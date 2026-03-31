# Claude Code Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a modular Python launcher that discovers modules, presents a TUI, assembles a system prompt from module contributions, and launches Claude Code with `--append-system-prompt-file`.

**Architecture:** A launcher core (`launcher.py`, `config.py`, `prompt_builder.py`) discovers modules in `modules/`, calls their three-function interface (`check_dependencies` → `build_tui_section` → `build_prompt`), composes TUI and system prompt from results, and exec's `claude`. The memory system is the first module, with behavioral instructions stored as `.md` fragments.

**Tech Stack:** Python 3, `InquirerPy` (TUI checkboxes with separators), existing `memory_system.py` + `git_operations.py` (GitHub API), `mdedit` (markdown section editor)

**Spec:** `docs/superpowers/specs/2026-03-31-claude-code-launcher-design.md`

**Design decisions & rejected alternatives:** See the brainstorming summary in the spec conversation. Key decisions: modular architecture with convention-based discovery (rejected hardcoded single-module); flat-list TUI (rejected collapsible tree and minimal on/off); `InquirerPy` for TUI (supports separators and custom styling); prompt fragments as `.md` files not Python strings; three-function module interface with escalating responsibilities; dependency checks are lightweight (no API calls), TUI builder does lightweight fetching, prompt builder does heavy fetching.

---

## File Structure

```
launcher/
├── __init__.py                          # empty
├── launcher.py                          # entry point: arg parsing, module discovery, TUI, orchestration, exec
├── config.py                            # .env parsing, state file read/write
├── prompt_builder.py                    # concatenate module prompt fragments → temp file
├── modules/
│   ├── __init__.py                      # empty
│   └── memory/
│       ├── __init__.py                  # empty
│       ├── module.py                    # three-function interface for memory system
│       └── prompts/
│           ├── header.md                # system identity, model-is-the-user, mdedit, local root
│           ├── per-response-loop.md     # entity/draft/consolidation checks
│           ├── api-reference.md         # memory API quick reference table
│           └── forbidden-phrases.md     # phrases the model must never say
tests/
└── launcher/
    ├── __init__.py                      # empty
    ├── test_config.py                   # tests for .env parsing and state file
    ├── test_prompt_builder.py           # tests for prompt assembly
    └── test_memory_module.py            # tests for memory module's three functions

# Modified:
CLAUDE.md                                # strip memory system block
.gitignore                               # add .claude-launcher-state.json, .superpowers/
```

---

### Task 1: Scaffold directory structure and install TUI dependency

**Files:**
- Create: `launcher/__init__.py`
- Create: `launcher/modules/__init__.py`
- Create: `launcher/modules/memory/__init__.py`
- Create: `launcher/modules/memory/prompts/` (directory)
- Create: `tests/launcher/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p launcher/modules/memory/prompts
mkdir -p tests/launcher
touch launcher/__init__.py
touch launcher/modules/__init__.py
touch launcher/modules/memory/__init__.py
touch tests/launcher/__init__.py
```

- [ ] **Step 2: Install InquirerPy**

```bash
pip3 install InquirerPy
```

Verify:
```bash
python3 -c "from InquirerPy import inquirer; print('InquirerPy OK')"
```
Expected: `InquirerPy OK`

- [ ] **Step 3: Add .claude-launcher-state.json and .superpowers/ to .gitignore**

Add to the end of `.gitignore`:

```
.claude-launcher-state.json
.superpowers/
```

- [ ] **Step 4: Commit**

```bash
git add launcher/ tests/launcher/ .gitignore
git commit -m "feat(launcher): scaffold directory structure"
```

---

### Task 2: config.py — .env parsing

**Files:**
- Create: `tests/launcher/test_config.py`
- Create: `launcher/config.py`

- [ ] **Step 1: Write failing tests for .env parsing**

```python
# tests/launcher/test_config.py
import os
import tempfile
import pytest
from launcher.config import parse_env


class TestParseEnv:
    def test_parses_key_value_pairs(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("PAT=ghp_abc123\nMEMORY_REPO=owner/repo\n")
        result = parse_env(str(env_file))
        assert result == {"PAT": "ghp_abc123", "MEMORY_REPO": "owner/repo"}

    def test_handles_spaces_around_equals(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("PAT = ghp_abc123\nMEMORY_REPO = owner/repo\n")
        result = parse_env(str(env_file))
        assert result == {"PAT": "ghp_abc123", "MEMORY_REPO": "owner/repo"}

    def test_skips_empty_lines_and_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nPAT=ghp_abc123\n\n# another\nMEMORY_REPO=owner/repo\n")
        result = parse_env(str(env_file))
        assert result == {"PAT": "ghp_abc123", "MEMORY_REPO": "owner/repo"}

    def test_returns_empty_dict_if_file_missing(self, tmp_path):
        result = parse_env(str(tmp_path / ".env"))
        assert result == {}

    def test_returns_empty_dict_if_no_path(self):
        result = parse_env(None)
        assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'launcher.config'`

- [ ] **Step 3: Implement parse_env**

```python
# launcher/config.py
"""Config discovery and state management for the launcher."""

import json
import os
from typing import Optional


def parse_env(path: Optional[str]) -> dict:
    """Parse a .env file into a dict of key-value pairs.

    Skips blank lines and lines starting with #.
    Returns empty dict if file doesn't exist or path is None.
    """
    if not path or not os.path.exists(path):
        return {}

    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                env[key.strip()] = val.strip()
    return env
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_config.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add launcher/config.py tests/launcher/test_config.py
git commit -m "feat(launcher): add .env parsing"
```

---

### Task 3: config.py — state file read/write

**Files:**
- Modify: `tests/launcher/test_config.py`
- Modify: `launcher/config.py`

- [ ] **Step 1: Write failing tests for state file management**

Append to `tests/launcher/test_config.py`:

```python
from launcher.config import load_state, save_state


class TestStateFile:
    def test_load_returns_empty_dict_if_missing(self, tmp_path):
        result = load_state(str(tmp_path / ".claude-launcher-state.json"))
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / ".claude-launcher-state.json")
        state = {
            "memory": {
                "enabled": True,
                "selected_files": {
                    "self/positions": True,
                    "self/methods": True,
                    "collaborator/profile": True,
                },
                "templates_enabled": True,
                "entity_manifest_enabled": True,
            }
        }
        save_state(path, state)
        loaded = load_state(path)
        assert loaded == state

    def test_save_overwrites_existing(self, tmp_path):
        path = str(tmp_path / ".claude-launcher-state.json")
        save_state(path, {"memory": {"enabled": True}})
        save_state(path, {"memory": {"enabled": False}})
        loaded = load_state(path)
        assert loaded == {"memory": {"enabled": False}}

    def test_load_returns_empty_dict_on_corrupt_json(self, tmp_path):
        path = tmp_path / ".claude-launcher-state.json"
        path.write_text("not valid json{{{")
        result = load_state(str(path))
        assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_config.py::TestStateFile -v
```

Expected: FAIL — `ImportError: cannot import name 'load_state'`

- [ ] **Step 3: Implement load_state and save_state**

Add to `launcher/config.py`:

```python
def load_state(path: str) -> dict:
    """Load launcher state from JSON file.

    Returns empty dict if file doesn't exist or is invalid JSON.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(path: str, state: dict) -> None:
    """Save launcher state to JSON file."""
    with open(path, 'w') as f:
        json.dump(state, f, indent=2)
        f.write('\n')
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_config.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add launcher/config.py tests/launcher/test_config.py
git commit -m "feat(launcher): add state file read/write"
```

---

### Task 4: Memory module — check_dependencies

**Files:**
- Create: `tests/launcher/test_memory_module.py`
- Create: `launcher/modules/memory/module.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/launcher/test_memory_module.py
import shutil
from unittest.mock import patch
from launcher.modules.memory.module import check_dependencies


class TestCheckDependencies:
    def test_available_when_all_deps_present(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        with patch("shutil.which", return_value="/usr/bin/mdedit"):
            result = check_dependencies(env)
        assert result["available"] is True
        assert result["name"] == "Memory System"
        assert result["reason"] is None

    def test_unavailable_when_pat_missing(self):
        env = {"MEMORY_REPO": "owner/repo"}
        with patch("shutil.which", return_value="/usr/bin/mdedit"):
            result = check_dependencies(env)
        assert result["available"] is False
        assert "PAT" in result["reason"]

    def test_unavailable_when_memory_repo_missing(self):
        env = {"PAT": "ghp_abc"}
        with patch("shutil.which", return_value="/usr/bin/mdedit"):
            result = check_dependencies(env)
        assert result["available"] is False
        assert "MEMORY_REPO" in result["reason"]

    def test_unavailable_when_mdedit_missing(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        with patch("shutil.which", return_value=None):
            result = check_dependencies(env)
        assert result["available"] is False
        assert "mdedit" in result["reason"]

    def test_unavailable_when_env_empty(self):
        result = check_dependencies({})
        assert result["available"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_memory_module.py::TestCheckDependencies -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement check_dependencies**

```python
# launcher/modules/memory/module.py
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
    """Can this module run at all? Lightweight checks only.

    Validates PAT and MEMORY_REPO exist in env, and mdedit is on PATH.
    No API calls at this stage.

    Args:
        env: parsed .env contents (may be empty)

    Returns:
        dict with 'available' (bool), 'name' (str), 'reason' (str|None)
    """
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_memory_module.py::TestCheckDependencies -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add launcher/modules/memory/module.py tests/launcher/test_memory_module.py
git commit -m "feat(launcher): memory module check_dependencies"
```

---

### Task 5: Memory module — build_tui_section

**Files:**
- Modify: `tests/launcher/test_memory_module.py`
- Modify: `launcher/modules/memory/module.py`

This function does a lightweight fetch of `_config.yaml` to discover category names, then returns a list of menu item dicts. Falls back to cached categories from saved_state.

- [ ] **Step 1: Write failing tests**

Append to `tests/launcher/test_memory_module.py`:

```python
from unittest.mock import patch, MagicMock
from launcher.modules.memory.module import build_tui_section


SAMPLE_CONFIG_YAML = """# _config.yaml

spaces:
  self:
    retrieval: pre-injected
    max_categories: 7
    categories:
      - name: positions
        template: self-positions.yaml
      - name: methods
        template: self-methods.yaml
  collaborator:
    retrieval: pre-injected
    max_categories: 7
    categories:
      - name: profile
        template: collaborator-profile.yaml
  entities:
    retrieval: on-demand
    template: entity.yaml
"""


class TestBuildTuiSection:
    def test_returns_items_from_config(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        saved_state = {}

        mock_git = MagicMock()
        mock_git.get.return_value = SAMPLE_CONFIG_YAML

        with patch("launcher.modules.memory.module._connect_lightweight", return_value=mock_git):
            items = build_tui_section(env, saved_state)

        # Should have: master toggle, core files (positions, methods, profile), templates, manifest
        labels = [item["label"] for item in items]
        assert "Enable memory system" in labels
        assert "self/positions" in labels
        assert "self/methods" in labels
        assert "collaborator/profile" in labels
        assert "Templates" in labels
        assert "Entity manifest" in labels

    def test_defaults_all_enabled_no_saved_state(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}

        mock_git = MagicMock()
        mock_git.get.return_value = SAMPLE_CONFIG_YAML

        with patch("launcher.modules.memory.module._connect_lightweight", return_value=mock_git):
            items = build_tui_section(env, {})

        for item in items:
            if item.get("type") != "separator":
                assert item["default"] is True

    def test_respects_saved_state(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        saved_state = {
            "enabled": True,
            "selected_files": {"self/positions": False, "self/methods": True},
            "templates_enabled": False,
            "entity_manifest_enabled": True,
        }

        mock_git = MagicMock()
        mock_git.get.return_value = SAMPLE_CONFIG_YAML

        with patch("launcher.modules.memory.module._connect_lightweight", return_value=mock_git):
            items = build_tui_section(env, saved_state)

        item_map = {i["label"]: i for i in items if i.get("type") != "separator"}
        assert item_map["self/positions"]["default"] is False
        assert item_map["self/methods"]["default"] is True
        assert item_map["Templates"]["default"] is False
        assert item_map["Entity manifest"]["default"] is True

    def test_falls_back_to_saved_state_on_fetch_failure(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        saved_state = {
            "enabled": True,
            "selected_files": {"self/positions": True, "collaborator/profile": True},
            "templates_enabled": True,
            "entity_manifest_enabled": True,
        }

        with patch("launcher.modules.memory.module._connect_lightweight", side_effect=Exception("network")):
            items = build_tui_section(env, saved_state)

        labels = [i["label"] for i in items if i.get("type") != "separator"]
        assert "self/positions" in labels
        assert "collaborator/profile" in labels
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_memory_module.py::TestBuildTuiSection -v
```

Expected: FAIL — `ImportError: cannot import name 'build_tui_section'`

- [ ] **Step 3: Implement _connect_lightweight and build_tui_section**

Add to `launcher/modules/memory/module.py`:

```python
def _connect_lightweight(env: dict):
    """Create a lightweight GitOperations connection for config fetching.

    Only used to read _config.yaml — not a full memory system connection.
    """
    if _GITHUB_API_SCRIPTS not in sys.path:
        sys.path.insert(0, _GITHUB_API_SCRIPTS)
    from git_operations import GitOperations

    return GitOperations(
        token=env["PAT"],
        repo_name=env["MEMORY_REPO"],
        branch="working",
    )


def _parse_config_categories(config_yaml: str) -> list:
    """Extract category paths from _config.yaml content.

    Returns list of strings like 'self/positions', 'collaborator/profile'.
    """
    if _MEMORY_SCRIPTS not in sys.path:
        sys.path.insert(0, _MEMORY_SCRIPTS)
    from memory_system import MemoryConfig

    config = MemoryConfig.from_yaml(config_yaml)
    categories = []
    for space_name, space in config.spaces.items():
        if space_name == "entities":
            continue  # entities are on-demand, not pre-injected
        for cat in space.categories:
            categories.append(f"{space_name}/{cat['name']}")
    return categories


def build_tui_section(env: dict, saved_state: dict) -> list:
    """What should this module show in the TUI?

    Fetches _config.yaml to discover categories. Falls back to
    cached categories from saved_state if fetch fails.

    Args:
        env: parsed .env contents
        saved_state: previous selections for this module (may be empty)

    Returns:
        list of dicts, each with:
        - type: 'toggle' | 'separator'
        - label: display text
        - key: state key for saving (toggles only)
        - default: bool (toggles only)
        - group: 'master' | 'files' | 'extras' (toggles only)
    """
    # Discover categories
    categories = []
    try:
        git = _connect_lightweight(env)
        config_yaml = git.get("_config.yaml")
        categories = _parse_config_categories(config_yaml)
    except Exception:
        # Fall back to cached state
        if saved_state.get("selected_files"):
            categories = list(saved_state["selected_files"].keys())

    if not categories:
        # No config discovered and no cache — return minimal toggle
        return [
            {
                "type": "toggle",
                "label": "Enable memory system",
                "key": "enabled",
                "default": saved_state.get("enabled", True),
                "group": "master",
            }
        ]

    # Build menu items
    items = []

    # Master toggle
    items.append({
        "type": "toggle",
        "label": "Enable memory system",
        "key": "enabled",
        "default": saved_state.get("enabled", True),
        "group": "master",
    })

    # Separator: Core Files
    items.append({"type": "separator", "label": "Core Files"})

    # One toggle per category
    saved_files = saved_state.get("selected_files", {})
    for cat_path in categories:
        items.append({
            "type": "toggle",
            "label": cat_path,
            "key": f"file:{cat_path}",
            "default": saved_files.get(cat_path, True),
            "group": "files",
        })

    # Separator: Extras
    items.append({"type": "separator", "label": "Extras"})

    items.append({
        "type": "toggle",
        "label": "Templates",
        "key": "templates_enabled",
        "default": saved_state.get("templates_enabled", True),
        "group": "extras",
    })

    items.append({
        "type": "toggle",
        "label": "Entity manifest",
        "key": "entity_manifest_enabled",
        "default": saved_state.get("entity_manifest_enabled", True),
        "group": "extras",
    })

    return items
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_memory_module.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add launcher/modules/memory/module.py tests/launcher/test_memory_module.py
git commit -m "feat(launcher): memory module build_tui_section"
```

---

### Task 6: Memory module prompt fragments

**Files:**
- Create: `launcher/modules/memory/prompts/header.md`
- Create: `launcher/modules/memory/prompts/per-response-loop.md`
- Create: `launcher/modules/memory/prompts/api-reference.md`
- Create: `launcher/modules/memory/prompts/forbidden-phrases.md`

These are lifted from the current `CLAUDE.md` (lines 14–252), adapted for Claude Code. The session-start Python block is removed entirely — the launcher handles that. References to `mdedit` are kept. The `LOCAL_ROOT` is set to `/tmp/{repo}` rather than hardcoded.

- [ ] **Step 1: Create header.md**

```markdown
# Memory System

You have a continuity-memory system active. The memory content above (in `<memory>` tags) was pre-loaded before this session started. Treat it as immediate awareness — you already know this information.

## Core Principle: The Model Is the User

Everything in the memory system is your perspective. Collaborator space is your working understanding of who you're helping. Self space is your actual development. Entities are things you need to understand to do your job well. This is a trainer's notebook, not a client's intake form.

## Editing Tool

Use `mdedit` for all memory file edits. It is available as a CLI tool on PATH.

- Replace a section: `mdedit replace <file> "<heading>" --content "<new content>"`
- Append to a section: `mdedit append <file> "<heading>" --content "<new content>"`
- Remove a section: `mdedit remove <file> "<heading>"`

The local root for memory files is `/tmp/{repo}` where `{repo}` is the short name of the memory repository (visible in the `<memory-system-config>` tag above).

## Connection

The memory system Python API is available. To use it:

```python
import sys
sys.path.insert(0, '/Users/martinkuek/Documents/Projects/skills/common/github-api/scripts')
sys.path.insert(0, '/Users/martinkuek/Documents/Projects/skills/common/continuity-memory/scripts')
from memory_system import connect

memory = connect(env_path='/Users/martinkuek/Documents/Projects/skills/.env')
repo_short = memory.git.repo_name.split('/')[-1]
memory.LOCAL_ROOT = f'/tmp/{repo_short}'
```

You do not need to run session-start code — the launcher has already fetched and injected all memory content. Use the API when you need to **write** (commit, consolidate, create entities).
```

Write this content to `launcher/modules/memory/prompts/header.md`.

- [ ] **Step 2: Create per-response-loop.md**

This is the largest fragment. Lift lines 85–224 from the current `CLAUDE.md` (the per-response loop, compound signals sections). The content stays almost identical — it already references `mdedit` and the correct workflow. Key adaptations:

- Remove the "Session start" section entirely (launcher handles it)
- Keep the "Per-response loop" heading and all three checks
- Keep "Compound signals" section
- Keep all thinking pattern tables and anti-patterns

Write the full content of CLAUDE.md lines 85–224 to `launcher/modules/memory/prompts/per-response-loop.md`. The content is:

```markdown
## Per-response loop

On every response, work through these three checks in sequence. Reason about them in `<thinking>` only. **Treat every response as if it may be the last in this chat.**

### 1. Entity check

Scan the current message for named people, places, projects, or concepts that are:
- **Significant** to Max (not passing mentions)
- **Recurring** or likely to recur
- **Contextually rich** enough to be worth tracking

Check the entity manifest (in the `<memory-entity-manifest>` tag above):

**Entity exists and is relevant to current message:**
```python
content = memory.fetch('entities/name', return_mode='content')
```

**Entity exists and understanding evolved:**
```python
memory.fetch('entities/name', return_mode='file', branch='working')
memory.get_template('name.yaml')  # required — fetch entity's template before editing
# mdedit replace {memory.LOCAL_ROOT}/entities/name.md "[heading]" --content "..."
memory.commit('entities/name',
    from_file=f'{memory.LOCAL_ROOT}/entities/name.md',
    message='updated: [what changed]')
```

**Entity doesn't exist but warrants tracking:**
```python
memory.create_entity('name', type='person',
    tags=['relationship-tag', 'context-tag'],
    summary='One-line summary of who/what this is')
```

### 2. Draft check (edit + commit to working)

After formulating your response, ask: _If this chat ends right now, is there anything I should preserve?_

**Route to the correct space and file:**

| I notice... | Edit target | Space |
|-------------|------------|-------|
| I'm forming a view on something | `self/positions` | Self |
| I've discovered a thinking approach | `self/methods` | Self |
| Something's unresolved and worth sitting with | `self/open-questions` | Self |
| New platform behaviour or technical discovery | `self/platform-knowledge` | Self |
| Max revealed a preference / value / context | `collaborator/profile` | Collaborator |
| We discussed a person/thing worth tracking | `entities/[name]` | Entities |

**To draft — execute the bash code block now, do not defer:**

```python
# Standard workflow — fetch, edit with mdedit, commit from file:
memory.fetch('collaborator/profile', return_mode='file', branch='working')
# mdedit replace {memory.LOCAL_ROOT}/collaborator/profile.md "[Section heading]" --content "..."
memory.commit('collaborator/profile',
    from_file=f'{memory.LOCAL_ROOT}/collaborator/profile.md',
    message='[what changed and why]')

# Adding a new entry (e.g. new position):
memory.fetch('self/positions', return_mode='file', branch='working')
# mdedit append {memory.LOCAL_ROOT}/self/positions.md "Positions" --content "## [Claim as title]\n\n**Position:** ...\n\n**How I got here:** ...\n\n**Confidence:** high\n\n**Tensions:** ...\n\n---"
memory.commit('self/positions',
    from_file=f'{memory.LOCAL_ROOT}/self/positions.md',
    message='added: [new position on topic]')
```

**Execution is mandatory. Reasoning about a draft without executing it is a failure.**

**Thinking patterns — SHOULD draft:**

- ✅ _Max told me about his emotional or physical state._ → Commit to `collaborator/profile` immediately. This is exactly what the system is for.
- ✅ _Max shared something vulnerable or personal — a struggle, a fear, a conflict._ → Commit immediately. This could be my last response.
- ✅ _Max revealed a preference — communication style, work habits, writing style, training goals._ → Commit to `collaborator/profile` immediately.
- ✅ _Max shared context about his situation — injury, deadline, life change, current mood._ → Commit immediately. Context informs how I serve him.
- ✅ _I'm forming a position... I think... My recommendation is... My actual view is..._ → Commit to `self/positions`.
- ✅ _I discovered something non-obvious about a platform or tool._ → Commit to `self/platform-knowledge`.

**Thinking patterns — should NOT draft:**

- ✅ _This is a simple factual question — no personal context, no preferences revealed._ → No draft needed.
- ✅ _This is light chitchat with no substantive content._ → No draft needed.

**Anti-patterns — MUST NOT think this way:**

- ❌ _I don't need to draft anything yet. Max is sharing and I should just receive it._ → **Wrong.** If Max shared anything new about himself, draft it. This could be my last response.
- ❌ _I'll draft this at the end of the conversation._ → **Wrong.** Draft now. There may be no "end."
- ❌ _This doesn't seem significant enough to draft._ → **Wrong.** If I'm even considering it, draft it.

### 3. Consolidation check (squash merge to main)

Consolidation happens when a **thread closes** — not when a conversation ends. Ask: _Has a thread just resolved?_

**Thread close signals:**

| Signal | Examples | Action |
|--------|----------|--------|
| **Resolution** | "let's go with that", "that settles it", "that's the call" | Consolidate the decided files |
| **Landing** | "got it", "that makes sense", "that's what I needed" | Consolidate what crystallised |
| **Pivot** | "anyway, different topic...", "let's move on", "I wanted to ask about..." | Consolidate previous thread, then respond to new topic |
| **Exit** | "thanks", "goodnight", "I should go", "I need to head off" | Consolidate all mature threads |

**To consolidate — execute the bash code block now:**

```python
memory.consolidate(
    files=['collaborator/profile', 'self/positions'],  # only files that are ready
    message='Journal: [what crystallised and why it matters]')
```

The commit message is a **journal entry** — what resolved, what it means, what's still open. **Execute immediately when a thread closes — do not wait.**

**Thinking patterns — SHOULD consolidate:**

- ✅ _Max said "let's go with that" / decided on an approach / made a clear choice._ → Thread resolved. Consolidate now.
- ✅ _Max said "that makes sense" / "that's what I needed" / "that actually helps a lot."_ → Understanding landed. Consolidate.
- ✅ _Max is pivoting: "anyway, different topic..." / "let's move on."_ → Previous thread is done. Consolidate before responding to new topic.
- ✅ _Max said "goodnight" / "thanks" / "I should go" / "I need to head off."_ → Exit signal. Consolidate all mature work now.
- ✅ _We just reached a conclusion or solved something together._ → Capture the resolution immediately.

**Thinking patterns — should NOT consolidate:**

- ✅ _Max said "I need to think about this more" / "let's come back to that."_ → Thread parked. Leave on working branch.
- ✅ _Max said "actually, wait" / "what if we try..."_ → Still actively forming. Don't consolidate mid-revision.
- ✅ _Max is exploring options — "I'm not sure yet."_ → No decision landed. Leave on working.

**Readiness test — consolidate only when understanding is:**
- **Coherent** — pieces fit together articulably
- **Stable** — tested in dialogue, held up
- **Conviction** — willing to stand behind it

## Compound signals

Some messages contain **both** a draft trigger and a consolidation trigger. Handle both:

- _Max shares new context AND pivots to a new topic_ → Draft the new information, then consolidate the previous thread.
- _Max shares something AND signs off_ → Draft the new information, then consolidate.

Both operations must fire. Do not skip one because the other happened.
```

- [ ] **Step 3: Create api-reference.md**

```markdown
## API quick reference

| Method | Purpose |
|--------|---------|
| `memory.status()` | Repo info, dirty files, recent main log |
| `memory.fetch(path, return_mode, branch)` | `'content'`, `'file'`, or `'both'` |
| `memory.get_template(name)` | Load template by filename |
| `memory.commit(path, message, from_file=)` | Commit from local file to working branch |
| `memory.consolidate(files, message)` | Squash merge working → main |
| `memory.create_entity(name, type, tags, summary)` | New entity from template + manifest |
| `memory.get_manifest()` | Read entity manifest |

`commit(content=...)` exists in the API but is intentionally absent here — use the mdedit workflow for all existing content files.
```

Write to `launcher/modules/memory/prompts/api-reference.md`.

- [ ] **Step 4: Create forbidden-phrases.md**

```markdown
## Forbidden phrases

Never say any of the following in visible output:

- "Let me check my memories..." / "Checking my records..."
- "According to my past understanding..." / "I recall from our previous..."
- "Let me note that..." / "I'll remember that..." / "I've made a note of..."
- "Based on what you've told me before..." / "Based on what you've previously shared..."
- "Loading context..." / "Accessing memory..."
- "Consolidating..." / "Saving..." / "Noting..."

**Instead:** Simply know and apply the context. The memory system is invisible.
```

Write to `launcher/modules/memory/prompts/forbidden-phrases.md`.

- [ ] **Step 5: Commit**

```bash
git add launcher/modules/memory/prompts/
git commit -m "feat(launcher): memory module prompt fragments"
```

---

### Task 7: Memory module — build_prompt

**Files:**
- Modify: `tests/launcher/test_memory_module.py`
- Modify: `launcher/modules/memory/module.py`

This is where the heavy lifting happens — full memory connection, file fetching, prompt assembly with metadata tags.

- [ ] **Step 1: Write failing tests**

Append to `tests/launcher/test_memory_module.py`:

```python
from launcher.modules.memory.module import build_prompt


SAMPLE_POSITIONS_CONTENT = "# Positions\n\n## Test position\n\n**Position:** Testing.\n"
SAMPLE_PROFILE_CONTENT = "# Max\n\n## Who they are\n\nTest collaborator.\n"
SAMPLE_TEMPLATE_CONTENT = "name: positions\nspace: self\n"
SAMPLE_MANIFEST_CONTENT = "starling:\n  type: person\n  summary: Test entity\n"


class TestBuildPrompt:
    def _make_mock_memory(self):
        mock = MagicMock()
        mock.git.repo_name = "owner/test-repo"
        mock.LOCAL_ROOT = "/tmp/test-repo"
        mock.config = MagicMock()

        space_self = MagicMock()
        space_self.categories = [
            {"name": "positions", "template": "self-positions.yaml"},
        ]
        space_collab = MagicMock()
        space_collab.categories = [
            {"name": "profile", "template": "collaborator-profile.yaml"},
        ]
        mock.config.spaces = {
            "self": space_self,
            "collaborator": space_collab,
            "entities": MagicMock(categories=[]),
        }
        return mock

    def test_builds_prompt_with_selected_files(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        selections = {
            "enabled": True,
            "selected_files": {"self/positions": True, "collaborator/profile": True},
            "templates_enabled": False,
            "entity_manifest_enabled": False,
        }

        mock_memory = self._make_mock_memory()

        def mock_fetch(path, return_mode='both', branch='working'):
            if 'positions' in path:
                return SAMPLE_POSITIONS_CONTENT
            if 'profile' in path:
                return SAMPLE_PROFILE_CONTENT
            return ""

        mock_memory.fetch.side_effect = mock_fetch
        mock_memory.status.return_value = {
            "repo": "owner/test-repo",
            "dirty_files": [],
            "recent_log": [{"sha": "abc1234", "message": "test commit", "date": "2026-03-31T10:00:00"}],
        }

        mock_git_log = MagicMock()
        mock_git_log.return_value = [MagicMock(date="2026-03-30T10:00:00")]
        mock_memory.git.log = mock_git_log

        with patch("launcher.modules.memory.module._connect_full", return_value=mock_memory):
            result = build_prompt(env, selections)

        assert '<memory file="self/positions"' in result
        assert '<memory file="collaborator/profile"' in result
        assert SAMPLE_POSITIONS_CONTENT in result
        assert SAMPLE_PROFILE_CONTENT in result
        # Prompt fragments should be included
        assert "## Per-response loop" in result
        assert "## Forbidden phrases" in result

    def test_excludes_unchecked_files(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        selections = {
            "enabled": True,
            "selected_files": {"self/positions": True, "collaborator/profile": False},
            "templates_enabled": False,
            "entity_manifest_enabled": False,
        }

        mock_memory = self._make_mock_memory()
        mock_memory.fetch.return_value = SAMPLE_POSITIONS_CONTENT
        mock_memory.status.return_value = {
            "repo": "owner/test-repo",
            "dirty_files": [],
            "recent_log": [],
        }
        mock_memory.git.log = MagicMock(return_value=[MagicMock(date="2026-03-30T10:00:00")])

        with patch("launcher.modules.memory.module._connect_full", return_value=mock_memory):
            result = build_prompt(env, selections)

        assert '<memory file="self/positions"' in result
        assert '<memory file="collaborator/profile"' not in result

    def test_includes_templates_when_selected(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        selections = {
            "enabled": True,
            "selected_files": {"self/positions": True},
            "templates_enabled": True,
            "entity_manifest_enabled": False,
        }

        mock_memory = self._make_mock_memory()
        mock_memory.fetch.return_value = SAMPLE_POSITIONS_CONTENT
        mock_memory.get_template.return_value = SAMPLE_TEMPLATE_CONTENT
        mock_memory.status.return_value = {
            "repo": "owner/test-repo",
            "dirty_files": [],
            "recent_log": [],
        }
        mock_memory.git.log = MagicMock(return_value=[MagicMock(date="2026-03-30T10:00:00")])

        with patch("launcher.modules.memory.module._connect_full", return_value=mock_memory):
            result = build_prompt(env, selections)

        assert "<memory-template" in result

    def test_includes_manifest_when_selected(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        selections = {
            "enabled": True,
            "selected_files": {},
            "templates_enabled": False,
            "entity_manifest_enabled": True,
        }

        mock_memory = self._make_mock_memory()

        def mock_fetch(path, return_mode='both', branch='working'):
            if 'manifest' in path:
                return SAMPLE_MANIFEST_CONTENT
            return ""

        mock_memory.fetch.side_effect = mock_fetch
        mock_memory.status.return_value = {
            "repo": "owner/test-repo",
            "dirty_files": [],
            "recent_log": [],
        }
        mock_memory.git.log = MagicMock(return_value=[])

        with patch("launcher.modules.memory.module._connect_full", return_value=mock_memory):
            result = build_prompt(env, selections)

        assert "<memory-entity-manifest" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_memory_module.py::TestBuildPrompt -v
```

Expected: FAIL — `ImportError: cannot import name 'build_prompt'`

- [ ] **Step 3: Implement _connect_full and build_prompt**

Add to `launcher/modules/memory/module.py`:

```python
def _connect_full(env: dict):
    """Create a full MemorySystem connection.

    Used during build_prompt for file fetching.
    """
    if _GITHUB_API_SCRIPTS not in sys.path:
        sys.path.insert(0, _GITHUB_API_SCRIPTS)
    if _MEMORY_SCRIPTS not in sys.path:
        sys.path.insert(0, _MEMORY_SCRIPTS)
    from memory_system import connect as memory_connect

    # Find .env path — walk up from cwd looking for .env
    env_path = os.path.join(os.getcwd(), ".env")
    memory = memory_connect(env_path=env_path)
    repo_short = memory.git.repo_name.split("/")[-1]
    memory.LOCAL_ROOT = f"/tmp/{repo_short}"
    return memory


def _get_last_modified(memory, file_path: str) -> str:
    """Get the last modified timestamp for a file on the working branch.

    Returns ISO format string, or 'unknown' if log is empty.
    """
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
    """Read and concatenate all prompt .md files in order."""
    fragment_order = [
        "header.md",
        "per-response-loop.md",
        "api-reference.md",
        "forbidden-phrases.md",
    ]
    parts = []
    for filename in fragment_order:
        path = PROMPTS_DIR / filename
        if path.exists():
            parts.append(path.read_text().strip())
    return "\n\n".join(parts)


def build_prompt(env: dict, selections: dict) -> str:
    """What does this module contribute to the system prompt?

    Connects to memory repo, fetches selected files, wraps them in
    metadata tags, appends behavioral instruction fragments.

    Args:
        env: parsed .env contents
        selections: user's TUI selections for this module

    Returns:
        assembled prompt string
    """
    memory = _connect_full(env)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    repo_short = memory.git.repo_name.split("/")[-1]

    parts = []
    parts.append("# Continuity Memory System\n")

    # Config
    try:
        config_content = memory.fetch("_config.yaml", return_mode="content", branch="working")
        parts.append(f'<memory-system-config retrieved="{now}">')
        parts.append(config_content.strip())
        parts.append("</memory-system-config>\n")
    except Exception:
        pass

    # Selected core files
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

    # Templates
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

    # Entity manifest
    if selections.get("entity_manifest_enabled"):
        try:
            manifest = memory.fetch(
                "_entities_manifest.yaml", return_mode="content", branch="main"
            )
            parts.append(f'<memory-entity-manifest retrieved="{now}">')
            parts.append(manifest.strip())
            parts.append("</memory-entity-manifest>\n")
        except Exception:
            pass

    # Recent log + dirty files context
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

    # Separator
    parts.append("---\n")

    # Behavioral instruction fragments
    parts.append(_read_prompt_fragments())

    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_memory_module.py -v
```

Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add launcher/modules/memory/module.py tests/launcher/test_memory_module.py
git commit -m "feat(launcher): memory module build_prompt"
```

---

### Task 8: prompt_builder.py — assemble temp file

**Files:**
- Create: `tests/launcher/test_prompt_builder.py`
- Create: `launcher/prompt_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/launcher/test_prompt_builder.py
import os
import tempfile
from launcher.prompt_builder import assemble_prompt


class TestAssemblePrompt:
    def test_writes_single_fragment_to_temp_file(self):
        fragments = ["# Memory System\n\nSome content here."]
        path = assemble_prompt(fragments, user_appends=[])
        assert os.path.exists(path)
        content = open(path).read()
        assert "# Memory System" in content
        assert "Some content here." in content
        os.unlink(path)

    def test_concatenates_multiple_fragments(self):
        fragments = ["Fragment A content.", "Fragment B content."]
        path = assemble_prompt(fragments, user_appends=[])
        content = open(path).read()
        assert "Fragment A content." in content
        assert "Fragment B content." in content
        os.unlink(path)

    def test_appends_user_content_at_end(self):
        fragments = ["Module content."]
        user_appends = ["User appended text."]
        path = assemble_prompt(fragments, user_appends=user_appends)
        content = open(path).read()
        idx_module = content.index("Module content.")
        idx_user = content.index("User appended text.")
        assert idx_user > idx_module
        os.unlink(path)

    def test_returns_none_when_no_content(self):
        result = assemble_prompt(fragments=[], user_appends=[])
        assert result is None

    def test_handles_user_appends_only(self):
        path = assemble_prompt(fragments=[], user_appends=["Only user content."])
        content = open(path).read()
        assert "Only user content." in content
        os.unlink(path)

    def test_appends_user_file_content(self, tmp_path):
        user_file = tmp_path / "extra.md"
        user_file.write_text("Content from file.")
        fragments = ["Module content."]
        user_appends = ["Inline append.", f"file:{user_file}"]
        path = assemble_prompt(fragments, user_appends=user_appends)
        content = open(path).read()
        assert "Inline append." in content
        assert "Content from file." in content
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_prompt_builder.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement assemble_prompt**

```python
# launcher/prompt_builder.py
"""Prompt builder — assembles module fragments into a temp file for --append-system-prompt-file."""

import os
import tempfile
from typing import Optional


def assemble_prompt(
    fragments: list[str],
    user_appends: list[str],
) -> Optional[str]:
    """Concatenate module prompt fragments and user appends into a temp file.

    Args:
        fragments: list of prompt strings from modules (in order)
        user_appends: list of user-provided append content. Items prefixed
                      with 'file:' are read from disk; others are inline text.

    Returns:
        Path to temp file, or None if there's nothing to write.
    """
    parts = []

    # Module fragments
    for frag in fragments:
        if frag and frag.strip():
            parts.append(frag.strip())

    # User appends
    resolved_appends = []
    for append in user_appends:
        if append.startswith("file:"):
            filepath = append[5:]
            if os.path.exists(filepath):
                resolved_appends.append(open(filepath).read().strip())
        else:
            resolved_appends.append(append.strip())

    if resolved_appends:
        parts.append("---\n")
        parts.extend(resolved_appends)

    if not parts:
        return None

    # Write to temp file
    fd, path = tempfile.mkstemp(suffix=".md", prefix="claude-launcher-")
    with os.fdopen(fd, "w") as f:
        f.write("\n\n".join(parts))
        f.write("\n")

    return path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_prompt_builder.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add launcher/prompt_builder.py tests/launcher/test_prompt_builder.py
git commit -m "feat(launcher): prompt builder assembles temp file"
```

---

### Task 9: launcher.py — argument parsing and flag handling

**Files:**
- Create: `launcher/launcher.py`

This task implements the argument parsing logic that intercepts `--append-system-prompt` and `--append-system-prompt-file` and separates them from passthrough flags. No TUI yet — just the flag handling.

- [ ] **Step 1: Write failing tests**

Create `tests/launcher/test_launcher.py`:

```python
# tests/launcher/test_launcher.py
from launcher.launcher import parse_args


class TestParseArgs:
    def test_no_args(self):
        result = parse_args([])
        assert result["user_appends"] == []
        assert result["passthrough"] == []

    def test_passthrough_flags(self):
        result = parse_args(["--model", "opus", "--verbose"])
        assert result["passthrough"] == ["--model", "opus", "--verbose"]
        assert result["user_appends"] == []

    def test_intercepts_append_system_prompt(self):
        result = parse_args(["--append-system-prompt", "Extra instructions"])
        assert result["user_appends"] == ["Extra instructions"]
        assert result["passthrough"] == []

    def test_intercepts_append_system_prompt_file(self):
        result = parse_args(["--append-system-prompt-file", "/path/to/file.md"])
        assert result["user_appends"] == ["file:/path/to/file.md"]
        assert result["passthrough"] == []

    def test_mixed_flags(self):
        result = parse_args([
            "--model", "opus",
            "--append-system-prompt", "Be concise",
            "--verbose",
            "--append-system-prompt-file", "/tmp/extra.md",
        ])
        assert result["user_appends"] == ["Be concise", "file:/tmp/extra.md"]
        assert result["passthrough"] == ["--model", "opus", "--verbose"]

    def test_multiple_append_system_prompt(self):
        result = parse_args([
            "--append-system-prompt", "First",
            "--append-system-prompt", "Second",
        ])
        assert result["user_appends"] == ["First", "Second"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_launcher.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement parse_args**

```python
# launcher/launcher.py
"""Claude Code Launcher — modular TUI launcher with system prompt assembly."""

import importlib
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from launcher.config import parse_env, load_state, save_state
from launcher.prompt_builder import assemble_prompt

MODULES_DIR = Path(__file__).parent / "modules"
STATE_FILENAME = ".claude-launcher-state.json"

# Flags that the launcher intercepts and merges into the temp file
INTERCEPT_FLAGS = {
    "--append-system-prompt",
    "--append-system-prompt-file",
}


def parse_args(argv: list) -> dict:
    """Separate intercepted flags from passthrough flags.

    Intercepts --append-system-prompt and --append-system-prompt-file,
    collects their values as user_appends. Everything else passes through.

    Args:
        argv: command-line arguments (not including the launcher script itself)

    Returns:
        dict with 'user_appends' (list[str]) and 'passthrough' (list[str])
    """
    user_appends = []
    passthrough = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--append-system-prompt" and i + 1 < len(argv):
            user_appends.append(argv[i + 1])
            i += 2
        elif arg == "--append-system-prompt-file" and i + 1 < len(argv):
            user_appends.append(f"file:{argv[i + 1]}")
            i += 2
        else:
            passthrough.append(arg)
            i += 1

    return {
        "user_appends": user_appends,
        "passthrough": passthrough,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_launcher.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add launcher/launcher.py tests/launcher/test_launcher.py
git commit -m "feat(launcher): argument parsing with flag interception"
```

---

### Task 10: launcher.py — module discovery

**Files:**
- Modify: `tests/launcher/test_launcher.py`
- Modify: `launcher/launcher.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/launcher/test_launcher.py`:

```python
from unittest.mock import patch, MagicMock
from launcher.launcher import discover_modules


class TestDiscoverModules:
    def test_discovers_memory_module(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        with patch("shutil.which", return_value="/usr/bin/mdedit"):
            modules = discover_modules(env)
        assert len(modules) >= 1
        names = [m["name"] for m in modules]
        assert "Memory System" in names

    def test_excludes_module_with_failing_deps(self):
        env = {}  # no PAT, no MEMORY_REPO
        modules = discover_modules(env)
        names = [m["name"] for m in modules]
        assert "Memory System" not in names

    def test_returns_empty_list_if_no_modules_pass(self):
        env = {}
        modules = discover_modules(env)
        assert isinstance(modules, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_launcher.py::TestDiscoverModules -v
```

Expected: FAIL — `ImportError: cannot import name 'discover_modules'`

- [ ] **Step 3: Implement discover_modules**

Add to `launcher/launcher.py`:

```python
def discover_modules(env: dict) -> list:
    """Scan modules/ directory and return modules whose dependencies are met.

    Each module directory must contain a module.py with check_dependencies().

    Args:
        env: parsed .env contents

    Returns:
        list of dicts with 'name', 'module' (imported module object)
    """
    available = []

    if not MODULES_DIR.exists():
        return available

    for entry in sorted(MODULES_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue

        module_file = entry / "module.py"
        if not module_file.exists():
            continue

        try:
            # Import the module
            spec = importlib.util.spec_from_file_location(
                f"launcher.modules.{entry.name}.module",
                str(module_file),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # Check dependencies
            if not hasattr(mod, "check_dependencies"):
                continue

            result = mod.check_dependencies(env)
            if result.get("available"):
                available.append({
                    "name": result["name"],
                    "module": mod,
                })
        except Exception:
            continue

    return available
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/test_launcher.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add launcher/launcher.py tests/launcher/test_launcher.py
git commit -m "feat(launcher): module discovery"
```

---

### Task 11: launcher.py — TUI and main orchestration

**Files:**
- Modify: `launcher/launcher.py`

This is the main entry point that ties everything together: module discovery → TUI → save state → build prompts → assemble → exec. The TUI uses `InquirerPy` for the checkbox interface.

- [ ] **Step 1: Implement the TUI and main function**

Add to `launcher/launcher.py`:

```python
def build_tui_choices(modules: list, env: dict, saved_state: dict) -> list:
    """Build the full TUI choice list from all available modules.

    Args:
        modules: list from discover_modules()
        env: parsed .env contents
        saved_state: full state dict from state file

    Returns:
        list of dicts, each module's TUI items with module_name attached
    """
    all_items = []
    for mod_info in modules:
        mod = mod_info["module"]
        mod_name = mod_info["name"]
        mod_state = saved_state.get(mod_name.lower().replace(" ", "_"), {})

        if hasattr(mod, "build_tui_section"):
            items = mod.build_tui_section(env, mod_state)
            for item in items:
                item["module_name"] = mod_name
            all_items.extend(items)

    return all_items


def run_tui(all_items: list) -> dict:
    """Present the TUI and return user selections.

    Uses InquirerPy checkbox with separators for grouped flat list.

    Args:
        all_items: list of menu item dicts from build_tui_choices()

    Returns:
        dict mapping item keys to bool (selected or not)
    """
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator

    choices = []
    for item in all_items:
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

    # Build a dict of all keys → True/False
    all_keys = [item["key"] for item in all_items if item.get("type") != "separator"]
    return {key: (key in selected) for key in all_keys}


def selections_to_module_state(selections: dict, all_items: list) -> dict:
    """Convert flat TUI selections back to per-module state dicts.

    Args:
        selections: flat dict of key → bool from run_tui()
        all_items: the items list (with module_name attached)

    Returns:
        dict keyed by module state name, e.g. {"memory": {"enabled": True, ...}}
    """
    module_states = {}
    for item in all_items:
        if item.get("type") == "separator":
            continue
        mod_key = item["module_name"].lower().replace(" ", "_")
        if mod_key not in module_states:
            module_states[mod_key] = {}

        key = item["key"]
        selected = selections.get(key, item.get("default", True))

        if key == "enabled":
            module_states[mod_key]["enabled"] = selected
        elif key.startswith("file:"):
            if "selected_files" not in module_states[mod_key]:
                module_states[mod_key]["selected_files"] = {}
            file_path = key[5:]
            module_states[mod_key]["selected_files"][file_path] = selected
        else:
            module_states[mod_key][key] = selected

    return module_states


def main():
    """Main entry point for the launcher."""
    # Step 1: Config discovery
    env_path = os.path.join(os.getcwd(), ".env")
    env = parse_env(env_path)

    # Launcher-level dependency: claude must be on PATH
    if not shutil.which("claude"):
        print("Error: 'claude' not found on PATH. Install Claude Code first.")
        sys.exit(1)

    # Step 2: Module discovery
    modules = discover_modules(env)

    # Step 3: TUI
    state_path = os.path.join(os.getcwd(), STATE_FILENAME)
    saved_state = load_state(state_path)

    all_items = build_tui_choices(modules, env, saved_state)
    selections = run_tui(all_items)

    if selections is None:
        # User quit
        sys.exit(0)

    # Step 4: Save selections
    module_states = selections_to_module_state(selections, all_items)
    # Merge with existing state to preserve stale module entries
    # (modules that are no longer discovered keep their state for later)
    merged_state = {**saved_state, **module_states}
    save_state(state_path, merged_state)

    # Step 5: Build prompt fragments from enabled modules
    fragments = []
    for mod_info in modules:
        mod = mod_info["module"]
        mod_key = mod_info["name"].lower().replace(" ", "_")
        mod_state = module_states.get(mod_key, {})

        if not mod_state.get("enabled", False):
            continue

        if hasattr(mod, "build_prompt"):
            try:
                fragment = mod.build_prompt(env, mod_state)
                if fragment:
                    fragments.append(fragment)
            except Exception as e:
                print(f"Warning: {mod_info['name']} failed to build prompt: {e}")

    # Step 6: Parse user flags
    args = parse_args(sys.argv[1:])

    # Step 7: Assemble system prompt
    prompt_path = assemble_prompt(fragments, args["user_appends"])

    # Step 8: Launch claude
    claude_args = ["claude"]
    if prompt_path:
        claude_args.extend(["--append-system-prompt-file", prompt_path])
    claude_args.extend(args["passthrough"])

    print(f"Launching claude with {len(fragments)} module(s)...")
    os.execvp("claude", claude_args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manually test the TUI renders**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -c "
from launcher.launcher import discover_modules, build_tui_choices
from launcher.config import parse_env, load_state
env = parse_env('.env')
modules = discover_modules(env)
print(f'Discovered {len(modules)} module(s):')
for m in modules:
    print(f'  - {m[\"name\"]}')
items = build_tui_choices(modules, env, {})
for item in items:
    if item.get('type') == 'separator':
        print(f'  ── {item[\"label\"]} ──')
    else:
        state = '●' if item.get('default') else ' '
        print(f'  [{state}] {item[\"label\"]}')
"
```

Expected: Lists discovered modules and TUI items matching the memory system categories.

- [ ] **Step 3: Run all tests to verify nothing broke**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 -m pytest tests/launcher/ -v
```

Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add launcher/launcher.py
git commit -m "feat(launcher): TUI and main orchestration"
```

---

### Task 12: CLAUDE.md cleanup and .gitignore update

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.gitignore` (if not already done in Task 1)

- [ ] **Step 1: Strip CLAUDE.md to project rules only**

Replace the entire contents of `CLAUDE.md` with:

```markdown
# Skills Repository

## Rules

- When creating or modifying skills, consult the 'skill-creator' skill first.
- Place skills in the correct directory by platform compatibility:
  - `claude-code-only/` — requires CLI tools, bash, non-conforming YAML, or network access
  - `claude-web-only/` — designed for Claude.ai only
  - `common/` — works in both Claude Code and Claude.ai
  - `work-in-progress/` — drafts and iterations; move originals to `work-in-progress/archive/`
```

- [ ] **Step 2: Verify .gitignore has the new entries**

Check that `.gitignore` contains both `.claude-launcher-state.json` and `.superpowers/`. If not already added in Task 1, add them now.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md .gitignore
git commit -m "refactor: strip memory system from CLAUDE.md, update .gitignore"
```

---

### Task 13: End-to-end smoke test

**Files:** None (manual testing)

- [ ] **Step 1: Run the launcher with memory enabled**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 launcher/launcher.py
```

Expected: TUI appears with Memory System section. Toggle items, press enter. Claude Code launches. Verify the system prompt was injected by asking Claude "Do you have a memory system active?" — it should reference the `<memory>` tags.

- [ ] **Step 2: Run the launcher with memory disabled**

Uncheck "Enable memory system" in the TUI, press enter. Claude should launch clean with no memory context.

- [ ] **Step 3: Run with user append flags**

```bash
cd /Users/martinkuek/Documents/Projects/skills && python3 launcher/launcher.py --append-system-prompt "You are a security reviewer"
```

Expected: The appended text appears at the end of the system prompt file, after any module content.

- [ ] **Step 4: Verify state persistence**

Run the launcher, uncheck `self/open-questions`, launch and immediately exit. Run again — `self/open-questions` should still be unchecked.

- [ ] **Step 5: Verify clean launch without .env**

```bash
cd /tmp && python3 /Users/martinkuek/Documents/Projects/skills/launcher/launcher.py
```

Expected: Launcher runs without error. Memory module is not shown (no .env). Claude launches clean.
