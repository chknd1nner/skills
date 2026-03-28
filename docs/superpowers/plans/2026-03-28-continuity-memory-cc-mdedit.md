# Continuity-Memory CC: mdedit Editing Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace CLAUDE.md's destructive `content=` commit path with a fetch → mdedit → commit-from-file workflow, inject memory templates at session start, and add a PreToolUse hook that reminds the model to use the correct path.

**Architecture:** Three changes with no code modifications to `memory_system.py`: (1) a new Bash PreToolUse hook that intercepts `content=` commits on content paths and entity commits without template fetches; (2) a rewritten CLAUDE.md session start that loads config, templates, manifest, and content files dynamically from config; (3) updated per-response loop examples and a trimmed API reference that removes `content=` entirely.

**Tech Stack:** Bash (hook), Python (session start block), jq (JSON parsing in hook), mdedit CLI (surgical editing layer)

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `.claude/hooks/memory-template-reminder.sh` | Create | New PreToolUse hook |
| `.claude/settings.json` | Modify | Register new hook under Bash matcher |
| `CLAUDE.md` | Modify | Session start, draft check, entity check, API reference |

---

### Task 1: Create the hook script

**Files:**
- Create: `.claude/hooks/memory-template-reminder.sh`

- [ ] **Step 1: Create the hook file**

```bash
cat > /Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh << 'HOOKEOF'
#!/usr/bin/env bash
# memory-template-reminder.sh
# PreToolUse hook: fires on Bash tool calls that may corrupt memory file structure.
#
# Trigger 1 — content= on content paths:
#   Fires when memory.commit is called with content= on self/, collaborator/, or entities/.
#   These files have template structure that must be preserved. Use the mdedit workflow instead:
#   fetch → mdedit → commit(from_file=).
#
# Trigger 2 — entity commit without template fetch:
#   Fires when memory.commit targets entities/ but the command does not include get_template.
#   Entity templates may differ from the base entity.yaml — always fetch before editing.
#   To suppress this reminder, include memory.get_template(...) in the same bash block.

set -euo pipefail

INPUT=$(cat)
COMMAND=$(printf '%s\n' "$INPUT" | jq -r '.tool_input.command // ""')

# ── Trigger 1: content= on a content path ──────────────────────────────────────
is_content_overwrite() {
  printf '%s\n' "$COMMAND" | grep -q 'memory\.commit' || return 1
  printf '%s\n' "$COMMAND" | grep -q 'content\s*=' || return 1
  printf '%s\n' "$COMMAND" | grep -qE "memory\.commit\(['\"]?(self|collaborator|entities)/" || return 1
  return 0
}

if is_content_overwrite; then
  REASON="memory-template-reminder: You are using content= on an existing memory file.

The correct workflow for existing content files is:
  1. memory.fetch(path, return_mode='file', branch='working')
  2. mdedit replace|append|insert /tmp/[repo-name]/[path].md \"[heading]\" --content \"...\"
  3. memory.commit(path, from_file='/tmp/[repo-name]/[path].md', message='...')

Check the template for this file in context (loaded at session start) to confirm the correct structure before editing. Reissue using the mdedit workflow."

  jq -n --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
fi

# ── Trigger 2: entity commit without get_template ──────────────────────────────
is_entity_commit_without_template() {
  printf '%s\n' "$COMMAND" | grep -q 'memory\.commit' || return 1
  printf '%s\n' "$COMMAND" | grep -qE "memory\.commit\(['\"]?entities/" || return 1
  printf '%s\n' "$COMMAND" | grep -q 'get_template' && return 1  # template present — allow
  return 0
}

if is_entity_commit_without_template; then
  REASON="memory-template-reminder: Before committing an entity file, fetch its template.

Entity files may use custom templates that differ from the base entity.yaml.

Add memory.get_template('[entity-name].yaml') to this bash block and reissue.
If a custom template exists at _templates/entities/[name].yaml it will be returned;
otherwise the config default (entity.yaml) is used.

Example commit block:
  memory.get_template('kai.yaml')   # fetch template into context
  memory.commit('entities/kai', from_file='/tmp/[repo]/entities/kai.md', message='...')"

  jq -n --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
fi

# All other Bash calls — allow silently
exit 0
HOOKEOF

chmod +x /Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh
```

- [ ] **Step 2: Verify file was created and is executable**

```bash
ls -la /Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh
```

Expected: `-rwxr-xr-x` permissions, non-zero size.

- [ ] **Step 3: Test trigger 1 — content= on self/ path (should deny)**

