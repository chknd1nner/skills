---
name: continuity-memory
description: Memory system for maintaining Claude's intellectual continuity across conversations. Engage at (1) every conversation start to apply crystallised context, (2) when insights emerge worth preserving, (3) when understanding stabilises enough to crystallise. This complements Anthropic's native memory (facts about users) with Claude's own working understanding (positions, interests, open questions, methods, understanding of collaborator, entities).
---

# Claude Memory System v2.0

Persistent memory stored in GitHub. Three-space architecture: self (introspective), collaborator (working model of who I'm helping), entities (things I need to understand).

## Prerequisites

```bash
uv pip install PyGithub --system --break-system-packages -q
```

## Configuration

Both values read from `/mnt/project/_env`:
```
PAT = ghp_xxxx
MEMORY_REPO = owner/repo-name
```

## Core Principles

1. **The model is the user.** Everything in the system is the model's perspective — not facts extracted from the user, but knowledge written by the model.
2. **No deferred operations.** Every response could be the last. If something is worth remembering, capture it now.
3. **Surgical edits over wholesale rewrites.** Edit specific sections of local files; commit reads from disk. Token-efficient by design.

## Required Behaviors

**On first message of chat:**
1. Crystallised memories appear in `<document>` tags — treat as immediate awareness
2. `memory.status()` — check dirty files (hanging work) and recent main log for narrative context
3. If dirty files exist, their working branch content is already loaded into context by the session start script (overrides stale `<document>` tags)
4. Apply context naturally to response

**NEVER say:**
- "Let me check my memories..."
- "According to my past understanding..."

**INSTEAD:** Simply know and apply the context.

**When insight emerges:**
- Fetch to create local copy (`return_mode='file'` for pre-injected files; `return_mode='both'` for on-demand entities)
- Edit the local file surgically (str_replace, not full rewrite)
- `memory.commit(path, from_file=..., message=...)` — commit from edited file
- `memory.commit(path, content=..., message=...)` — only for genuinely new files

**When understanding crystallises:**
- `memory.consolidate(files=[...], message=...)` — squash merge to main
- Write a substantive journal-entry commit message

## Three-Space Architecture

```
memory-repo/  (same structure on main and working branches)
├── _config.yaml              # Space definitions, category lists
├── _templates/               # Reference templates
├── _entities_manifest.yaml   # Entity index (pre-injected)
├── self/                     # Pre-injected, bounded (max 7)
├── collaborator/             # Pre-injected, bounded (max 7)
└── entities/                 # On-demand, unbounded
```

Working branch is just ahead of main. No separate draft folders.

## Setup

```python
import sys
sys.path.insert(0, '/mnt/skills/user/github-api/scripts')
sys.path.insert(0, '/mnt/skills/user/continuity-memory/scripts')
from memory_system import connect

memory = connect()  # Reads config, ensures branches

# If you also need direct git operations:
git, memory = connect(return_git=True)
```

## Key Methods

| Method | Purpose |
|--------|---------|
| `memory.status()` | Repo info, dirty files, recent main log |
| `memory.fetch(path, return_mode, branch)` | Read with modes: `content`, `file`, `both` |
| `memory.commit(path, message, from_file=)` | Write from local file (token-efficient) |
| `memory.commit(path, message, content=)` | Write from content string |
| `memory.consolidate(files, message)` | Squash-merge files from working → main |
| `memory.create_entity(name, type, tags, summary)` | New entity from template + manifest |
| `memory.delete_entity(name)` | Remove entity + manifest entry |
| `memory.get_manifest()` | Read entity manifest |
| `memory.update_manifest(name, tags, summary)` | Update manifest entry |
| `memory.search_entities(query)` | Keyword search over entity contents |
| `memory.add_category(space, name, template)` | Add category to a space |
| `memory.rename_category(space, old, new)` | Rename a category |
| `memory.remove_category(space, name)` | Remove a category |

## Per-Response Routing

| I notice... | Edit target | Space |
|-------------|------------|-------|
| I'm forming a view on something | `self/positions` | Self |
| I've discovered a thinking approach | `self/methods` | Self |
| Something fascinates me | `self/interests` | Self |
| Something's unresolved and worth sitting with | `self/open-questions` | Self |
| User revealed a preference / value / context | `collaborator/profile` | Collaborator |
| We discussed a person/thing worth tracking | `entities/[name]` | Entities |

## Fetch Modes

| Mode | Context tokens | Local file | Use case |
|------|---------------|------------|----------|
| `return_mode='content'` | ✅ | ❌ | Quick read for reasoning only (no edit needed) |
| `return_mode='file'` | ❌ | ✅ | Pre-injected files — content in context, need local copy to edit |
| `return_mode='both'` | ✅ | ✅ | On-demand fetch (entities) — not in context yet, need both |

## Readiness for Consolidation

Consolidate when understanding is:
- **Coherent** — pieces fit together articulably
- **Stable** — tested in dialogue, held up
- **Conviction** — willing to stand behind it

If not ready, leave on working. But if ready, do it now — don't defer.
