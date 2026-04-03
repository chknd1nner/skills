# OpenCode Async Bridge — Design Spec

> **Last updated:** 2026-04-03
> This is a living document. If source code were lost, this spec should be sufficient to recreate it.

## Overview

A next-generation review interceptor hook that replaces the v1 synchronous Gemini CLI approach with an asynchronous, HTTP-native architecture built on OpenCode Server. Reviews are dispatched via OpenCode's REST API and run in the background while the main Claude session continues working. Results are delivered via file-based handshake.

The mechanism remains entirely hook-based. No superpowers skill files are modified.

---

## Problem

The v1 Gemini review hook works but blocks the main Claude session for 60–120 seconds per review. This is dead time — Claude can't do anything else while waiting for Gemini CLI to finish. Additionally, the v1 approach is locked to Gemini as the only review backend. OpenCode Server, authenticated via GHCP OAuth, provides access to multiple models and exposes a REST API that enables asynchronous dispatch.

---

## Approach

A `PreToolUse` hook fires on every `Agent` tool call. Detection logic is identical to v1. When a review call is detected, the hook dispatches the review to OpenCode Server via HTTP, spawns a background poller process, and returns a deny immediately (under 1 second). The poller monitors OpenCode's message API and writes the result to a file when complete. Claude reads the file at a natural breakpoint and continues the workflow.

If OpenCode is unavailable or fails, the hook falls through and the original Claude Agent call proceeds.

---

## Architecture

Four components, all Python 3 stdlib (no pip dependencies):

### 1. The Hook (`intercept-review-agents.py`)

Same entry point and detection logic as v1. Instead of shelling out to `gemini`, it dispatches to OpenCode Server via `urllib.request` and returns immediately. The hook file contains all logic — server management, dispatch, and poller — invoked differently based on argv.

- Normal invocation (from Claude Code): detect, dispatch, return deny
- `--poll {session_id} {task_id} {port} {cwd}`: poller mode, called as a subprocess

### 2. The Server Manager

Functions within the hook that handle on-demand OpenCode Server startup. The server is a long-running process that persists across hook invocations — startup cost is paid once per working session.

### 3. The Background Poller

A detached subprocess of the hook (same file, `--poll` flag) that monitors `GET /session/{id}/message` until the review result appears, then writes it to the handshake files.

### 4. The Result Files

File-based handshake mechanism under `.opencode/tasks/` in the project root:
- `{task_id}.status` — `PENDING`, `COMPLETE`, or `FAILED`
- `{task_id}.result.md` — the review content (written by poller on completion)

---

## Detection

Identical to v1, with one addition — the bypass flag:

| Pattern | Behaviour |
|---|---|
| `description.startswith('[BYPASS_HOOK]')` | **Pass through immediately** — bypass flag from a retry after failure |
| `subagent_type == "superpowers:code-reviewer"` | Intercept |
| `subagent_type == "general-purpose"` AND `description.lower().startswith("review")` | Intercept |
| Everything else | Pass through |

The bypass check is the very first thing in the hook, before detection or server checks.

---

## Server Lifecycle Management

### Discovery

On each invocation, the hook tries `GET http://127.0.0.1:{port}/` as a health check. If it gets a response, the server is ready. Port is configurable via `OPENCODE_PORT` (default `4096`).

### On-Demand Startup

If the health check fails (connection refused), the hook starts OpenCode:

```python
proc = subprocess.Popen(
    ['opencode', 'serve', '--port', str(port)],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    start_new_session=True,
)
```

Then polls in a tight loop (every 0.5s, up to `OPENCODE_STARTUP_TIMEOUT` seconds):

- **Process died?** (`proc.poll() is not None`) — read stderr, surface the error to Claude via the deny reason, fall through to Claude Agent. This catches auth failures, port conflicts, missing binary, and config errors immediately.
- **Health check passes?** — server is ready, proceed with dispatch.
- **Timeout without health or exit?** — fall through with a generic "server didn't become healthy" message.

### Fail Fast

The early-exit detection is critical. If OpenCode can't start (e.g., not authenticated via `opencode auth`), the user sees the error message immediately through Claude rather than waiting for a silent 10-second timeout:

> *"OpenCode Server failed to start: `Not authenticated. Run 'opencode auth' to log in.` Falling back to Claude agent."*

### Persistence

The server outlives the hook invocation. No shutdown logic — it runs until the user kills it or the machine sleeps. Subsequent reviews reuse the same server instance.

### Auth Assumption

OpenCode is pre-authenticated via GHCP OAuth (`opencode auth` done once). The hook doesn't manage credentials. If `OPENCODE_SERVER_PASSWORD` is set, the hook includes it in HTTP requests.

---

## Dispatch Flow

Once the server is healthy, three steps:

### 1. Create Session