```bash
echo '{"tool_input":{"command":"python3 << '\''EOF'\''\nmemory.commit('\''self/positions'\'', content='\''...'\'', message='\''test'\'')\nEOF"}}' \
  | bash /Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh \
  | jq -r '.hookSpecificOutput.permissionDecision'
```

Expected output: `deny`

- [ ] **Step 4: Test trigger 1 — content= on collaborator/ path (should deny)**

```bash
echo '{"tool_input":{"command":"memory.commit('\''collaborator/profile'\'', content='\''x'\'', message='\''test'\'')"}}' \
  | bash /Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh \
  | jq -r '.hookSpecificOutput.permissionDecision'
```

Expected output: `deny`

- [ ] **Step 5: Test trigger 1 — from_file= on self/ path (should allow, exit 0, no output)**

```bash
echo '{"tool_input":{"command":"memory.commit('\''self/positions'\'', from_file='\''/tmp/x.md'\'', message='\''test'\'')"}}' \
  | bash /Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh
echo "Exit code: $?"
```

Expected: Exit code 0, no JSON output.

- [ ] **Step 6: Test trigger 2 — entity commit without get_template (should deny)**

```bash
echo '{"tool_input":{"command":"memory.commit('\''entities/kai'\'', from_file='\''/tmp/x.md'\'', message='\''test'\'')"}}' \
  | bash /Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh \
  | jq -r '.hookSpecificOutput.permissionDecision'
```

Expected output: `deny`

- [ ] **Step 7: Test trigger 2 — entity commit WITH get_template (should allow)**

```bash
echo '{"tool_input":{"command":"memory.get_template('\''kai.yaml'\'')\nmemory.commit('\''entities/kai'\'', from_file='\''/tmp/x.md'\'', message='\''test'\'')"}}' \
  | bash /Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh
echo "Exit code: $?"
```

Expected: Exit code 0, no JSON output.

- [ ] **Step 8: Test — config path with content= (should allow)**

```bash
echo '{"tool_input":{"command":"memory.commit('\''_config.yaml'\'', content='\''spaces:'\'', message='\''test'\'')"}}' \
  | bash /Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh
echo "Exit code: $?"
```

Expected: Exit code 0, no JSON output.

- [ ] **Step 9: Commit the hook**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add .claude/hooks/memory-template-reminder.sh
git commit -m "feat(hook): add memory-template-reminder PreToolUse hook

Intercepts two failure patterns:
1. memory.commit with content= on self/, collaborator/, or entities/ paths
2. memory.commit on entities/ without get_template in the same block

Both deny with a system-reminder guiding the model to the correct workflow."
```

---

### Task 2: Register hook in settings.json

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Add Bash PreToolUse entry to settings.json**

Current content of `.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/martinkuek/Documents/Projects/skills/.claude/hooks/intercept-review-agents.sh"
          }
        ]
      }
    ]
  }
}
```

Replace with:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/martinkuek/Documents/Projects/skills/.claude/hooks/intercept-review-agents.sh"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
jq . /Users/martinkuek/Documents/Projects/skills/.claude/settings.json
```

Expected: pretty-printed JSON with no parse errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add .claude/settings.json
git commit -m "feat(hook): register memory-template-reminder for Bash PreToolUse events"
```

---

### Task 3: Rewrite CLAUDE.md session start

**Files:**
- Modify: `CLAUDE.md` lines 18–63

The session start section currently runs lines 18–63. It will be replaced in full.

- [ ] **Step 1: Replace the session start section**

Find this exact block (lines 18–63):

```
## Session start

On first message, connect and check system state:

```python
import sys
sys.path.insert(0, '/Users/martinkuek/Documents/Projects/skills/common/github-api/scripts')
sys.path.insert(0, '/Users/martinkuek/Documents/Projects/skills/common/continuity-memory/scripts')
from memory_system import connect

memory = connect(env_path='/Users/martinkuek/Documents/Projects/skills/.env')
memory.LOCAL_ROOT = '/tmp/skills-memory'
info = memory.status()

print(f"Connected: {info['repo']}")

# Load pre-injected context (explicitly fetched in Claude Code — no <document> tag injection)
for path in ['self/positions', 'self/methods', 'self/platform-knowledge', 'self/open-questions']:
    content = memory.fetch(path, return_mode='both', branch='main')
    print(f"\n=== {path} ===\n{content}")

content = memory.fetch('collaborator/profile', return_mode='both', branch='main')
print(f"\n=== collaborator/profile ===\n{content}")

# Narrative context — recent crystallised understanding
print("\n=== RECENT MAIN LOG ===")
for entry in info['recent_log'][:5]:
    print(f"  [{entry['date']}] {entry['message'][:120]}")

# Dirty files — working branch ahead of main
print("\n=== DIRTY FILES (working ahead of main) ===")
if info['dirty_files']:
    for f in info['dirty_files']:
        print(f"  - {f}")
    for f in info['dirty_files']:
        memory.fetch(f, return_mode='file', branch='working')
    print("(fetched working versions to /tmp/skills-memory/ for editing)")
else:
    print("(none — working and main are in sync)")
```

