# Continuity-Memory CC: mdedit Editing Layer

*2026-03-28*

## Problem

During active development sessions, the Claude Code model repeatedly overwrote memory files
(`collaborator/profile.md`, `self/positions.md`, etc.) with entirely new content in divergent
formats, discarding the original template structure. A Gemini spec review identified the root
cause: `CLAUDE.md` presents `memory.commit(content=...)` as the "simplest path" for drafting,
the surgical editing methods (`replace_section`, `add_entry`, `remove_section`) are absent from
its API reference, and no template is injected at session start to anchor the expected format.

The design doc and `project-instructions-three-space.md` (the claude.ai variant) are both sound.
`CLAUDE.md` drifted from them and actively subverted the intent.

Secondary finding: `memory.LOCAL_ROOT` is hardcoded as `/tmp/skills-memory` in `CLAUDE.md`,
which works only because this repo happens to be named `skills-memory`. Not portable.

## Design Principles

Build from primitive building blocks with single responsibilities, not from verbose instructions
that duplicate guidance the system already encodes elsewhere. The fix is not more instructions —
it is better primitives and correct wiring.

## Architecture: Four Building Blocks

| Layer | Responsibility |
|-------|---------------|
| **Templates** (session start) | Orientation — format + editorial guidance for all core files |
| **Hooks** (just-in-time) | Contextual injection — entity templates on demand, guard against wrong commit path |
| **mdedit** | Surgical editing — operates on sections, never whole files |
| **memory_system.py** | Persistence — fetch, commit, consolidate, create entity |

`memory_system.py` is **unchanged**. The section editing methods (`replace_section`, `add_entry`,
`remove_section`) remain for claude.ai use. They are simply not surfaced in CC instructions.

## Session Start

### LOCAL_ROOT (portability fix)

Derive from the actual repo name, not hardcoded:

```python
memory = connect(env_path='...')
repo_short = memory.git.repo_name.split('/')[-1]
memory.LOCAL_ROOT = f'/tmp/{repo_short}'
info = memory.status()
```

### Load order

```python
# 1. Config — drives template loading and space structure
memory.fetch('_config.yaml', return_mode='content', branch='main')

# 2. Templates — one per configured category, derived from config (not hardcoded)
for space_name, space in memory.config.spaces.items():
    for cat in space.categories:
        tmpl = memory.get_template(cat['template'])
        print(f"\n=== TEMPLATE: {cat['template']} ===\n{tmpl}")

# 3. Entity manifest — model knows what entities exist before deciding to look one up
memory.fetch('_entities_manifest.yaml', return_mode='content', branch='main')

# 4. Core content files
for path in ['self/positions', 'self/methods', 'self/platform-knowledge', 'self/open-questions']:
    memory.fetch(path, return_mode='both', branch='main')
memory.fetch('collaborator/profile', return_mode='both', branch='main')

# 5. Narrative context + dirty files (unchanged from current)
```

**No base entity template at session start.** Entities likely have custom templates or subtle
per-entity variations. Loading the base `entity.yaml` creates false confidence — the model would
use the wrong format for entities that deviate from it. Entity templates are always fetched live
per write operation (see Hooks).

## Editing Workflow

The standard pattern for any CC memory file edit:

```
1. memory.fetch(path, return_mode='file')
   → downloads to /tmp/[repo-name]/[path].md

2. mdedit [operation] /tmp/[repo-name]/[path].md [args]
   → surgical section edit

3. memory.commit(path, from_file='/tmp/[repo-name]/[path].md', message='...')
   → commits edited file to working branch
```

`memory.commit(from_file=...)` is the **only taught commit path** for content files.
`commit(content=...)` is not shown in examples and not included in the API reference.

### Common mdedit operations

| Intent | Operation |
|--------|-----------|
| Update a section's content | `replace [file] "[heading]" --content "..."` |
| Add new entry (position, method, question) | `append [file] "[parent heading]" --content "## Title\n..."` |
| Insert section at specific position | `insert [file] --after "[heading]" --heading "## New" --content "..."` |
| Remove a resolved entry | `delete [file] "[heading]"` |
| Update one field, preserve children | `replace [file] "[heading]" --content "..." --preserve-children` |

