# OpenCode Router Hook Setup

The OpenCode router hook (`intercept-review-agents.py`) intercepts Agent calls from Claude Code and dispatches them to OpenCode Server asynchronously. Routes are configured via a TOML file that maps agent types to OpenCode agents with optional model overrides. Results are delivered via file handshake.

## Prerequisites

1. **OpenCode installed** and on your PATH. Verify with `opencode --version`.
2. **OpenCode authenticated** via GitHub Copilot. Run `opencode auth` if needed. The hook starts OpenCode Server on demand, so you don't need to run `opencode serve` manually.
3. **The hook file** at `.claude/hooks/intercept-review-agents.py` (already installed in this repo).
4. **The hook registered** in `.claude/settings.json` under `PreToolUse` with matcher `Agent` (already configured in this repo).
5. **The router config** at `.claude/hooks/opencode-router.toml` (already configured in this repo).

## Configuration

### Router Config (`.claude/hooks/opencode-router.toml`)

This is the primary configuration surface. It defines **profiles** (what to dispatch to) and **routes** (when to dispatch).

```toml
version = 1

[defaults]
startup_timeout_seconds = 10

[profiles.review_gpt54]
agent = "code-reviewer"
provider = "poe"
model = "openai/gpt-5.4"
timeout_seconds = 1200

[profiles.implementor_sonnet]
agent = "implementor"
provider = "poe"
model = "anthropic/claude-sonnet-4.6"
timeout_seconds = 3600

[[routes]]
name = "superpowers-review"
enabled = true
match_subagent = "superpowers:code-reviewer"
profile = "review_gpt54"

[[routes]]
name = "general-review-prefix"
enabled = true
match_subagent = "general-purpose"
match_description_prefix = "review"
profile = "review_gpt54"
```

### Profiles

A profile defines where and how to dispatch:

| Field | Required | Description |
|---|---|---|
| `agent` | Yes | OpenCode agent name (must match an agent defined in your OpenCode config) |
| `provider` | No* | Provider ID (e.g. `poe`) |
| `model` | No* | Model ID (e.g. `openai/gpt-5.4`) |
| `timeout_seconds` | No | Request timeout (default: 1800) |

*`provider` and `model` are optional as a pair — if either is set, both are required. When omitted, the OpenCode agent's default model applies.

**Why `agent` vs `provider`/`model`?** The `agent` field selects which OpenCode agent handles the task — this determines system prompt, tools, and behavior. The `provider`/`model` fields are optional overrides for experimentation (e.g., testing a new model with an existing agent). For stable setups, configure the model in OpenCode's agent definition and leave `provider`/`model` out of the hook TOML.

### Routes

Routes are evaluated in declared order. First match wins.

| Field | Required | Description |
|---|---|---|
| `match_subagent` | Yes | Exact match on Claude's `subagent_type` |
| `match_description_prefix` | No | Case-insensitive prefix match on the agent description |
| `profile` | Yes | Which profile to use |
| `enabled` | No | Set to `false` to disable (default: `true`) |
| `name` | No | Human-readable label for logging |

Every route must have `match_subagent` — this prevents accidental catch-all routes.

### Example: Reviewer + Implementor Split

Route code reviews to GPT-5.4 for a second opinion, and implementation tasks to Sonnet for fast execution:

```toml
version = 1

[defaults]
startup_timeout_seconds = 10

[profiles.reviewer]
agent = "code-reviewer"
provider = "poe"
model = "openai/gpt-5.4"
timeout_seconds = 1200

[profiles.implementor]
agent = "implementor"
provider = "poe"
model = "anthropic/claude-sonnet-4.6"
timeout_seconds = 3600

[[routes]]
name = "superpowers-review"
enabled = true
match_subagent = "superpowers:code-reviewer"
profile = "reviewer"

[[routes]]
name = "general-review"
enabled = true
match_subagent = "general-purpose"
match_description_prefix = "review"
profile = "reviewer"

[[routes]]
name = "codex-rescue"
enabled = true
match_subagent = "codex:codex-rescue"
profile = "implementor"
```

### Environment Variables

