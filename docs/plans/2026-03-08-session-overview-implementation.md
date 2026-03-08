# Session Overview Skill — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a `/session-overview` skill that prints a unified, formatted summary of all configuration affecting a Claude Code session, with clickable file paths and LLM-generated summaries for large content files.

**Architecture:** A bash script (`session-overview.sh`) crawls all known config locations (project, user, managed), parses JSON with jq, and outputs structured data. The SKILL.md wraps the script, adds one-line summaries for large files, and prints the final output to stdout.

**Tech Stack:** Bash, jq, Claude Code skill system

**Design doc:** `docs/plans/2026-03-08-session-overview-design.md`
**Skill template:** `templates/SKILL-template.md`

---

### Task 1: Create skill directory structure

**Files:**
- Create: `claude-code-only/session-overview/SKILL.md`
- Create: `claude-code-only/session-overview/scripts/session-overview.sh`

**Step 1: Create directories**

```bash
mkdir -p claude-code-only/session-overview/scripts
```

**Step 2: Create placeholder SKILL.md**

Create `claude-code-only/session-overview/SKILL.md` with minimal frontmatter:

```markdown
---
name: session-overview
description: Print a unified overview of all hooks, skills, CLAUDE.md files, MCP servers, agents, plugins, and settings affecting the current Claude Code session. Use when user asks what's active, what's configured, or wants a session overview.
---

# Purpose

Placeholder — will be completed in Task 5.
```

**Step 3: Create placeholder script**

Create `claude-code-only/session-overview/scripts/session-overview.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "session-overview: placeholder"
```

```bash
chmod +x claude-code-only/session-overview/scripts/session-overview.sh
```

**Step 4: Commit**

```bash
git add claude-code-only/session-overview/
git commit -m "feat: scaffold session-overview skill directory structure"
```

---

### Task 2: Implement settings file discovery

The script must find all settings files across scopes and output their paths and content.

**Files:**
- Modify: `claude-code-only/session-overview/scripts/session-overview.sh`

**Step 1: Write the settings discovery section**

Replace the placeholder script with the settings discovery logic. The script should:

- Accept `--by-scope` flag, default to by-category
- Detect the project root (walk up to find `.claude/` or use `$PWD`)
- Define known config file locations:
  - Project: `$PROJECT_ROOT/.claude/settings.json`, `$PROJECT_ROOT/.claude/settings.local.json`
  - User: `$HOME/.claude/settings.json`
  - Managed: `/etc/claude/settings.json`, `$HOME/.claude/managed/settings.json` (best-effort)
- For each that exists, record path + scope label
- Output a `SETTINGS_FILES` section in a parseable format:

```
=== SETTINGS_FILES ===
[project] /full/path/.claude/settings.json
[user] /Users/martinkuek/.claude/settings.json
=== END_SETTINGS_FILES ===
```

**Step 2: Test manually**

```bash
cd /Users/martinkuek/Documents/Projects/skills
bash claude-code-only/session-overview/scripts/session-overview.sh
```

Expected: Should list `[user] /Users/martinkuek/.claude/settings.json`. No project settings file exists for this repo.

**Step 3: Commit**

```bash
git add claude-code-only/session-overview/scripts/session-overview.sh
git commit -m "feat(session-overview): settings file discovery across scopes"
```

---

### Task 3: Implement CLAUDE.md discovery

**Files:**
- Modify: `claude-code-only/session-overview/scripts/session-overview.sh`

**Step 1: Add CLAUDE.md discovery**

Search for CLAUDE.md files at:
- `$PROJECT_ROOT/CLAUDE.md` (project)
- `$HOME/.claude/CLAUDE.md` (user)

For each found file, output:
```
=== CLAUDE_MD ===
[project] 47 /full/path/CLAUDE.md
[user] 12 /Users/martinkuek/.claude/CLAUDE.md
=== END_CLAUDE_MD ===
```

Format: `[scope] <line_count> <absolute_path>`

Also output the first 500 chars of each file in a separate block for LLM summarization:
```
=== CLAUDE_MD_CONTENT ===
--- /full/path/CLAUDE.md ---
<first 500 chars>
--- END ---
=== END_CLAUDE_MD_CONTENT ===
```

**Step 2: Test manually**

```bash
bash claude-code-only/session-overview/scripts/session-overview.sh
```

Expected: Should show `[project] 47 /Users/martinkuek/Documents/Projects/skills/CLAUDE.md` (approximately). No user CLAUDE.md exists.

