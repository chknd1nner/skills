# codebase-memory-mcp — Full Agent Config Reference

What the installer *would* have added to Claude Code if run without
`--skip-config`. Extracted verbatim from `src/cli/cli.c` @ `DeusData/codebase-memory-mcp` v0.6.0.

Use this as a menu for cherry-picking behaviours into your own hook/launcher
setup.

---

## Summary of what gets installed

| Component | File | Scope |
|---|---|---|
| 1 skill (`codebase-memory`) | `~/.claude/skills/codebase-memory/SKILL.md` | created |
| MCP entry | `~/.claude/.mcp.json` | created or merged |
| MCP entry (legacy) | `~/.claude.json` | merged |
| PreToolUse hook entry | `~/.claude/settings.json` → `hooks.PreToolUse[]` | merged |
| 4× SessionStart hook entries | `~/.claude/settings.json` → `hooks.SessionStart[]` | merged |
| Gate script | `~/.claude/hooks/cbm-code-discovery-gate` | created, `chmod 755` |
| Reminder script | `~/.claude/hooks/cbm-session-reminder` | created, `chmod 755` |

The installer uses yyjson field-surgical upserts, so unrelated keys in
`settings.json` / `.mcp.json` / `.claude.json` are preserved. Re-installs are
idempotent (entries matched by `matcher` string).

Note: the README says "4 Skills" but the current binary ships a single
consolidated skill. The code removes the old 4 (`codebase-memory-exploring`,
`codebase-memory-tracing`, `codebase-memory-quality`, `codebase-memory-cypher`)
and the older monolithic name `codebase-memory-mcp` during install.

---

## 1. MCP server entry

**Written to both `~/.claude/.mcp.json` and `~/.claude.json`** under the
`mcpServers` key:

```json
{
  "mcpServers": {
    "codebase-memory-mcp": {
      "command": "/Users/martinkuek/.local/bin/codebase-memory-mcp"
    }
  }
}
```

No `args`, no `env`. The binary reads stdin as JSON-RPC and writes stdout.

**You already have this** — added earlier via `claude mcp add -s user` into
`~/.claude.json` only. The installer would additionally write
`~/.claude/.mcp.json` (separate global location) which is currently absent.
Both work; having only one is cleaner.

---

## 2. PreToolUse hook — the "first-call Grep block"

**Settings delta** in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Grep|Glob|Read|Search",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/cbm-code-discovery-gate"
          }
        ]
      }
    ]
  }
}
```

The `matcher` is a `|`-separated Claude Code tool-name regex. Note the
`Search` token — that's not a real Claude Code tool name, so it's a dead
match. Effective matchers are `Grep`, `Glob`, `Read`.

**Script contents** at `~/.claude/hooks/cbm-code-discovery-gate`:

```bash
#!/bin/bash
# Gate hook: nudges Claude toward codebase-memory-mcp for code discovery.
# First Grep/Glob/Read/Search per session -> block. Subsequent -> allow.
# PPID = Claude Code process PID, unique per session.
GATE=/tmp/cbm-code-discovery-gate-$PPID
find /tmp -name 'cbm-code-discovery-gate-*' -mtime +1 -delete 2>/dev/null
if [ -f "$GATE" ]; then
    exit 0
fi
touch "$GATE"
echo 'BLOCKED: For code discovery, use codebase-memory-mcp tools first: search_graph(name_pattern) to find functions/classes, trace_path() for call chains, get_code_snippet(qualified_name) to read source. If the graph is not indexed yet, call index_repository first. Fall back to Grep/Glob/Read only for text content search. If you need Grep, retry.' >&2
exit 2
```

**Behaviour:**
- First Grep/Glob/Read in a session → exit 2 (blocks the tool call, nudge shown to agent), marker file created.
- Every subsequent call in the same session → exit 0 (passes through).
- Session identity = `$PPID` (Claude Code process). New session = new block.
- Old marker files (>24h) garbage-collected on each run.

**Claude Code hook contract:** `exit 2` = deny the tool call and feed stderr
back to the model as context. `exit 0` = allow. No JSON stdout needed —
stderr is the nudge channel.

**Known weaknesses of this hook design:**
- `$PPID` can be unstable in some shell chains — if the PPID resolution drifts, the marker misses and the block fires twice.
- The `find /tmp -name ... -delete` runs on every tool call — cheap but not free. On a slow /tmp this adds latency per Grep/Glob/Read.
- No awareness of whether a project is actually indexed. If you run `claude` in a fresh, unindexed repo, the first block still fires and tells you to `index_repository` first.
- The `Search` token in the matcher is a bug — it matches no real tool.

---

## 3. SessionStart hooks — 4× "code discovery protocol" reminders

**Settings delta** in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup", "hooks": [{ "type": "command", "command": "~/.claude/hooks/cbm-session-reminder" }] },
      { "matcher": "resume",  "hooks": [{ "type": "command", "command": "~/.claude/hooks/cbm-session-reminder" }] },
      { "matcher": "clear",   "hooks": [{ "type": "command", "command": "~/.claude/hooks/cbm-session-reminder" }] },
      { "matcher": "compact", "hooks": [{ "type": "command", "command": "~/.claude/hooks/cbm-session-reminder" }] }
    ]
  }
}
```