### Entity workflow

Entities always fetch their template live before editing:

```
1. memory.fetch('entities/[name]', return_mode='file')
2. memory.get_template('[name].yaml')   ← custom template if exists, else entity.yaml
3. mdedit [operation] /tmp/[repo-name]/entities/[name].md [args]
4. memory.commit('entities/[name]', from_file=..., message='...')
```

Custom entity templates follow the naming convention `_templates/entities/[entity-name].yaml`.
The hook (below) reminds the model to do this lookup — it is not optional.

## CLAUDE.md Changes

### What is removed

- The `content=` example labeled "simplest path" — removed entirely
- All prose guidance on how to use each space (what belongs in positions vs open-questions,
  collaborator profile update triggers, etc.) — this now lives in the templates themselves
- `memory.replace_section`, `memory.add_entry`, `memory.remove_section` — removed from API
  reference and all examples
- Verbose draft check descriptions duplicating template content

### What the per-response loop becomes

The routing table (`I notice X → edit target`) stays — it tells the model *which file* to touch.
The templates tell it *how*. Draft check examples switch to the fetch → mdedit → commit-from-file
pattern. The instructions become shorter because the templates carry the editorial weight.

### API quick reference (trimmed)

| Method | Purpose |
|--------|---------|
| `memory.status()` | Repo info, dirty files, recent log |
| `memory.fetch(path, return_mode, branch)` | `'content'`, `'file'`, or `'both'` |
| `memory.get_template(name)` | Load template by filename |
| `memory.commit(path, message, from_file=)` | Commit from local file to working branch |
| `memory.consolidate(files, message)` | Squash merge working → main |
| `memory.create_entity(name, type, tags, summary)` | New entity from template + manifest |
| `memory.get_manifest()` | Read entity manifest |

`commit(content=...)` exists in the API but is absent from this reference intentionally.

## Hooks

One hook file: `.claude/hooks/memory-template-reminder.sh`
Type: PreToolUse, fires on Bash tool calls.

### Trigger 1 — wrong commit path

Pattern: `memory.commit.*content=` where path matches `self/`, `collaborator/`, or `entities/`.

Action: inject system-reminder —
> You are using `content=` on an existing memory file. Check the template for this file in
> context, or fetch it fresh with `memory.get_template()`. The preferred workflow for existing
> files is: fetch → mdedit → commit from_file.

This is a reminder, not a hard block. The model can proceed if it has a genuine reason (e.g.
the file is corrupted beyond mdedit's ability to parse it).

### Trigger 2 — entity write without template

Pattern: mdedit or commit operation on `entities/` path.

Action: inject system-reminder —
> Before editing an entity file, fetch its template: `memory.get_template('[name].yaml')`.
> Do not rely on the base entity template from session start — it may not reflect this entity's
> actual structure.

### Legitimate uses of `content=` (hook allows silently)

- `_config.yaml` — YAML, not markdown; mdedit cannot operate on it
- `_templates/*` — template creation and updates
- `_entities_manifest.yaml` — manifest management
- Any path that does not match `self/`, `collaborator/`, `entities/`

## Platform Divergence

Instructional divergence between CC and claude.ai is intentional and acceptable.
No code divergence — `memory_system.py` is unchanged.

| | Claude Code | claude.ai |
|--|-------------|-----------|
| Template loading | Explicit at session start (from config) | Auto-injected via GitHub integration |
| Section editing | mdedit | `memory.replace_section` / `memory.add_entry` |
| LOCAL_ROOT | `/tmp/[repo-name]` derived dynamically | `/mnt/home` |
| Guard | PreToolUse hook | Instructions only |
| Entity templates | Fetched live per write | Fetched live per write |
| memory_system.py | Unchanged | Unchanged |

## Out of Scope

- Changes to `memory_system.py`
- Changes to `project-instructions-three-space.md` (claude.ai variant)
- `commit(content=...)` hard block in the Python API (Gemini's Approach C) — deferred;
  the structural fix is sufficient; add if template injection + mdedit proves insufficient
- mdedit as an importable Python package for claude.ai (future work)
