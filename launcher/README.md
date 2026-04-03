# Claude Code Launcher

A modular TUI launcher for Claude Code that injects system prompt content before launch.

## Quick Start

```bash
cd /path/to/your/project   # must contain .env with PAT and MEMORY_REPO
python3 launcher/launcher.py
```

The launcher presents a checkbox menu. Use arrow keys to navigate, space to toggle, enter to launch.

```
? Configure launch options:
  [●] Enable memory system
  ── Core Files ──
  [●] self/positions
  [●] self/methods
  [●] self/platform-knowledge
  [ ] self/open-questions
  [●] collaborator/profile
  ── Extras ──
  [●] Templates
  [●] Entity manifest
```

Your selections persist between launches in `.claude-launcher-state.json`.

## Passing Flags to Claude

Everything after `launcher.py` passes through to `claude`:

```bash
python3 launcher/launcher.py --model opus --verbose
```

The launcher intercepts `--append-system-prompt` and `--append-system-prompt-file` and merges them into its assembled prompt file, so there's no flag collision:

```bash
python3 launcher/launcher.py --append-system-prompt "You are a security reviewer"
```

## Without Memory System

If `.env` is missing or doesn't have `PAT`/`MEMORY_REPO`, the memory module simply won't appear in the TUI. You can still launch claude through the launcher (useful for future modules).

If no modules are enabled and no append flags are passed, claude launches clean — equivalent to running `claude` directly.

## Requirements

- `claude` on PATH (Claude Code CLI)
- `mdedit` on PATH (for memory module — checked during module discovery)
- `InquirerPy` Python package (`pip3 install InquirerPy`)
- `.env` in project root with `PAT` and `MEMORY_REPO` (for memory module)

## Adding Modules

Drop a directory into `launcher/modules/` with a `module.py` implementing:

```python
def check_dependencies(env: dict) -> dict:
    """Return {'available': bool, 'name': str, 'reason': str|None}"""

def build_tui_section(env: dict, saved_state: dict) -> list:
    """Return list of menu items for the TUI"""

def build_prompt(env: dict, selections: dict) -> str:
    """Return the system prompt fragment for this module"""
```

The launcher discovers it automatically on next run.