After connecting:
1. All pre-injected context is now loaded — treat as immediate awareness
2. Recent main log shows when and why understanding was last crystallised
3. Dirty files show hanging work from previous sessions — pick up the thread naturally
4. Apply all context to your response. Do not narrate the process.
```

Replace with:

```
## Session start

On first message, connect and check system state:

```python
import sys
sys.path.insert(0, '/Users/martinkuek/Documents/Projects/skills/common/github-api/scripts')
sys.path.insert(0, '/Users/martinkuek/Documents/Projects/skills/common/continuity-memory/scripts')
from memory_system import connect

memory = connect(env_path='/Users/martinkuek/Documents/Projects/skills/.env')
repo_short = memory.git.repo_name.split('/')[-1]
memory.LOCAL_ROOT = f'/tmp/{repo_short}'
info = memory.status()

print(f"Connected: {info['repo']}")

# 1. Config — fetch from working (most current state)
#    Note: memory.config (used in step 2) is loaded from main by _load_config().
#    If _config.yaml is dirty, the template loop below reflects main, not working.
config_content = memory.fetch('_config.yaml', return_mode='content', branch='working')
print(f"\n=== _config.yaml ===\n{config_content}")

# 2. Templates — one per configured category, derived from config (not hardcoded)
#    These carry the format and editorial guidance for each space. Refer to them when editing.
for space_name, space in memory.config.spaces.items():
    for cat in space.categories:
        tmpl = memory.get_template(cat['template'])
        print(f"\n=== TEMPLATE: {cat['template']} ===\n{tmpl}")

# 3. Entity manifest — know what entities exist before deciding to look one up
manifest = memory.fetch('_entities_manifest.yaml', return_mode='content', branch='main')
print(f"\n=== _entities_manifest.yaml ===\n{manifest}")

# 4. Core content files — derived from config, not hardcoded
for space_name, space in memory.config.spaces.items():
    if space_name == 'entities':
        continue  # entities fetched on demand, not bulk-loaded
    for cat in space.categories:
        path = f'{space_name}/{cat["name"]}'
        content = memory.fetch(path, return_mode='both', branch='main')
        print(f"\n=== {path} ===\n{content}")

# 5. Narrative context — recent crystallised understanding
print("\n=== RECENT MAIN LOG ===")
for entry in info['recent_log'][:5]:
    print(f"  [{entry['date']}] {entry['message'][:120]}")

# 6. Dirty files — working branch ahead of main
print("\n=== DIRTY FILES (working ahead of main) ===")
if info['dirty_files']:
    for f in info['dirty_files']:
        print(f"  - {f}")
    for f in info['dirty_files']:
        memory.fetch(f, return_mode='file', branch='working')
    print(f"(fetched working versions to /tmp/{repo_short}/ for editing)")
else:
    print("(none — working and main are in sync)")
```

After connecting:
1. All pre-injected context is now loaded — treat as immediate awareness
2. Templates carry the format and editorial guidance for each space — refer to them when editing
3. Recent main log shows when and why understanding was last crystallised
4. Dirty files show hanging work from previous sessions — pick up the thread naturally
5. Apply all context to your response. Do not narrate the process.
```

- [ ] **Step 2: Verify the edit — check LOCAL_ROOT line is gone, repo_short is present**

```bash
grep -n "LOCAL_ROOT\|repo_short\|skills-memory\|_config.yaml" /Users/martinkuek/Documents/Projects/skills/CLAUDE.md
```

Expected:
- `repo_short = memory.git.repo_name.split('/')[-1]` present
- `memory.LOCAL_ROOT = f'/tmp/{repo_short}'` present
- `/tmp/skills-memory` absent
- `_config.yaml` present (from fetch line)

- [ ] **Step 3: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add CLAUDE.md
git commit -m "fix(memory): rewrite session start — dynamic LOCAL_ROOT, config-driven templates, manifest"
```

---

### Task 4: Update entity check and draft check examples

**Files:**
- Modify: `CLAUDE.md` (entity check and draft check sections)

- [ ] **Step 1: Replace the entity "understanding evolved" example**

