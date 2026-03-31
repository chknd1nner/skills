# Claude Code Launcher

*Design spec — 2026-03-31*

## Problem

The continuity-memory system activates differently across platforms. On Claude.ai, core memory files and templates are pre-injected into the system prompt via GitHub integration — they persist through context compression and have first-class status. In Claude Code, the same content is retrieved via tool calls during the session, making it vulnerable to context compression and giving it lower priority than system prompt content.

Additionally, the current CLAUDE.md carries a large block of session-start Python code and behavioral instructions that dominate the file. The session-start code must execute on every first message, consuming tokens and adding latency. The behavioral instructions are interleaved with data-loading logic, making them hard to maintain.

## Solution

A modular Python launcher that runs before Claude Code starts. It discovers available modules (the memory system being the first), presents a TUI menu composed from modules whose dependencies are satisfied, assembles a system prompt file from module contributions, and launches `claude` with `--append-system-prompt-file`. This gives memory content the same system-prompt-level persistence it has on Claude.ai, eliminates the session-start code block entirely, and separates the memory system from CLAUDE.md.

The launcher is designed to be extensible — future modules can be added by dropping a Python file into the `modules/` directory. Each module is self-contained: it declares its own dependencies, contributes its own TUI section, and builds its own system prompt fragment. The launcher orchestrates without knowing what any module does.

## Directory Structure

```
launcher/
├── launcher.py                    # Entry point: TUI, orchestration, exec claude
├── config.py                      # .env discovery, saved selections state
├── prompt_builder.py              # Assembles system prompt from module contributions
└── modules/
    └── memory/
        ├── module.py              # Module interface: check_dependencies, build_tui, build_prompt
        └── prompts/
            ├── header.md          # System identity, model-is-the-user framing, mdedit dependency
            ├── per-response-loop.md  # Entity check, draft check, consolidation check
            ├── api-reference.md   # Memory API quick reference
            └── forbidden-phrases.md  # Things never to say in visible output
```

Each module lives in its own subdirectory under `modules/`. A module contains a `module.py` implementing the standard interface, plus whatever resources it needs (prompt fragments, templates, etc.). The launcher scans `modules/`, imports each `module.py`, and asks it whether it can run.

## Module Interface

Every module implements three functions:

```python
def check_dependencies(env: dict) -> dict:
    """Can this module run at all? Lightweight checks only.

    Validates that required credentials, tools, and prerequisites exist.
    No heavy fetching — just presence checks.

    For the memory module: PAT and MEMORY_REPO in env, mdedit on PATH.

    Args:
        env: parsed .env contents (may be empty)

    Returns:
        {
            'available': bool,       # can this module run?
            'name': str,             # display name for TUI
            'reason': str | None,    # why not, if unavailable
        }
    """

def build_tui_section(env: dict, saved_state: dict) -> list:
    """What should this module show in the TUI?

    Called only if check_dependencies passed. This is where the module
    does any lightweight fetching needed to populate its menu items.

    For the memory module: fetches _config.yaml from the memory repo
    (using credentials from env) to discover category names, then
    renders a toggle per category. Falls back to cached categories
    from saved_state if the fetch fails.

    Args:
        env: parsed .env contents
        saved_state: previous selections from state file for this module

    Returns:
        list of toggleable menu items with labels and default states
    """

def build_prompt(env: dict, selections: dict) -> str:
    """What does this module contribute to the system prompt?

    Called only after the user confirms selections. This is where the
    heavy work happens — full API connections, file content fetches,
    prompt fragment assembly.

    For the memory module: connects to the memory repo, fetches selected
    core files and extras, reads prompts/*.md fragments, and assembles
    the complete system prompt fragment with metadata tags.

    Args:
        env: parsed .env contents
        selections: the user's TUI selections for this module

    Returns:
        assembled prompt string (content + behavioral instructions)
    """
```

The three functions have clean, escalating responsibilities: "can I run?" → "what do I show?" → "what do I contribute?" Each stage only does the work appropriate to its purpose. The launcher doesn't know what a "memory system" is — it calls these functions on each discovered module and orchestrates the results. Future modules implement the same interface and get picked up automatically.