`POST /session` with `{ "title": "review-{task_id}" }`. Returns a session object with an ID. The task ID is generated by the hook — a short UUID.

### 2. Send Prompt Async

`POST /session/{id}/prompt_async` with the review prompt as a text part:

```json
{
  "parts": [{ "type": "text", "text": "<review prompt>" }]
}
```

Returns `204` immediately. The review is now running inside OpenCode.

If `OPENCODE_MODEL` is set, it's included in the request body as `"model"`.

### 3. Spawn Poller

The hook launches itself as a detached subprocess in poller mode:

```python
subprocess.Popen(
    [sys.executable, __file__, '--poll', session_id, task_id, str(port), cwd],
    start_new_session=True,
    stdout=subprocess.DEVNULL,
    stderr=open(log_file, 'a') if debug else subprocess.DEVNULL,
)
```

The `cwd` argument is passed so the poller knows where to write `.opencode/tasks/` files.

### 4. Return Deny

The hook creates `.opencode/tasks/` if needed, writes `{task_id}.status` → `PENDING`, then prints the deny JSON and exits.

**Total hook runtime: under 1 second.**

---

## Deny Reasons

### Successful dispatch (async)

```
A PreToolUse hook dispatched this review to OpenCode Server (async). The review
is running in the background. When you're ready for the result, read
`.opencode/tasks/{task_id}.status`. When it says COMPLETE, read
`.opencode/tasks/{task_id}.result.md` and continue the workflow as normal.
If it says FAILED, re-invoke the original agent call with [BYPASS_HOOK]
prepended to the description field — the hook will let it through to the
Claude agent this time.
```

### Server startup failure

On startup failure, the hook exits 0 with no output — the original Agent call proceeds (Claude subagent handles the review). The error is logged to `OPENCODE_LOG_FILE` when debug is enabled, and written to stderr. Example error:

```
OpenCode Server failed to start: Not authenticated. Run 'opencode auth' to log in.
Falling back to Claude agent.
```

---

## Background Poller

### Loop

