# OpenCode Async Bridge — Design Spec

> **Last updated:** 2026-04-05
> This is a living document. If source code were lost, this spec should be sufficient to recreate it.

## Overview

A next-generation review interceptor hook that replaces the v1 synchronous Gemini CLI approach with an asynchronous, HTTP-native architecture built on OpenCode Server. Reviews are dispatched via OpenCode's REST API and run in the background while the main Claude session continues working. Results are delivered via file-based handshake.

The mechanism remains entirely hook-based. No superpowers skill files are modified.

---

## Problem

The v1 Gemini review hook works but blocks the main Claude session for 60–120 seconds per review. This is dead time — Claude can't do anything else while waiting for Gemini CLI to finish. Additionally, the v1 approach is locked to Gemini as the only review backend. OpenCode Server, authenticated via GHCP OAuth, provides access to multiple models and exposes a REST API that enables asynchronous dispatch.

---

## Approach

A `PreToolUse` hook fires on every `Agent` tool call. Detection logic is identical to v1. When a review call is detected, the hook dispatches the review to OpenCode Server via HTTP, spawns a background poller process, and returns a deny with `permissionDecision: "deny"` — all within under 1 second. The `permissionDecisionReason` field carries instructions back to the calling Claude session: what happened (review dispatched to OpenCode), where the result will appear (file paths), and what to do on failure (retry with bypass flag). This is the same return channel v1 used to deliver synchronous results, repurposed here to deliver async coordination instructions.

The background process sends a blocking POST to OpenCode and concurrently subscribes to OpenCode's SSE event stream, writing a real-time progress transcript as the agent works. When the POST returns, the final result is written to the handshake file. Claude reads the file at a natural breakpoint and continues the workflow.

If OpenCode is unavailable or fails, the hook falls through (exit 0, no output) and the original Claude Agent call proceeds.

---

## Architecture

Four components, all Python 3 stdlib (no pip dependencies):

### 1. The Hook (`intercept-review-agents.py`)

Same entry point and detection logic as v1. Instead of shelling out to `gemini`, it dispatches to OpenCode Server via `urllib.request` and returns immediately. The hook file contains all logic — server management, dispatch, and poller — invoked differently based on argv.

- Normal invocation (from Claude Code): detect, dispatch, return deny
- `--poll {session_id} {task_id} {port} {cwd}`: poller mode, called as a subprocess

### 2. The Server Manager

Functions within the hook that handle on-demand OpenCode Server startup. The server is a long-running process that persists across hook invocations — startup cost is paid once per working session.

### 3. The Background Process

A detached subprocess of the hook (same file, `--poll` flag) that does two things concurrently:

- **Main thread:** sends `POST /session/{id}/message` and blocks until OpenCode returns the completed response (`info.finish == "stop"`). Then writes the result to the handshake files.
- **SSE thread:** subscribes to `GET /global/event` and streams token deltas and tool call events to the progress transcript file. Terminates when the main thread exits.

### 4. The Result Files

File-based handshake mechanism under `.opencode/tasks/` in the project root:
- `{task_id}.status` — `PENDING`, `COMPLETE`, or `FAILED`
- `{task_id}.prompt` — the review prompt text (written by hook, read by poller as IPC)
- `{task_id}.result.md` — the review content (written when POST returns)
- `{task_id}.progress.md` — real-time transcript of agent work: token stream and tool calls (written continuously by SSE thread)

Status and result files are written atomically via temp file + `os.replace()`. Readers polling these files are guaranteed to see either the previous state or the new state, never partial content.

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

On each invocation, the hook resolves the port via `resolve_port(cwd)`: first checks `OPENCODE_PORT` env var (force override), then reads `.opencode/server.port` and health-checks that port, then auto-selects a free port by hashing the cwd into the ephemeral range (49152–65535). Health check is `GET http://127.0.0.1:{port}/global/health`, expecting `{"healthy": true}`.

### On-Demand Startup

If the health check fails (connection refused), the hook starts OpenCode:

```python
log_fh = open(log_file, 'a')
proc = subprocess.Popen(
    ['opencode', 'serve', '--port', str(port)],
    stdout=subprocess.DEVNULL,
    stderr=log_fh,
    start_new_session=True,
)
```

Server stderr is redirected to `OPENCODE_LOG_FILE` (not PIPE) to prevent deadlock — the server is a long-lived daemon that outlives the hook, and PIPE buffers would fill and block it. The log file captures both startup errors and ongoing server output.

Then polls in a tight loop (every 0.5s, up to `OPENCODE_STARTUP_TIMEOUT` seconds):

- **Process died?** (`proc.poll() is not None`) — read the tail of the log file for the error message. Log the failure, print a one-line warning to stderr, and fall through to Claude Agent. This catches auth failures, port conflicts, missing binary, and config errors immediately.
- **Health check passes?** — server is ready, proceed with dispatch.
- **Timeout without health or exit?** — fall through with a generic "server didn't become healthy" message.

### Fail Fast