## Launch Sequence

1. **Config discovery** — look for `.env` in the current working directory. Parse key-value pairs if present. No error if missing.

2. **Module discovery** — scan `modules/` directory, import each `module.py`, call `check_dependencies(env)` on each. Lightweight checks only: the memory module verifies `PAT` and `MEMORY_REPO` exist in env and `mdedit` is on PATH. No API calls at this stage. Modules that pass get included in the TUI. Modules that fail are silently excluded.

3. **TUI menu** — load last selections from `.claude-launcher-state.json`. Call `build_tui_section(env, saved_state)` on each available module to compose the menu. This is where modules do any lightweight fetching needed for their menu items (the memory module fetches `_config.yaml` to discover category names, falling back to cached state). Each module contributes its own section with separator grouping. `claude` on PATH is checked as a launcher-level dependency (not module-level) since nothing works without it.

4. **User presses enter to launch.**

5. **Save selections** — write current choices to `.claude-launcher-state.json` in the project root.

6. **Build prompt fragments** — call `build_prompt(selections)` on each enabled module. This is where the memory module does its full connection, fetches selected files, and assembles its prompt fragment (content in metadata tags + behavioral instructions from `prompts/`).

7. **Assemble system prompt** — `prompt_builder.py` concatenates all module prompt fragments and writes to a temp file.

8. **Merge user flags** — if the user passed `--append-system-prompt-file` or `--append-system-prompt` as extra arguments to the launcher, append that content to the end of the temp file. This prevents duplicate-flag conflicts with `claude`.

9. **Launch** — `os.execvp("claude", ["claude", "--append-system-prompt-file", tempfile, ...remaining_flags])`. If no modules are enabled and no user appends exist, launch `claude` clean with just the passthrough flags.

## TUI Design

Flat list with visual grouping via separator lines. Arrow keys to navigate, space to toggle, enter to launch, q to quit.

```
Memory System
[●] Enable memory system
────────────────────────
Core Files
❯ [●] self/positions
  [●] self/methods
  [●] self/platform-knowledge
  [ ] self/open-questions
  [●] collaborator/profile
────────────────────────
Extras
  [●] Templates
  [●] Entity manifest
────────────────────────
↑↓ navigate  ␣ toggle  ⏎ launch  q quit
```

The TUI is composed from module contributions. The memory module generates its section from `_config.yaml` — adding a new category to the config makes it appear in the launcher automatically. When a module's master toggle is off, its sub-items are visually dimmed or hidden. Future modules contribute their own sections in the same flat-list style.

Selections persist between launches via `.claude-launcher-state.json`. On first run (no state file), everything defaults to enabled.

## System Prompt File Format

The assembled temp file follows this structure:

```markdown
# Continuity Memory System

<memory-system-config retrieved="2026-03-31T14:23:00Z">
[contents of _config.yaml]
</memory-system-config>

<memory file="self/positions" branch="working" last_modified="2026-03-29T09:56:53Z">
[file contents]
</memory>

<memory file="collaborator/profile" branch="working" last_modified="2026-03-30T22:15:00Z">
[file contents]
</memory>

<memory-template name="self-positions.yaml">
[template contents]
</memory-template>

<memory-entity-manifest retrieved="2026-03-31T14:23:00Z">
[manifest contents]
</memory-entity-manifest>

---

[contents of prompts/header.md]

[contents of prompts/per-response-loop.md]

[contents of prompts/api-reference.md]

[contents of prompts/forbidden-phrases.md]

---

[any user-appended content from --append-system-prompt or --append-system-prompt-file]
```

Content first (what to know), then behavioral instructions (how to act), then user appends. Each memory file is wrapped in semantic tags with metadata: the branch it was fetched from and the last-modified timestamp. This gives the model freshness signals that Claude.ai's pre-injection doesn't provide.

Only selected files appear in the output. If the user unchecked `self/open-questions` in the TUI, it's absent from the file entirely.

## Memory Module Prompt Fragments