**Step 3: Commit**

```bash
git add claude-code-only/session-overview/scripts/session-overview.sh
git commit -m "feat(session-overview): CLAUDE.md file discovery and content extraction"
```

---

### Task 4: Implement hooks, MCP servers, agents, plugins, skills, and memory discovery

This is the bulk of the script. Each category parses from the settings JSON files already discovered.

**Files:**
- Modify: `claude-code-only/session-overview/scripts/session-overview.sh`

**Step 1: Add hooks extraction**

For each settings file found in Task 2, use jq to extract hooks:
```bash
jq -r '.hooks // {} | to_entries[] | "\(.key) \(.value | length) hooks"' "$settings_file"
```

Output format:
```
=== HOOKS ===
[user] SessionStart command:"bash startup.sh" /Users/martinkuek/.claude/settings.json
[project] PreToolUse matcher:Bash command:"safety.sh" /path/.claude/settings.json
=== END_HOOKS ===
```

For each hook, extract: event type, matcher (if any), and a short command summary (first 60 chars of the command).

**Step 2: Add MCP servers extraction**

Parse from settings files:
```bash
jq -r '.mcpServers // {} | to_entries[] | "\(.key) \(.value.type // "stdio")"' "$settings_file"
```

Output format:
```
=== MCP_SERVERS ===
[user] claude-in-chrome stdio /Users/martinkuek/.claude/settings.json
=== END_MCP_SERVERS ===
```

**Step 3: Add agents discovery**

Two sources:
1. Settings files: `jq -r '.agents // {} | keys[]'`
2. Agent markdown files: `$HOME/.claude/agents/*.md`

Output format:
```
=== AGENTS ===
[user] borg /Users/martinkuek/.claude/agents/borg.md
=== END_AGENTS ===
```

Include first 200 chars of agent .md files in a content block for LLM summarization.

**Step 4: Add plugins discovery**

Enumerate `$HOME/.claude/plugins/cache/` directories. Cross-reference with `enabledPlugins` from user settings to show enabled/disabled status.

```
=== PLUGINS ===
anthropic-agent-skills enabled
claude-plugins-official enabled
flow-state enabled
=== END_PLUGINS ===
```

**Step 5: Add skills discovery**

Three sources:
1. Project skills: `$PROJECT_ROOT/claude-code-only/*/SKILL.md`, `$PROJECT_ROOT/.claude/skills/*/SKILL.md`
2. User skills: `$HOME/.claude/skills/*/SKILL.md`
3. Plugin skills: enumerate from plugin cache dirs

For each, extract the `name:` from frontmatter and count.

```
=== SKILLS ===
[project] deep-research /Users/martinkuek/Documents/Projects/skills/claude-code-only/deep-research/SKILL.md
[user] youtube-to-markdown /Users/martinkuek/.claude/skills/youtube-to-markdown/SKILL.md
[plugin:superpowers] brainstorming /Users/martinkuek/.claude/plugins/cache/claude-plugins-official/superpowers/4.3.1/skills/brainstorming/SKILL.md
=== END_SKILLS ===
```

**Step 6: Add auto-memory discovery**

Find the project memory directory. The path pattern is `$HOME/.claude/projects/<encoded-project-path>/memory/`.

The encoded path replaces `/` with `-`. For the current project:
```bash
project_path=$(pwd)
encoded=$(echo "$project_path" | sed 's|/|-|g')
memory_dir="$HOME/.claude/projects/$encoded/memory"
```

List files in that directory if it exists.

```
=== MEMORY ===
MEMORY.md 23 /Users/martinkuek/.claude/projects/-Users-martinkuek-Documents-Projects-skills/memory/MEMORY.md
=== END_MEMORY ===
```

**Step 7: Add model info**

Extract from settings:
```bash
jq -r '.model // "default"' "$HOME/.claude/settings.json"
```

```
=== MODEL ===
opus
=== END_MODEL ===
```

**Step 8: Test all sections**

```bash
bash claude-code-only/session-overview/scripts/session-overview.sh
```

Verify all sections output correctly. Check that:
- Hooks section appears (even if empty — "none found")
- MCP section shows servers if configured
- Agents shows borg
- Plugins lists all 3 plugin repos
- Skills lists project + user + plugin skills
- Memory finds MEMORY.md

**Step 9: Commit**