The early-exit detection is critical. If OpenCode can't start (e.g., not authenticated via `opencode auth`), the hook detects this within milliseconds rather than waiting for a 10-second timeout. The hook falls through silently (exit 0, no output) so the review proceeds via Claude Agent, but **always** logs the error and prints a one-line warning to stderr — regardless of whether debug mode is enabled:

```
[stderr] OpenCode hook: server startup failed — Not authenticated. Run 'opencode auth' to log in. Falling back to Claude agent. Details: /tmp/opencode-hook-debug.log
```

The full error is captured in `OPENCODE_LOG_FILE` for inspection. Debug mode controls verbose per-request logging; startup failures are exceptional events that are always recorded.

### Persistence

The server outlives the hook invocation. No shutdown logic — it runs until the user kills it or the machine sleeps. Subsequent reviews reuse the same server instance.

### Auth Assumption

OpenCode is pre-authenticated via GHCP OAuth (`opencode auth` done once). The hook doesn't manage credentials. If `OPENCODE_SERVER_PASSWORD` is set, the hook includes it in HTTP requests.

---

## Dispatch Flow

Once the server is healthy, three steps:

### 1. Create Session

`POST /session` with `{}`. Returns a session object — the session ID is in the `id` field. The task ID is generated by the hook — a short UUID.

### 2. Spawn Background Process

The hook launches itself as a detached subprocess in poller mode, passing the session ID and task ID:

```python
subprocess.Popen(
    [sys.executable, __file__, '--poll', session_id, task_id, str(port), cwd],
    start_new_session=True,
    stdout=subprocess.DEVNULL,
    stderr=open(log_file, 'a') if debug else subprocess.DEVNULL,
)
```

The `cwd` argument is passed so the background process knows where to write `.opencode/tasks/` files. The background process immediately sends the blocking POST to OpenCode and subscribes to the SSE stream — see **Background Process** section.

### 3. Return Deny

The hook creates `.opencode/tasks/` if needed, writes `{task_id}.prompt` (the review prompt text for the poller to read) and `{task_id}.status` → `PENDING`, then prints the deny JSON and exits.

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

On startup failure, the hook exits 0 with no output — the original Agent call proceeds (Claude subagent handles the review). The error is **always** written to `OPENCODE_LOG_FILE` and a one-line summary is printed to stderr, regardless of debug mode. This ensures the user can always inspect why OpenCode handoff failed and fix it for next time.

```
[stderr] OpenCode hook: server startup failed — Not authenticated. Run 'opencode auth' to log in. Falling back to Claude agent. Details: /tmp/opencode-hook-debug.log
```

---

## Background Process

The background process runs two concurrent threads from the moment it starts.

### Main Thread: Blocking POST

Sends `POST /session/{session_id}/message` with the review prompt:

```json
{
  "parts": [{ "type": "text", "text": "<review prompt>" }]
}
```

If `OPENCODE_MODEL` is set, it's included as `"modelID"`.

This call blocks until OpenCode finishes — including all internal tool calls the agent makes. The response is a single `{ info, parts }` object representing the final assistant message. Completion is confirmed by `response["info"]["finish"] == "stop"`. No polling loop required.

The timeout for this call is `OPENCODE_TIMEOUT` (default 300s). If the call exceeds the timeout, write `FAILED` to the status file and exit.

### SSE Thread: Progress Transcript