The memory module's `prompts/` directory contains the behavioral instructions as standalone markdown files, lifted from the current CLAUDE.md and adapted for Claude Code:

**`header.md`** — establishes that a memory system is active, frames the "model is the user" principle, notes that `mdedit` is the editing tool for memory files, and sets the local root path (`/tmp/{repo}`).

**`per-response-loop.md`** — the three sequential checks the model runs on every response (entity check, draft check, consolidation check). Includes the routing table (what to edit based on what was noticed), the "should draft" / "should not draft" thinking patterns, thread-close signals for consolidation, compound signal handling, and the readiness test for consolidation. This is the largest fragment — lifted mostly as-is from the current CLAUDE.md.

**`api-reference.md`** — quick-reference table of memory system methods with signatures: `memory.status()`, `memory.fetch()`, `memory.commit()`, `memory.consolidate()`, `memory.create_entity()`, `memory.get_manifest()`, `memory.get_template()`.

**`forbidden-phrases.md`** — the list of phrases the model must never say in visible output ("Let me check my memories...", "I'll remember that...", etc.) and the instruction to simply know and apply context seamlessly.

These files are owned by the memory module, not the launcher. Other future modules would have their own `prompts/` directories with their own fragments.

## Flag Handling

The launcher intercepts and merges append-related flags to avoid conflicts:

- `--append-system-prompt "text"` — the inline text is appended to the end of the temp file.
- `--append-system-prompt-file /path/to/file` — the file's contents are appended to the end of the temp file.

All other flags pass through to `claude` untouched. The launcher itself consumes no flags — everything after the launcher command is either intercepted (append flags) or passed through.

If no modules are enabled and the user passed append flags, the launcher still builds a temp file containing just the user's appended content and passes it via `--append-system-prompt-file`.

If no modules are enabled and no append flags were passed, `claude` is launched with no `--append-system-prompt-file` at all — equivalent to running `claude` directly.

## CLAUDE.md Changes

The entire memory system block is removed from CLAUDE.md. What remains is only the project-specific rules:

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

The session-start Python code block is eliminated entirely — the launcher handles it. The per-response loop, API reference, and forbidden phrases move to `launcher/prompts/`. CLAUDE.md returns to being purely about the project.

## Saved State

`.claude-launcher-state.json` lives in the project root and is gitignored. State is namespaced by module:

```json
{
  "memory": {
    "enabled": true,
    "selected_files": {
      "self/positions": true,
      "self/methods": true,
      "self/platform-knowledge": true,
      "self/open-questions": false,
      "collaborator/profile": true
    },
    "templates_enabled": true,
    "entity_manifest_enabled": true
  }
}
```

Each module owns its own key in the state file. On first run with no state file, all options default to enabled. If a module's config has changed since last run (new categories added, old ones removed), new entries default to enabled and removed entries are cleaned from that module's state. Modules that are no longer discovered are left in the state file (not deleted) in case they become available again later.

## Dependencies

**Launcher-level (always checked):**
- `claude` — Claude Code CLI, must be on PATH

**Module-level (checked by each module during discovery):**
- Memory module: `mdedit` on PATH, `PAT` and `MEMORY_REPO` in `.env`, reachable memory repo

**Python dependencies:**
- `questionary` or `InquirerPy` — TUI checkbox/toggle menu
- `memory_system.py` + `git_operations.py` — existing memory system code (imported by memory module)
- `PyGithub` — already a dependency of the memory system

**Future:** `mdedit` will become auto-installable (via npm or cargo). For now, the memory module silently excludes itself from the TUI if `mdedit` is not found.

## Out of Scope

- **Hooks for behavioral nudges** — deferred to a future design. Will affect the memory module's prompt fragments when designed.
- **Auto-install of mdedit** — requires mdedit to be published to a package registry first.
- **Non-interactive mode** — if you want a bare claude session, run `claude` directly.
- **Multiple memory repo support** — single repo per project via `.env`.
- **Additional modules** — only the memory module ships in v1. The module interface is designed for extensibility but no other modules are in scope.