Four separate entries, one per SessionStart event type. Same script, same
command. SessionStart fires on `startup`, `resume`, `clear`, and `compact`
— meaning this reminder lands in context on every `/clear`, every auto-compact,
every session start, and every resume.

**Script contents** at `~/.claude/hooks/cbm-session-reminder`:

```bash
#!/bin/bash
# SessionStart hook: remind agent to use codebase-memory-mcp tools.
# Installed by codebase-memory-mcp. Fires on startup/resume/clear/compact.
cat << 'REMINDER'
CRITICAL - Code Discovery Protocol:
1. ALWAYS use codebase-memory-mcp tools FIRST for ANY code exploration:
   - search_graph(name_pattern/label/qn_pattern) to find functions/classes/routes
   - trace_path(function_name, mode=calls|data_flow|cross_service) for call chains
   - get_code_snippet(qualified_name) to read source (NOT Read/cat)
   - query_graph(query) for complex Cypher patterns
   - get_architecture(aspects) for project structure
   - search_code(pattern) for text search (graph-augmented grep)
2. Fall back to Grep/Glob/Read ONLY for text content, config values, non-code files.
3. If a project is not indexed yet, run index_repository FIRST.
REMINDER
```

**Behaviour:** Stdout from a SessionStart hook is injected into the agent's
context. Every session reset adds ~15 lines of imperative protocol to the
opening state.

**Cost:** ~120 tokens × 4 event types × every session reset. For sessions
that never touch code exploration (memory consolidation, doc writing,
chat), this is dead weight.

---

## 4. Skill file

**Written to** `~/.claude/skills/codebase-memory/SKILL.md`:

```markdown
---
name: codebase-memory
description: Use the codebase knowledge graph for structural code queries. Triggers on: explore the codebase, understand the architecture, what functions exist, show me the structure, who calls this function, what does X call, trace the call chain, find callers of, show dependencies, impact analysis, dead code, unused functions, high fan-out, refactor candidates, code quality audit, graph query syntax, Cypher query examples, edge types, how to use search_graph.
---

# Codebase Memory — Knowledge Graph Tools

Graph tools return precise structural results in ~500 tokens vs ~80K for grep.

## Quick Decision Matrix

| Question | Tool call |
|----------|----------|
| Who calls X? | `trace_path(direction="inbound")` |
| What does X call? | `trace_path(direction="outbound")` |
| Full call context | `trace_path(direction="both")` |
| Find by name pattern | `search_graph(name_pattern="...")` |
| Dead code | `search_graph(max_degree=0, exclude_entry_points=true)` |
| Cross-service edges | `query_graph` with Cypher |
| Impact of local changes | `detect_changes()` |
| Risk-classified trace | `trace_path(risk_labels=true)` |
| Text search | `search_code` or Grep |

## Exploration Workflow
1. `list_projects` — check if project is indexed
2. `get_graph_schema` — understand node/edge types
3. `search_graph(label="Function", name_pattern=".*Pattern.*")` — find code
4. `get_code_snippet(qualified_name="project.path.FuncName")` — read source

## Tracing Workflow
1. `search_graph(name_pattern=".*FuncName.*")` — discover exact name
2. `trace_path(function_name="FuncName", direction="both", depth=3)` — trace
3. `detect_changes()` — map git diff to affected symbols

## Quality Analysis
- Dead code: `search_graph(max_degree=0, exclude_entry_points=true)`
- High fan-out: `search_graph(min_degree=10, relationship="CALLS", direction="outbound")`
- High fan-in: `search_graph(min_degree=10, relationship="CALLS", direction="inbound")`

## 14 MCP Tools
`index_repository`, `index_status`, `list_projects`, `delete_project`,
`search_graph`, `search_code`, `trace_path`, `detect_changes`,
`query_graph`, `get_graph_schema`, `get_code_snippet`, `get_architecture`,
`manage_adr`, `ingest_traces`

## Edge Types
CALLS, HTTP_CALLS, ASYNC_CALLS, IMPORTS, DEFINES, DEFINES_METHOD,
HANDLES, IMPLEMENTS, OVERRIDE, USAGE, FILE_CHANGES_WITH,
CONTAINS_FILE, CONTAINS_FOLDER, CONTAINS_PACKAGE

## Cypher Examples (for query_graph)
```
MATCH (a)-[r:HTTP_CALLS]->(b) RETURN a.name, b.name, r.url_path, r.confidence LIMIT 20
MATCH (f:Function) WHERE f.name =~ '.*Handler.*' RETURN f.name, f.file_path
MATCH (a)-[r:CALLS]->(b) WHERE a.name = 'main' RETURN b.name
```

## Gotchas
1. `search_graph(relationship="HTTP_CALLS")` filters nodes by degree — use `query_graph` with Cypher to see actual edges.
2. `query_graph` has a 200-row cap — use `search_graph` with degree filters for counting.
3. `trace_path` needs exact names — use `search_graph(name_pattern=...)` first.
4. `direction="outbound"` misses cross-service callers — use `direction="both"`.
5. Results default to 10 per page — check `has_more` and use `offset`.
```