Concurrently with the blocking POST, subscribes to `GET /global/event` (OpenCode's SSE stream) and writes a running transcript to `{task_id}.progress.md`, filtered to the active `sessionID`.

Two event types are captured:

- **`message.part.delta`** — raw token string in `properties.delta`. Appended directly to the transcript to form the streaming text as the model generates it.
- **`message.part.updated`** with `part.type == "tool"` — tool call lifecycle. Written as a structured entry when `part.state.status == "completed"`:

```
[TOOL: read] /path/to/file.md
[TOOL: bash] ls -la
```

The SSE thread writes to the progress file append-only as events arrive — if the process crashes mid-review, the partial transcript is preserved. The thread terminates when the main thread exits (the SSE connection is closed).

### Write Result

When the blocking POST returns with `finish == "stop"`:

1. Signal the SSE thread to stop (`stop_event.set()`), then wait for it to drain (`sse.join(timeout=5)`).
2. Extract all `parts` where `type == "text"` and join them.
3. Write to `.opencode/tasks/{task_id}.result.md` (atomic via temp file + `os.replace()`).
4. Write `COMPLETE` to `.opencode/tasks/{task_id}.status` (atomic via temp file + `os.replace()`).
5. Exit.

### Error Handling

If the POST fails (HTTP error, server crashed, timeout), write `FAILED` to the status file and exit. No retry — if OpenCode died mid-review, there's nothing to retry against. The partial progress transcript (if any) is preserved for inspection.

If `finish` is anything other than `"stop"` (e.g., a future error state), treat it as `FAILED`.

### Cleanup

The background process doesn't delete anything. Files accumulate in `.opencode/tasks/`. They serve as an audit trail — Claude Code can read the progress transcript to understand what the agent did. The directory should be gitignored.

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
| `OPENCODE_PORT` | *(auto)* | Force-override port (skips per-project auto-selection) |
| `OPENCODE_TIMEOUT` | `1800` | Seconds before background process write FAILED (HTTP request timeout) |
| `OPENCODE_STARTUP_TIMEOUT` | `10` | Seconds to wait for server health on startup |
| `OPENCODE_DEBUG` | `0` | Enable debug logging |
| `OPENCODE_LOG_FILE` | `/tmp/opencode-hook-debug.log` | Log file path |
| `OPENCODE_MODEL` | *(none)* | Override model (passed as `modelID` in prompt request) |
| `OPENCODE_SERVER_PASSWORD` | *(none)* | Auth password if configured |
| `OPENCODE_SKIP_POLLER` | `0` | Test-only: suppress background process spawning |

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

.opencode/                           # gitignored
  server.port                      # auto-selected port (plain text, atomic write)
  tasks/                           # created on first dispatch
    {task_id}.status               # PENDING | COMPLETE | FAILED
    {task_id}.prompt               # review prompt text (hook → poller IPC)
    {task_id}.result.md            # review content (written on POST completion)
    {task_id}.progress.md          # real-time transcript: token stream + tool calls
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

A `fake_opencode` pytest fixture that spins up a minimal `http.server` on a random port with configurable responses per endpoint:

- `POST /session` → returns a session JSON with an `id` field.
- `POST /session/{id}/message` → blocks for `delay` seconds (simulating review time), then returns `{"info": {"finish": "stop", "time": {"created": ..., "completed": ...}, ...}, "parts": [...]}`.
- `GET /global/event` → SSE stream that emits a configurable sequence of `message.part.delta` and `message.part.updated` events then closes.

The `delay` parameter drives meaningful test scenarios: slow startup (2–3s), realistic review time (5–10s), and timeout cases (delay exceeding `OPENCODE_TIMEOUT`).

### Test Groups

| Group | Tests | What's Covered |
|---|---|---|
| Detection | ~7 | Pass-through cases, both interception patterns, bypass flag, case-insensitivity |
| Server lifecycle | ~5 | Health check success (`/global/health`), on-demand startup, startup failure with stderr capture, startup timeout, fail-fast on early exit |
| Dispatch | ~4 | Session creation, background process spawned, deny JSON structure, status file initialised to PENDING |
| Background process | ~6 | Blocking POST → result written on `finish=stop`, status transitions PENDING → COMPLETE, timeout → FAILED, HTTP error → FAILED, SSE deltas written to progress file, tool calls written to progress file |
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

- **OpenCode TypeScript SDK** — adds a Node.js dependency for marginal benefit. Raw HTTP via `urllib` is sufficient for the endpoints we use.
- **Configurable routing by agent type** — architecture supports it, but v2 ships with reviews-only. Future work.
- **Synchronous fallback mode** (`OPENCODE_ASYNC=0`) — noted as an escape hatch if Claude's async behaviour is unreliable, but not implemented in v2.
- **OpenAI-compatible streaming endpoint** — OpenCode does not expose `/v1/chat/completions`. The native SSE stream at `/global/event` is the only streaming mechanism and is what we use.

---

## API Contract — Empirically Verified (2026-04-04)

All of the following were confirmed against OpenCode v1.3.13 via live probing.

- **Health check:** `GET /global/health` returns `{"healthy": true, "version": "1.3.13"}`. `GET /` also works (returns the web UI HTML), but `/global/health` is the correct endpoint.
- **Session creation:** `POST /session` with `{}` body returns `{"id": "ses_...", "slug": "...", "directory": "...", "title": "...", "time": {...}}`. The session ID field is `id`.
- **Prompt endpoint:** `POST /session/{id}/message` with `{"parts": [{"type": "text", "text": "..."}]}`. Blocks synchronously until the model finishes — including all internal tool calls. Returns `{"info": {...}, "parts": [...]}`.
- **Completion signal:** `response["info"]["finish"] == "stop"`. Set only on the terminal message. `info.time.completed` is also set when done (absent while in-progress). Intermediate tool-call messages have `finish == "tool-calls"` and exist only in the session history — the blocking POST returns only the final message.
- **Text extraction:** Collect `part["text"]` for all `parts` where `part["type"] == "text"`.
- **Part types observed:** `step-start`, `step-finish`, `text`, `tool`. `step-finish` carries a `reason` field: `"stop"` (normal completion) or `"tool-calls"` (intermediate step, not returned by the POST).
- **SSE stream:** `GET /global/event` — Server-Sent Events, no auth required on an unsecured server. Each event is `data: {JSON}\n\n`. The JSON has a `payload` object with `type` and `properties` fields. Relevant event types: `message.part.delta` (token chunk in `properties.delta`, a raw string), `message.part.updated` (full part state including tool call input/output), `session.status` (`busy`/`idle`), `session.idle` (fires after POST completes). All events include a `sessionID` in `properties` — filter on this to isolate the active session.
- **No OpenAI-compatible endpoint:** `/v1/chat/completions`, `/v1/models`, and similar paths do not exist.
- **Auth header format:** `Authorization: Bearer {OPENCODE_SERVER_PASSWORD}`. Sent on health check, session creation, message POST, and SSE subscription. Verified in test suite.
