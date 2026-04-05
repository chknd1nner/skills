# OpenCode Review Hook Setup

The OpenCode review hook (`intercept-review-agents.py`) intercepts review-type Agent calls from Claude Code and dispatches them to OpenCode Server asynchronously. Reviews run in the background while Claude continues working, with results delivered via file handshake.

## Prerequisites

1. **OpenCode installed** and on your PATH. Verify with `opencode --version`.
2. **OpenCode authenticated** via GitHub Copilot. Run `opencode auth` if needed. The hook starts OpenCode Server on demand, so you don't need to run `opencode serve` manually.
3. **The hook file** at `.claude/hooks/intercept-review-agents.py` (already installed in this repo).
4. **The hook registered** in `.claude/settings.json` under `PreToolUse` with matcher `Agent` (already configured in this repo).

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENCODE_PORT` | No | `4096` | Port for OpenCode Server |
| `OPENCODE_MODEL` | No | (server default) | Model ID for reviews, e.g. `gemini-2.5-pro` |
| `OPENCODE_TIMEOUT` | No | `1800` | Timeout in seconds for the background POST |
| `OPENCODE_STARTUP_TIMEOUT` | No | `10` | Seconds to wait for server to become healthy |
| `OPENCODE_SERVER_PASSWORD` | No | (none) | Bearer token if OpenCode requires auth |
| `OPENCODE_DEBUG` | No | `0` | Set to `1` for verbose logging |
| `OPENCODE_LOG_FILE` | No | `/tmp/opencode-hook-debug.log` | Where debug and error logs are written |
| `OPENCODE_SKIP_POLLER` | No | `0` | Test-only: suppresses background process |

For most setups, you only need `OPENCODE_PORT` (if not using the default 4096) and optionally `OPENCODE_MODEL` to target a specific model from the GHCP catalog.

## Configuration Methods

### Method 1: Shell environment (simplest)

Export variables before launching Claude Code. Good for quick testing or one-off sessions.

```bash
export OPENCODE_PORT=4096
export OPENCODE_MODEL=gemini-2.5-pro
claude
```

Or inline:

```bash
OPENCODE_MODEL=gemini-2.5-pro claude
```

Variables set this way last for the duration of the shell session. They're inherited by Claude Code and passed through to the hook subprocess.

### Method 2: Top-level `env` in settings.json (recommended for per-project config)

Claude Code supports a top-level `env` object in `.claude/settings.json`. Variables set here are available to all hooks in the project.

```json
{
  "env": {
    "OPENCODE_PORT": "4096",
    "OPENCODE_MODEL": "gemini-2.5-pro"
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/intercept-review-agents.py"
          }
        ]
      }
    ]
  }
}
```

This is the recommended approach for project-level configuration. The settings file is checked into the repo, so the configuration travels with the project. Use `.claude/settings.local.json` (gitignored) for values you don't want committed, like `OPENCODE_SERVER_PASSWORD`.

### Method 3: SessionStart hook with CLAUDE_ENV_FILE (dynamic)

For configuration that depends on runtime conditions (e.g. detecting whether OpenCode is installed), use a SessionStart hook that writes to `CLAUDE_ENV_FILE`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "if command -v opencode >/dev/null 2>&1; then echo 'export OPENCODE_MODEL=gemini-2.5-pro' >> \"$CLAUDE_ENV_FILE\"; fi"
          }
        ]
      }
    ]
  }
}
```

Variables written to `CLAUDE_ENV_FILE` persist for the entire Claude Code session and are available to all subsequent hooks and Bash commands.

## Verifying the Setup

### 1. Check OpenCode is reachable

```bash
opencode serve --port 4096 &
curl -s http://127.0.0.1:4096/global/health | python3 -m json.tool
# Expected: {"healthy": true, "version": "..."}
```

### 2. Smoke test the hook

```bash
# Non-review call — should pass through silently (exit 0, no output)
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","description":"Find files","prompt":"test"},"cwd":"/tmp"}' | python3 .claude/hooks/intercept-review-agents.py
echo "Exit: $?"

# Review call with no server — should fall through gracefully
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

When Claude dispatches a review agent (e.g. `superpowers:code-reviewer`), the hook:

1. Detects the review call (bypass with `[BYPASS_HOOK]` prefix in description)
2. Ensures OpenCode Server is running (starts it on demand if needed)
3. Creates a session via `POST /session`
4. Writes a `.prompt` file and sets status to `PENDING`
5. Spawns a background process that sends the blocking POST and streams SSE progress
6. Returns a deny with instructions for Claude to check `.opencode/tasks/{id}.status`

Claude continues working. When it checks back and finds `COMPLETE`, it reads `.opencode/tasks/{id}.result.md` for the review content. If `FAILED`, it re-invokes the review with `[BYPASS_HOOK]` to fall back to a Claude agent.

## Troubleshooting

**Hook falls through silently (review runs as Claude agent):**
Check that OpenCode is installed (`which opencode`), authenticated (`opencode auth`), and the port isn't already in use. Enable debug logging to see what's happening.

**"server startup failed" on stderr:**
OpenCode couldn't start. Check `OPENCODE_LOG_FILE` for details. Common causes: not authenticated, port in use, binary not on PATH.

**Review takes too long:**
Increase `OPENCODE_TIMEOUT` (default 300s). Some models with extensive tool use can take several minutes.

**Want to skip the hook temporarily:**
Prefix the agent's description with `[BYPASS_HOOK]` — the hook passes through immediately.
