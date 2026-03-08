# Session Overview Skill — Design

## Problem

Claude Code sessions are affected by configuration from multiple sources (hooks, skills, CLAUDE.md files, MCP servers, agents, plugins, settings) spread across three scopes (project, user, global/managed). There is no single command to see what's active. Project-level files are visible in the VSCode explorer, but user-level (`~/.claude/`) and global/managed configs are hidden and require running 12+ individual slash commands.

## Solution

A `session-overview` skill that invokes a bash script to inspect all configuration sources and prints a formatted summary to stdout with clickable absolute file paths (cmd-click in VSCode/iTerm2 opens the file).

### Key design decisions

- **Bash script does 90% of the work** — parsing JSON, discovering files, formatting output. No LLM tokens wasted on structural data that's already in the system prompt.
- **LLM adds one-line summaries** — only for large content files (CLAUDE.md, skill descriptions). Small token cost, high value.
- **Clickable absolute paths** — every config file gets its full path printed so users can cmd-click to open it in VSCode without leaving the editor.
- **Scope labels on every item** — `[project]`, `[user]`, `[global]` so you always know where something lives.
- **Two view modes** — default by-category, `--by-scope` flag to group by scope instead.

## Architecture

```
/session-overview [--by-scope]
        │
        ▼
   SKILL.md (thin wrapper, invokes script, instructs LLM to summarize)
        │
        ▼
   scripts/session-overview.sh
   ├── Discovers all config files across 3 scopes
   ├── Parses JSON with jq
   ├── Formats + prints structural info (line counts, hook types, server names)
   └── Outputs raw content of large files for LLM summarization
        │
        ▼
   LLM post-processing:
   ├── Generates one-line summaries for CLAUDE.md files, agent descriptions
   └── Prints final formatted output to stdout
```

## Output format

### Default: by category

```
═══ Session Overview ═══════════════════════════════════

── Model ───────────────────────────────────────────────
claude-opus-4-6 | effort: high | permissions: default

── CLAUDE.md Files (2) ─────────────────────────────────
 [project] (47 lines): Skills repo rules, directory conventions
   /Users/user/projects/myapp/CLAUDE.md
 [user] (12 lines): Global preferences, commit style
   /Users/user/.claude/CLAUDE.md

── Hooks (5) ───────────────────────────────────────────
 [user]    SessionStart  → ~/.claude/hooks/startup.sh
   /Users/user/.claude/settings.json
 [project] PreToolUse    → safety check (Bash)
   /Users/user/projects/myapp/.claude/settings.json

── MCP Servers (2) ─────────────────────────────────────
 [user] claude-in-chrome (stdio) — 15 tools
 [user] filesystem (stdio) — 4 tools
   /Users/user/.claude/settings.json

── Skills (27) ─────────────────────────────────────────
 [plugin] superpowers v4.3.1 (11 skills)
   /Users/user/.claude/plugins/cache/claude-plugins-official/superpowers/4.3.1/
 [plugin] document-skills v4.3.1 (16 skills)
   /Users/user/.claude/plugins/cache/claude-plugins-official/document-skills/4.3.1/

── Plugins (1) ─────────────────────────────────────────
 claude-plugins-official v4.3.1
   /Users/user/.claude/plugins/cache/claude-plugins-official/

── Agents (3) ──────────────────────────────────────────
 [user] code-reviewer: Reviews code against plan
   /Users/user/.claude/settings.json
 [user] borg: Assimilation agent
   /Users/user/.claude/settings.json

── Auto-Memory ─────────────────────────────────────────
 MEMORY.md (23 lines): Project patterns, debugging notes
   /Users/user/.claude/projects/.../memory/MEMORY.md

── Settings Files ──────────────────────────────────────
 [project] /Users/user/projects/myapp/.claude/settings.json
 [local]   /Users/user/projects/myapp/.claude/settings.local.json
 [user]    /Users/user/.claude/settings.json
```

### With `--by-scope`

Same data, grouped into Project → User → Global/Managed sections.

## Script responsibilities (no LLM needed)

The bash script (`scripts/session-overview.sh`) handles:

1. **Settings files** — discover and validate existence of:
   - `$PWD/.claude/settings.json` (project)
   - `$PWD/.claude/settings.local.json` (local)
   - `~/.claude/settings.json` (user)
   - Managed/enterprise paths if they exist
2. **CLAUDE.md files** — find at project root and `~/.claude/CLAUDE.md`
3. **Hooks** — parse from all settings JSON files using jq
4. **MCP servers** — parse from all settings JSON files using jq
5. **Agents** — parse from all settings JSON files using jq
6. **Plugins** — enumerate `~/.claude/plugins/cache/` directories
7. **Skills** — enumerate skill directories within plugins
8. **Auto-memory** — find files in `~/.claude/projects/*/memory/`
9. **Format output** — structured text with scope labels, line counts, absolute paths

The script outputs two things:
- Formatted structural data (printed directly to stdout)
- Raw content of large files as a structured block (for LLM summarization)

## Skill responsibilities (LLM needed)

The SKILL.md instructs Claude to:

1. Run the bash script with any flags passed by the user
2. Read the script's output
3. For each large content file listed, generate a one-line summary
4. Print the final formatted output with summaries inserted

## Skill file structure

```
claude-code-only/session-overview/
├── SKILL.md                          # Skill definition (follows templates/SKILL-template.md)
└── scripts/
    └── session-overview.sh           # Main inspection script
```

## Skill template reference

The SKILL.md will follow the structure defined in `templates/SKILL-template.md`:
- `name` + `description` in frontmatter
- Variables section for `VIEW_MODE` (category vs scope)
- Instructions referencing `scripts/session-overview.sh`
- Workflow with sequential steps
- Cookbook with scenarios for default view vs `--by-scope`

## Dependencies

- `jq` — for JSON parsing (standard on macOS, installable everywhere)
- `bash` — standard shell
- Platform: claude-code-only (requires filesystem + bash access)

## Edge cases

- **Missing jq** — script should detect and fall back to basic grep/sed parsing or warn user
- **No settings files** — gracefully show "none found" per category
- **Empty categories** — skip the section entirely, don't show empty headers
- **Managed/enterprise configs** — best-effort discovery; document known paths
- **Large plugin directories** — summarize counts, don't enumerate every skill file