Env vars serve as operational overrides — they take precedence over TOML values when set.

| Variable | Default | Purpose |
|---|---|---|
| `OPENCODE_PORT` | (auto-selected) | Force-override port (skips auto-selection) |
| `OPENCODE_STARTUP_TIMEOUT` | TOML default or `10` | Override startup timeout |
| `OPENCODE_TIMEOUT` | Profile or `1800` | Override request timeout |
| `OPENCODE_SERVER_PASSWORD` | (none) | Bearer token if OpenCode requires auth |
| `OPENCODE_DEBUG` | `0` | Set to `1` for verbose logging |
| `OPENCODE_LOG_FILE` | `/tmp/opencode-hook-debug.log` | Where debug and error logs are written |
| `OPENCODE_SKIP_POLLER` | `0` | Test-only: suppresses background process |

For most setups, the TOML config is sufficient. Env vars are for temporary overrides or CI environments.

**Port auto-selection:** When `OPENCODE_PORT` is not set, the hook automatically selects a free port for each project and writes it to `.opencode/server.port`. The server persists across sessions — subsequent invocations reuse the same port via the file.

## Verifying the Setup

### 1. Check OpenCode is reachable

```bash
opencode serve --port 4096 &
curl -s http://127.0.0.1:4096/global/health | python3 -m json.tool
# Expected: {"healthy": true, "version": "..."}
```

### 2. Smoke test the hook

```bash
# Non-matching route — should pass through silently (exit 0, no output)
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","description":"Find files","prompt":"test"},"cwd":"/tmp"}' | python3 .claude/hooks/intercept-review-agents.py
echo "Exit: $?"

# Matching route with no server — should fall through gracefully
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"superpowers:code-reviewer","description":"Review","prompt":"test"},"cwd":"/tmp"}' | OPENCODE_PORT=19999 OPENCODE_STARTUP_TIMEOUT=1 python3 .claude/hooks/intercept-review-agents.py
echo "Exit: $?"
```

### 3. Enable debug logging

Set `OPENCODE_DEBUG=1` to see what the hook is doing. Logs go to `OPENCODE_LOG_FILE` (default: `/tmp/opencode-hook-debug.log`).

```bash
OPENCODE_DEBUG=1 OPENCODE_LOG_FILE=/tmp/hook.log claude
# After triggering a review, check:
cat /tmp/hook.log
```

## How It Works

When Claude dispatches an agent call, the hook:

1. Checks for `[BYPASS_HOOK]` prefix in description — passes through immediately if found
2. Loads the TOML config — passes through if missing or invalid
3. Evaluates routes in order — passes through if no route matches
4. Ensures OpenCode Server is running (starts it on demand if needed)
5. Creates a session via `POST /session`
6. Writes a `.prompt` file and sets status to `PENDING`
7. Spawns a background process that sends the blocking POST with `agent` and optional `model`
8. Returns a deny with instructions for Claude to check `.opencode/tasks/{id}.status`

Claude continues working. When it checks back and finds `COMPLETE`, it reads `.opencode/tasks/{id}.result.md` for the result. If `FAILED`, it re-invokes with `[BYPASS_HOOK]` to fall back to a Claude agent.

## Troubleshooting

**Hook falls through silently (agent runs as Claude subagent):**
Check that: (1) the TOML config exists and is valid, (2) a route matches the subagent type, (3) OpenCode is installed and authenticated, (4) the port isn't already in use. Enable debug logging to see what's happening.

**"server startup failed" on stderr:**
OpenCode couldn't start. Check `OPENCODE_LOG_FILE` for details. Common causes: not authenticated, port in use, binary not on PATH.

**"config error" on stderr:**
The TOML config has a validation problem. Check the error message — common causes: profile missing `agent`, route missing `match_subagent` or `profile`, provider/model set individually instead of as a pair.

**Task takes too long:**
Increase `timeout_seconds` in the profile or set `OPENCODE_TIMEOUT` env var. Some models with extensive tool use can take 30+ minutes.

**Want to skip the hook temporarily:**
Prefix the agent's description with `[BYPASS_HOOK]` — the hook passes through immediately.
