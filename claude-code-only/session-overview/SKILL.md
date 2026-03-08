---
name: session-overview
description: Print a unified overview of all hooks, skills, CLAUDE.md files, MCP servers, agents, plugins, and settings affecting the current Claude Code session. Use when user asks what's active, what's configured, wants a session overview, or asks about their setup.
---

# Purpose

Gives users a single-command view of everything affecting their Claude Code session — configuration that's normally spread across 12+ individual slash commands and hidden in `~/.claude/` directories. The bash script does the heavy lifting (file discovery, JSON parsing); the LLM adds one-line summaries for large content files.

## Variables

```
VIEW_MODE: "formatted" (formatted, by-scope, or raw)
```

## Instructions

1. **Bundled script**: `scripts/session-overview.sh` discovers all config files across project, user, and managed scopes. It parses settings JSON with jq and outputs structured data. Run it via Bash tool.

## Workflow

1. Parse the user's request for flags (`--by-scope` or `--raw`)
2. Run `scripts/session-overview.sh --raw` via Bash to get structured data with content blocks
3. For each `CLAUDE_MD_CONTENT` and `AGENTS_CONTENT` block, generate a one-line summary (under 80 chars)
4. Run `scripts/session-overview.sh [--by-scope]` via Bash to get the formatted output
5. Print the formatted output to the user, inserting your one-line summaries after each file's line count. For example, change `[project] (47 lines)` to `[project] (47 lines): Skills repo rules, directory conventions`
6. Do NOT add any preamble or commentary — just print the formatted overview

## Cookbook

### Scenario 1: Default overview

- **IF**: User invokes `/session-overview` with no flags
- **THEN**:
  1. Run `bash scripts/session-overview.sh --raw` — capture output
  2. Extract content blocks, generate one-line summaries for each
  3. Run `bash scripts/session-overview.sh` — capture formatted output
  4. Insert summaries into the formatted output at the appropriate positions
  5. Print the result directly — no extra commentary
- **EXAMPLES**:
  - "User says: /session-overview"
  - "User says: what's affecting my session?"
  - "User says: show me my setup"

### Scenario 2: Group by scope

- **IF**: User asks to see things grouped by scope, or passes `--by-scope`
- **THEN**:
  1. Run `bash scripts/session-overview.sh --raw` — capture output
  2. Generate summaries as above
  3. Run `bash scripts/session-overview.sh --by-scope` — capture formatted output
  4. Insert summaries and print
- **EXAMPLES**:
  - "User says: /session-overview --by-scope"
  - "User says: show me what's configured at each level"

### Scenario 3: Raw output for debugging

- **IF**: User passes `--raw`
- **THEN**:
  1. Run `bash scripts/session-overview.sh --raw`
  2. Print the raw output directly, no summaries needed
- **EXAMPLES**:
  - "User says: /session-overview --raw"