```bash
git add claude-code-only/session-overview/scripts/session-overview.sh
git commit -m "feat(session-overview): hooks, MCP, agents, plugins, skills, memory discovery"
```

---

### Task 5: Implement formatted output mode

The script currently outputs machine-parseable blocks. Now add the `--formatted` flag (default) that produces the nice human-readable output, and `--raw` to get the parseable blocks (for LLM consumption).

**Files:**
- Modify: `claude-code-only/session-overview/scripts/session-overview.sh`

**Step 1: Add output formatting**

When `--formatted` (default), output:

```
═══ Session Overview ═══════════════════════════════════

── Model ───────────────────────────────────────────────
opus | permissions: default

── CLAUDE.md Files (1) ─────────────────────────────────
 [project] (47 lines)
   /Users/martinkuek/Documents/Projects/skills/CLAUDE.md

── Hooks (0) ───────────────────────────────────────────
 (none)

── MCP Servers ─────────────────────────────────────────
 [user] claude-in-chrome (stdio)
   /Users/martinkuek/.claude/settings.json

...etc
```

Skip sections with zero items (except always show Model). Use box-drawing characters for headers. Print absolute paths on their own line, indented, for clickability.

When `--raw`, output the `=== SECTION ===` blocks from Task 4. When `--by-scope`, group all items by scope instead of category.

**Step 2: Test formatted output**

```bash
bash claude-code-only/session-overview/scripts/session-overview.sh
bash claude-code-only/session-overview/scripts/session-overview.sh --raw
bash claude-code-only/session-overview/scripts/session-overview.sh --by-scope
```

**Step 3: Commit**

```bash
git add claude-code-only/session-overview/scripts/session-overview.sh
git commit -m "feat(session-overview): formatted and by-scope output modes"
```

---

### Task 6: Write the SKILL.md

**Files:**
- Modify: `claude-code-only/session-overview/SKILL.md`

**Step 1: Write the full SKILL.md**

Follow `templates/SKILL-template.md` structure. Key sections:

- **Frontmatter:** name + description (trigger on "session overview", "what's active", "what's configured", "show my hooks/skills/agents")
- **Purpose:** Unified session introspection without wasting context on redisplaying what's already loaded
- **Variables:**
  ```
  VIEW_MODE: "category" (category or scope)
  ```
- **Instructions:** Reference `scripts/session-overview.sh` — explain it does the heavy lifting
- **Workflow:**
  1. Parse user args (`--by-scope` if requested)
  2. Run `scripts/session-overview.sh --raw` to get structured data
  3. For each content block (CLAUDE.md, agent files), generate a one-line summary
  4. Run `scripts/session-overview.sh [--by-scope]` for formatted output
  5. Insert summaries into the formatted output at the appropriate lines
  6. Print the final result
- **Cookbook:**
  - Scenario 1: Default invocation → run formatted, add summaries
  - Scenario 2: `--by-scope` → pass flag through
  - Scenario 3: User asks "what hooks do I have" → run full overview but highlight the hooks section

**Step 2: Commit**

```bash
git add claude-code-only/session-overview/SKILL.md
git commit -m "feat(session-overview): complete SKILL.md with workflow and cookbook"
```

---

### Task 7: End-to-end testing

**Files:**
- No new files

**Step 1: Test the bash script standalone**

```bash
cd /Users/martinkuek/Documents/Projects/skills
bash claude-code-only/session-overview/scripts/session-overview.sh
```

Verify: formatted output with all sections, absolute clickable paths, scope labels.

**Step 2: Test with --by-scope**

```bash
bash claude-code-only/session-overview/scripts/session-overview.sh --by-scope
```

Verify: output grouped by Project → User → Global.

**Step 3: Test with --raw**

```bash
bash claude-code-only/session-overview/scripts/session-overview.sh --raw
```

Verify: machine-parseable `=== SECTION ===` blocks.

**Step 4: Test the skill invocation**

In a Claude Code session, run `/session-overview` and verify:
- Script output appears
- LLM summaries are inserted for CLAUDE.md files
- All paths are absolute and clickable in VSCode terminal

**Step 5: Test in a different project directory**

```bash
cd /tmp && bash /Users/martinkuek/Documents/Projects/skills/claude-code-only/session-overview/scripts/session-overview.sh
```

Verify: gracefully handles missing project-level configs.

**Step 6: Commit any fixes**

```bash
git add -A && git commit -m "fix(session-overview): end-to-end test fixes"
```

(Only if fixes were needed.)