**Discrepancies to flag:**
- Skill references `trace_path` with `mode=calls|data_flow|cross_service` in the session reminder but `trace_path(direction=...)` in the skill. The README also shows `trace_call_path` as the tool name. The actual MCP tool name needs verification against the live server. Before wiring this into a launcher module, run `get_graph_schema` or inspect the server's tool manifest to confirm.
- Skill tool list (14) matches README. Session reminder mentions `search_code` and `get_architecture` — both present.

---

## 5. Full resulting `~/.claude/settings.json` shape

If you had nothing in `hooks` before the install, the file ends up with:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Grep|Glob|Read|Search",
        "hooks": [
          { "type": "command", "command": "~/.claude/hooks/cbm-code-discovery-gate" }
        ]
      }
    ],
    "SessionStart": [
      { "matcher": "startup", "hooks": [{ "type": "command", "command": "~/.claude/hooks/cbm-session-reminder" }] },
      { "matcher": "resume",  "hooks": [{ "type": "command", "command": "~/.claude/hooks/cbm-session-reminder" }] },
      { "matcher": "clear",   "hooks": [{ "type": "command", "command": "~/.claude/hooks/cbm-session-reminder" }] },
      { "matcher": "compact", "hooks": [{ "type": "command", "command": "~/.claude/hooks/cbm-session-reminder" }] }
    ]
  }
}
```

Plus existing keys (`permissions`, `model`, `enabledPlugins`, `env`, etc.)
preserved untouched.

---

## Customisation menu — pick-and-choose

| Component | Keep? | Notes |
|---|---|---|
| MCP entry | **yes** (already installed) | core of the integration |
| Skill file | **probably** | Cheap reference material. Fix the `trace_path` discrepancy first. |
| PreToolUse gate script | **conditional** | Useful for repos that ARE indexed. Should check indexed-state before blocking. Bug: the `Search` matcher token does nothing. |
| PreToolUse entry in settings | **conditional** | Ties to the script above. |
| SessionStart reminder script | **conditional** | Useful for code-exploration sessions. Dead weight for doc/memory sessions. Consider firing only on explicit opt-in. |
| SessionStart × 4 entries | **reduce** | `startup` alone is probably enough. `clear` and `compact` are noisy — they fire on every context reset. |

---

## Launcher integration sketch

The launcher already provisions a system prompt via modules. A `cbm`
module could follow the same pattern:

```
launcher/modules/cbm/
├── module.py              # check_dependencies, build_tui_section, build_prompt
├── prompts/
│   ├── code-discovery.md  # optional: inject a slim version of the protocol
│   └── skill-summary.md   # optional: inject the decision matrix
└── hooks/
    ├── gate.sh            # improved gate: checks index state, fixes $PPID drift
    └── reminder.sh        # improved reminder: shorter, fires only on startup
```

TUI section presents a checkbox: "Enable code discovery nudges (cbm)".
When enabled:
1. `build_prompt` contributes `prompts/code-discovery.md` to the system prompt.
2. The module writes `hooks/gate.sh` to a session-scoped path and emits a
   `--append-settings` merge that points `PreToolUse` at it. (Requires
   extending the launcher to merge hooks, not just system prompt.)
3. Or — simpler — the module skips hooks entirely and relies on the
   injected system prompt to nudge the agent. This is what your existing
   memory module does, and it may be all you need.

The session reminder is redundant with a prompt-injection approach — the
launcher already injects the module's prompt fragment at session start.
A dedicated SessionStart hook duplicates that channel.

The gate hook is the only piece that can't be replaced by a prompt
fragment: it physically blocks the first Grep/Glob/Read. If you want
that behaviour, the hook is the only path. If you trust the agent to
respond to a prompt-level nudge, skip the hook.

---

## Extraction pointers

If you want the exact source:
- Hook matcher constant: `CMM_HOOK_MATCHER` @ `src/cli/cli.c:1461`
- Gate script generator: `cbm_install_hook_gate_script()` @ `src/cli/cli.c:1641`
- Reminder script generator: `cbm_install_session_reminder_script()` @ `src/cli/cli.c:1685`
- SessionStart matcher list: `cbm_upsert_session_hooks()` @ `src/cli/cli.c:1725`
- Skill content: `skill_content[]` @ `src/cli/cli.c:396`
- Install orchestrator: `install_claude_code_config()` @ `src/cli/cli.c:2621`