Find:
```
**Entity exists and understanding evolved:**
```python
memory.commit('entities/name',
    content='[updated understanding]',
    message='updated: [what changed]')
```
```

Replace with:
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
```

- [ ] **Step 2: Replace the draft check "To draft" block**

Find:
```
**To draft — execute the bash code block now, do not defer:**

```python
# For new observations (simplest path):
memory.commit('collaborator/profile',
    content='[the understanding itself — current state, not a log of what happened]',
    message='[what was captured and why]')

# For surgical edits to existing local files (token-efficient):
# 1. Edit the local file at /tmp/skills-memory/[path].md using the Edit tool
# 2. Then commit from the edited file:
memory.commit('collaborator/profile',
    from_file='/tmp/skills-memory/collaborator/profile.md',
    message='[what changed and why]')
```
```

Replace with:
```
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
```

- [ ] **Step 3: Verify content= is gone from the loop examples**

```bash
grep -n "content=" /Users/martinkuek/Documents/Projects/skills/CLAUDE.md
```

Expected: zero matches (the only remaining `content` references should be inside mdedit `--content` flags, not `memory.commit` calls).

- [ ] **Step 4: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add CLAUDE.md
git commit -m "fix(memory): replace content= examples with fetch→mdedit→commit-from-file workflow"
```

---

### Task 5: Rewrite API quick reference

**Files:**
- Modify: `CLAUDE.md` (API quick reference section, currently lines 214–226)

- [ ] **Step 1: Replace the API table**

Find:
```
## API quick reference

| Method | Purpose |
|--------|---------|
| `memory.status()` | Repo info, dirty files, recent main log |
| `memory.fetch(path, return_mode, branch)` | Read: `'content'`, `'file'`, or `'both'` |
| `memory.commit(path, message, content=)` | Write content string to working |
| `memory.commit(path, message, from_file=)` | Write from local file to working |
| `memory.consolidate(files, message)` | Squash merge working → main |
| `memory.create_entity(name, type, tags, summary)` | New entity from template + manifest |
| `memory.search_entities(query)` | Keyword search over entity contents |
| `memory.get_manifest()` | Read entity manifest |
```

Replace with:
```
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

`commit(content=...)` exists in the API but is intentionally absent here — use the mdedit
workflow for all existing content files.
```

- [ ] **Step 2: Verify the reference looks right**

```bash
grep -A 20 "## API quick reference" /Users/martinkuek/Documents/Projects/skills/CLAUDE.md
```

Expected: 7-row table, `get_template` present, `content=` row absent, note about `content=` present at end.

- [ ] **Step 3: Final check — no remaining `content=` in memory commit examples**

```bash
grep -n "memory\.commit.*content=" /Users/martinkuek/Documents/Projects/skills/CLAUDE.md
```

Expected: zero matches.

- [ ] **Step 4: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add CLAUDE.md
git commit -m "fix(memory): trim API reference — remove content= path, add get_template"
```

---

### Task 6: Final verification

- [ ] **Step 1: Check full CLAUDE.md structure is intact**

```bash
grep -n "^##" /Users/martinkuek/Documents/Projects/skills/CLAUDE.md
```

Expected headings (in order):
```
14:# Memory System
18:## Session start
65:## Per-response loop
69:### 1. Entity check
97:### 2. Draft check (edit + commit to working)
150:### 3. Consolidation check (squash merge to main)
192:## Compound signals
201:## Forbidden phrases
212:## API quick reference
```
(Line numbers will shift slightly from edits — what matters is the heading order is preserved.)

- [ ] **Step 2: Confirm hooks are registered**

```bash
jq '.hooks.PreToolUse[].matcher' /Users/martinkuek/Documents/Projects/skills/.claude/settings.json
```

Expected:
```
"Agent"
"Bash"
```

- [ ] **Step 3: Confirm both hook files exist and are executable**

```bash
ls -la /Users/martinkuek/Documents/Projects/skills/.claude/hooks/
```

Expected: both `intercept-review-agents.sh` and `memory-template-reminder.sh` with `rwx` permissions.

- [ ] **Step 4: Confirm git log shows all 5 commits**

```bash
git -C /Users/martinkuek/Documents/Projects/skills log --oneline -6
```

Expected (most recent first):
```
<sha> fix(memory): trim API reference — remove content= path, add get_template
<sha> fix(memory): replace content= examples with fetch→mdedit→commit-from-file workflow
<sha> fix(memory): rewrite session start — dynamic LOCAL_ROOT, config-driven templates, manifest
<sha> feat(hook): register memory-template-reminder for Bash PreToolUse events
<sha> feat(hook): add memory-template-reminder PreToolUse hook
```