Every `OPENCODE_POLL_INTERVAL` seconds (default 3), hit `GET /session/{session_id}/message`. Parse the JSON response — an array of `{ info, parts }` objects. Look for an assistant message (the model's reply). If found, extract the text content from the parts.

### Write Result

Write extracted text to `.opencode/tasks/{task_id}.result.md`. Update `.opencode/tasks/{task_id}.status` → `COMPLETE`. Exit.

### Timeout

Controlled by `OPENCODE_TIMEOUT` (default 300s). Reviews can run longer than v1's 120s since the main session isn't blocked. If the timeout fires before a result appears, write `FAILED` to the status file and exit.

### Error Handling

If any HTTP request fails (server crashed, network error), write `FAILED` to the status file and exit. No retry loop — if OpenCode died mid-review, there's nothing to retry against.

### Cleanup

The poller doesn't delete anything. Result files accumulate in `.opencode/tasks/`. They're small text files and serve as an audit trail. The directory should be gitignored.

### Logging

When `OPENCODE_DEBUG=1`, the poller appends to `OPENCODE_LOG_FILE`. Each poll cycle logs the HTTP status and whether a result was found.

---

## Result Delivery to Claude

### How Claude Handles the Async Result

Claude reads the deny reason, understands the review is in-flight, and continues with other work in the superpowers workflow. At a natural breakpoint, it reads the status file. If COMPLETE, it reads the result file and incorporates the review. If FAILED, it retries the original Agent call with `[BYPASS_HOOK]` in the description, which the hook passes through to the Claude subagent.

### The Bypass Mechanism

When a review fails (timeout, server crash, HTTP error), the deny reason instructs Claude to retry with `[BYPASS_HOOK]` prepended to the description field. The hook checks for this marker before any other logic:

```python
if description.startswith('[BYPASS_HOOK]'):
    log('bypass flag detected, passing through')
    sys.exit(0)
```

This ensures a review always happens — either via OpenCode or via the original Claude Agent fallback.

### Timing Hint

The deny reason includes a nudge: *"The review typically takes 30–60 seconds. Continue with your current work and check back after completing your next task."* This guides Claude toward productive async behaviour.

### Escape Hatch

If Claude's async behaviour proves unreliable in practice, `OPENCODE_ASYNC=0` could make the hook poll internally and return synchronously (like v1 but via HTTP instead of CLI). This is not implemented in v2 — noted as a future option if needed.

---

## Configuration

Environment variables, settable in `settings.local.json` under `"env"`:

| Variable | Default | Description |
|---|---|---|
| `OPENCODE_PORT` | `4096` | Port for OpenCode Server |
| `OPENCODE_TIMEOUT` | `300` | Seconds before poller writes FAILED |
| `OPENCODE_STARTUP_TIMEOUT` | `10` | Seconds to wait for server health on startup |
| `OPENCODE_POLL_INTERVAL` | `3` | Seconds between polling attempts |
| `OPENCODE_DEBUG` | `0` | Enable debug logging |
| `OPENCODE_LOG_FILE` | `/tmp/opencode-hook-debug.log` | Log file path |
| `OPENCODE_MODEL` | *(none)* | Override model for reviews (passed to OpenCode prompt API) |
| `OPENCODE_SERVER_PASSWORD` | *(none)* | Auth password if configured |

---

## Extensibility

The detection logic is hardcoded for reviews only in v2. The dispatch function is cleanly separated — it takes a prompt and returns a task ID. Adding a config file that maps `subagent_type` patterns to different backends/models would slot in at the detection layer without touching dispatch or polling. The architecture supports this without structural changes.

---

## File Layout

```
.claude/hooks/
  intercept-review-agents.py      # v2 — replaces v1 in-place
  gemini-review-policy.toml       # retained from v1, unused by v2
  archive/
    intercept-review-agents.sh     # v1 bash (already archived)
    intercept-review-agents-v1.py  # v1 python, archived when v2 ships

.opencode/tasks/                   # gitignored, created on first dispatch
  {task_id}.status                 # PENDING | COMPLETE | FAILED
  {task_id}.result.md              # review content
```

---

## Settings Configuration

Same hook registration as v1 — no changes needed:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "<absolute-path-to-project>/.claude/hooks/intercept-review-agents.py"
          }
        ]
      }
    ]
  }
}
```

---

## Test Suite

pytest, using a fake OpenCode server fixture.

### Fake OpenCode Server

A `fake_opencode` pytest fixture that spins up a minimal `http.server` on a random port with configurable responses per endpoint. Accepts a `delay` parameter to simulate realistic timing — slow startup (2–3s), review processing time (5–10s for the message endpoint to return a result), and timeouts (delay exceeding the configured limit). This ensures the polling loop actually loops and the timeout path actually fires.

### Test Groups

| Group | Tests | What's Covered |
|---|---|---|
| Detection | ~7 | Pass-through cases, both interception patterns, bypass flag, case-insensitivity |
| Server lifecycle | ~5 | Health check success, on-demand startup, startup failure with stderr capture, startup timeout, fail-fast on early exit |
| Dispatch | ~4 | Session creation, async prompt, poller subprocess spawned, deny JSON structure |
| Poller | ~5 | Result extraction from message API, status file transitions (PENDING → COMPLETE), timeout → FAILED, HTTP error → FAILED, realistic delays |
| Fallback | ~3 | OpenCode binary not found, server unreachable after startup, all paths fall through to Claude Agent |
| Bypass | ~2 | `[BYPASS_HOOK]` in description passes through, normal descriptions still intercepted |

### Integration Tests (Manual)

Not in the automated suite. Documented steps:
1. Start OpenCode Server manually
2. Trigger a superpowers review from Claude Code
3. Verify: hook dispatches, poller runs, result file appears, Claude reads it
4. Verify: kill OpenCode mid-review, confirm FAILED status and bypass retry

---

## Migration from v1

1. Archive `intercept-review-agents.py` to `archive/intercept-review-agents-v1.py`
2. Write new `intercept-review-agents.py` with v2 logic
3. Add `.opencode/` to `.gitignore`
4. No changes to `.claude/settings.json` — same hook path
5. Ensure `opencode` is on PATH and authenticated (`opencode auth`)

v1's `gemini-review-policy.toml` is retained but unused. It can be removed later or kept for reference.

---

## Out of Scope

- **SSE event-driven polling** — OpenCode exposes SSE events, but the event types beyond `server.connected` are not well-documented. Polling is sufficient and simpler. Can revisit if the event API matures.
- **OpenCode TypeScript SDK** — adds a Node.js dependency for marginal benefit. Raw HTTP via urllib is sufficient for the 3 endpoints we use.
- **Configurable routing by agent type** — architecture supports it, but v2 ships with reviews-only. Future work.
- **Synchronous fallback mode** (`OPENCODE_ASYNC=0`) — noted as an escape hatch if Claude's async behaviour is unreliable, but not implemented in v2.

---

## Implementation Notes — Verify During Build

These details are based on OpenCode's public documentation but need hands-on verification:

- **Health check endpoint:** Spec assumes `GET /` works. The OpenAPI spec is at `/doc` — may need to use that or another endpoint. Test empirically.
- **Message response shape:** The `info` field on each message presumably contains a role or type to distinguish user messages from assistant messages. Verify the exact field name and values.
- **Session ID field:** Session creation returns a session object — verify the field name for the ID (`id`, `sessionID`, etc.).
- **Auth header format:** If `OPENCODE_SERVER_PASSWORD` is set, verify whether it's Basic auth, Bearer token, or a custom header.
