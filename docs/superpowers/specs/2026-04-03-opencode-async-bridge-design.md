# OpenCode Async Bridge — Design Spec

> **Last updated:** 2026-04-07
> This is a living document. If source code were lost, this spec should be sufficient to recreate it.

## Overview

A TOML-configured router hook that classifies Claude `Agent` tool calls, selects an OpenCode agent and optional provider/model override, and dispatches work asynchronously via OpenCode Server's REST API. Work runs in the background while the main Claude session continues. Results are delivered via file-based handshake.

The mechanism remains entirely hook-based. No superpowers skill files are modified.

---

## Problem

The v1 Gemini review hook works but blocks the main Claude session for 60–120 seconds per review. This is dead time — Claude can't do anything else while waiting for Gemini CLI to finish. Additionally, the v1 approach is locked to a single model and a single use case (reviews). OpenCode Server, authenticated via GHCP OAuth, provides access to multiple models and agents, and exposes a REST API that enables asynchronous dispatch of arbitrary agent work.

---

## Approach

A `PreToolUse` hook fires on every `Agent` tool call. The hook loads a TOML config file (`.claude/hooks/opencode-router.toml`) that defines named profiles and ordered routes. Each invocation evaluates the incoming `subagent_type` and `description` against the route table using first-match-wins semantics. If a route matches, the hook resolves the associated profile, dispatches work to OpenCode Server via HTTP, spawns a background poller process, and returns a deny with `permissionDecision: "deny"` — all within under 1 second. The `permissionDecisionReason` field carries instructions back to the calling Claude session: what happened (work dispatched to OpenCode), where the result will appear (file paths), and what to do on failure (retry with bypass flag).

The `[BYPASS_HOOK]` escape hatch is checked before any route evaluation. If the description starts with `[BYPASS_HOOK]`, the hook passes through immediately — this is the retry mechanism after a dispatch failure.

The background process sends a blocking POST to OpenCode and concurrently subscribes to OpenCode's SSE event stream, writing a real-time progress transcript as the agent works. When the POST returns, the final result is written to the handshake file. Claude reads the file at a natural breakpoint and continues the workflow.

If the TOML config file is missing, the hook does nothing and falls through silently (exit 0, no output) — Claude's Agent call proceeds unintercepted. The same fall-through applies when no route matches, or when OpenCode is unavailable.

---

## Architecture

Five components, all Python 3 stdlib (no pip dependencies):

### 1. The Hook (`intercept-review-agents.py`)

Single entry point. On normal invocation, the hook loads the TOML router config, evaluates routes against the incoming `subagent_type` and `description`, resolves the matching profile, dispatches to OpenCode Server via `urllib.request`, and returns immediately. The hook file contains all logic — config loading, route matching, server management, dispatch, and poller — invoked differently based on argv.

- Normal invocation (from Claude Code): load config, match route, dispatch, return deny
- `--poll {session_id} {task_id} {port} {cwd} {profile_name}`: poller mode, called as a subprocess

### 1a. The Router Config (`opencode-router.toml`)

A TOML file at `.claude/hooks/opencode-router.toml` that defines named profiles and ordered routes. The hook loads this file on every invocation. See the **Configuration** section for the full schema.

### 2. The Server Manager

Functions within the hook that handle on-demand OpenCode Server startup. The server is a long-running process that persists across hook invocations — startup cost is paid once per working session.

### 3. The Background Process

A detached subprocess of the hook (same file, `--poll` flag) that does two things concurrently:

- **Main thread:** sends `POST /session/{id}/message` and blocks until OpenCode returns the completed response (`info.finish == "stop"`). Then writes the result to the handshake files.
- **SSE thread:** subscribes to `GET /global/event` and streams token deltas and tool call events to the progress transcript file. Terminates when the main thread exits.

### 4. The Result Files

File-based handshake mechanism under `.opencode/tasks/` in the project root:
- `{task_id}.status` — `PENDING`, `COMPLETE`, or `FAILED`
- `{task_id}.prompt` — the prompt text (written by hook, read by poller as IPC)
- `{task_id}.result.md` — the agent's output (written when POST returns)
- `{task_id}.progress.md` — real-time transcript of agent work: token stream and tool calls (written continuously by SSE thread)

Status and result files are written atomically via temp file + `os.replace()`. Readers polling these files are guaranteed to see either the previous state or the new state, never partial content.

---

## Route Matching

Classification uses ordered route evaluation against the TOML config. The `[BYPASS_HOOK]` check runs first, before config loading or route evaluation.

### Evaluation Order

1. **Bypass check:** if `description.startswith('[BYPASS_HOOK]')`, pass through immediately (exit 0, no output). This is the retry mechanism after a dispatch failure.
2. **Config loading:** load `.claude/hooks/opencode-router.toml`. If the file is missing, pass through silently.
3. **Route evaluation:** iterate `[[routes]]` in declared order. For each enabled route:
   - `match_subagent`: exact string equality against `subagent_type`. Required on every route.
   - `match_description_prefix`: case-insensitive `startswith()` against `description`. Optional — if omitted, any description matches.
   - First route where all specified fields match wins. The associated profile is resolved.
4. **No match:** if no route matches, pass through silently (exit 0, no output).

### Example Route Table

| Route | `match_subagent` | `match_description_prefix` | Profile |
|---|---|---|---|
| `superpowers-review` | `superpowers:code-reviewer` | *(any)* | `review_gpt54` |
| `general-review-prefix` | `general-purpose` | `review` | `review_gpt54` |

With this config, a `superpowers:code-reviewer` call matches the first route. A `general-purpose` call with a description starting with "Review" (case-insensitive) matches the second. All other calls pass through.

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

The early-exit detection is critical. If OpenCode can't start (e.g., not authenticated via `opencode auth`), the hook detects this within milliseconds rather than waiting for a 10-second timeout. The hook falls through silently (exit 0, no output) so the work proceeds via Claude Agent, but **always** logs the error and prints a one-line warning to stderr — regardless of whether debug mode is enabled:

```
[stderr] OpenCode hook: server startup failed — Not authenticated. Run 'opencode auth' to log in. Falling back to Claude agent. Details: /tmp/opencode-hook-debug.log
```

The full error is captured in `OPENCODE_LOG_FILE` for inspection. Debug mode controls verbose per-request logging; startup failures are exceptional events that are always recorded.

### Persistence

The server outlives the hook invocation. No shutdown logic — it runs until the user kills it or the machine sleeps. Subsequent dispatches reuse the same server instance.

### Auth Assumption

OpenCode is pre-authenticated via GHCP OAuth (`opencode auth` done once). The hook doesn't manage credentials. If `OPENCODE_SERVER_PASSWORD` is set, the hook includes it in HTTP requests.

---

## Dispatch Flow

Once a route matches and the server is healthy, three steps:

### 1. Create Session

`POST /session` with `{}`. Returns a session object — the session ID is in the `id` field. The task ID is generated by the hook — a short UUID.

### 2. Spawn Background Process

The hook launches itself as a detached subprocess in poller mode, passing the session ID, task ID, and the resolved profile name:

```python
subprocess.Popen(
    [sys.executable, __file__, '--poll', session_id, task_id, str(port), cwd, profile_name],
    start_new_session=True,
    stdout=subprocess.DEVNULL,
    stderr=open(log_file, 'a') if debug else subprocess.DEVNULL,
)
```

The `cwd` argument is passed so the background process knows where to write `.opencode/tasks/` files. The `profile_name` is passed so the background process can reload the TOML config and resolve the dispatch settings (agent, optional provider/model, timeout) independently. The background process immediately sends the blocking POST to OpenCode and subscribes to the SSE stream — see **Background Process** section.

### 3. Return Deny

The hook creates `.opencode/tasks/` if needed, writes `{task_id}.prompt` (the prompt text for the poller to read) and `{task_id}.status` -> `PENDING`, then prints the deny JSON and exits.

**Total hook runtime: under 1 second.**

---

## Deny Reasons

### Successful dispatch (async)

```
A PreToolUse hook dispatched this task to OpenCode Server (async, agent:
{agent_name}). The task is running in the background. When you're ready for
the result, read `.opencode/tasks/{task_id}.status`. When it says COMPLETE,
read `.opencode/tasks/{task_id}.result.md` and continue the workflow as
normal. If it says FAILED, re-invoke the original agent call with
[BYPASS_HOOK] prepended to the description field — the hook will let it
through to the Claude agent this time.
```

### Server startup failure

On startup failure, the hook exits 0 with no output — the original Agent call proceeds (Claude subagent handles the work). The error is **always** written to `OPENCODE_LOG_FILE` and a one-line summary is printed to stderr, regardless of debug mode. This ensures the user can always inspect why OpenCode handoff failed and fix it for next time.

```
[stderr] OpenCode hook: server startup failed — Not authenticated. Run 'opencode auth' to log in. Falling back to Claude agent. Details: /tmp/opencode-hook-debug.log
```

---

## Background Process

The background process runs two concurrent threads from the moment it starts.

### Main Thread: Blocking POST

Sends `POST /session/{session_id}/message` with the prompt and routing fields resolved from the matched profile:

```json
{
  "agent": "code-reviewer",
  "model": {
    "providerID": "poe",
    "modelID": "openai/gpt-5.4"
  },
  "parts": [{ "type": "text", "text": "<prompt>" }]
}
```

Field rules:
- `agent` is always sent when a route matches. It selects which OpenCode agent handles the work.
- `model` is sent only when the selected profile specifies both `provider` and `model`. It is an object with `providerID` and `modelID` fields. When omitted, the OpenCode agent's configured defaults apply.
- `parts` contains the prompt text.

This call blocks until OpenCode finishes — including all internal tool calls the agent makes. The response is a single `{ info, parts }` object representing the final assistant message. Completion is confirmed by `response["info"]["finish"] == "stop"`. No polling loop required.

The timeout for this call is resolved from the profile's `timeout_seconds`, falling back to the TOML `defaults.startup_timeout_seconds` for startup and the `OPENCODE_TIMEOUT` env var (default 1800s) for the request. If the call exceeds the timeout, write `FAILED` to the status file and exit.

**Note:** An invalid `agent` value does not produce an HTTP error from OpenCode. The API returns an empty 200 response. The hook treats empty response bodies as failure — see **Error Handling**.

### SSE Thread: Progress Transcript

Concurrently with the blocking POST, subscribes to `GET /global/event` (OpenCode's SSE stream) and writes a running transcript to `{task_id}.progress.md`, filtered to the active `sessionID`.

Two event types are captured:

- **`message.part.delta`** — raw token string in `properties.delta`. Appended directly to the transcript to form the streaming text as the model generates it.
- **`message.part.updated`** with `part.type == "tool"` — tool call lifecycle. Written as a structured entry when `part.state.status == "completed"`:

```
[TOOL: read] /path/to/file.md
[TOOL: bash] ls -la
```

The SSE thread writes to the progress file append-only as events arrive — if the process crashes mid-task, the partial transcript is preserved. The thread terminates when the main thread exits (the SSE connection is closed).

### Write Result

When the blocking POST returns with `finish == "stop"`:

1. Signal the SSE thread to stop (`stop_event.set()`), then wait for it to drain (`sse.join(timeout=5)`).
2. Extract all `parts` where `type == "text"` and join them.
3. Write to `.opencode/tasks/{task_id}.result.md` (atomic via temp file + `os.replace()`).
4. Write `COMPLETE` to `.opencode/tasks/{task_id}.status` (atomic via temp file + `os.replace()`).
5. Exit.

### Error Handling

The background process writes `FAILED` to the status file and exits on any of these conditions:

- HTTP error or connection failure
- Server crashed or became unreachable
- Request timeout exceeded
- Empty response body (returned by OpenCode for invalid agent names)
- Response body is not valid JSON
- Response JSON missing `info` or `parts` fields
- `info.finish` is anything other than `"stop"`

No retry — if OpenCode died mid-work, there's nothing to retry against. The partial progress transcript (if any) is preserved for inspection. The failure reason is always logged.

### Cleanup

The background process doesn't delete anything. Files accumulate in `.opencode/tasks/`. They serve as an audit trail — Claude Code can read the progress transcript to understand what the agent did. The directory should be gitignored.

---

## Result Delivery to Claude

### How Claude Handles the Async Result

Claude reads the deny reason, understands the task is in-flight, and continues with other work. At a natural breakpoint, it reads the status file. If COMPLETE, it reads the result file and incorporates the output. If FAILED, it retries the original Agent call with `[BYPASS_HOOK]` in the description, which the hook passes through to the Claude subagent.

### The Bypass Mechanism

When a dispatched task fails (timeout, server crash, HTTP error, invalid agent), the deny reason instructs Claude to retry with `[BYPASS_HOOK]` prepended to the description field. The hook checks for this marker before any other logic — including config loading and route evaluation:

```python
if description.startswith('[BYPASS_HOOK]'):
    log('bypass flag detected, passing through')
    sys.exit(0)
```

This ensures work always completes — either via OpenCode or via the original Claude Agent fallback.

### Timing Hint

The deny reason includes a nudge: *"Continue with your current work and check back after completing your next task."* This guides Claude toward productive async behaviour.

---

## Configuration

### Router TOML (`opencode-router.toml`)

Config path: `.claude/hooks/opencode-router.toml` (adjacent to the hook script). Loaded on every invocation. If the file is missing, the hook passes through silently and does nothing.

#### Full Schema

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

#### Top-Level Keys

| Key | Required | Description |
|---|---|---|
| `version` | Yes | Schema version. Must be `1`. |
| `[defaults]` | Yes | Default settings for the hook. |
| `[profiles.*]` | Yes (at least one) | Named dispatch profiles. |
| `[[routes]]` | Yes (at least one) | Ordered route table. |

#### `[defaults]`

| Key | Required | Default | Description |
|---|---|---|---|
| `startup_timeout_seconds` | No | `10` | Seconds to wait for OpenCode server health on startup. |

There is no `defaults.fallback` field. Fallback is always handled by the `[BYPASS_HOOK]` retry mechanism: when dispatch fails, the deny reason instructs Claude to retry with `[BYPASS_HOOK]` prepended to the description, and the hook passes that through to the Claude Agent.

#### `[profiles.<name>]`

| Key | Required | Description |
|---|---|---|
| `agent` | Yes | OpenCode agent name (e.g., `"code-reviewer"`, `"implementor"`). Always sent in the dispatch payload. |
| `provider` | No* | Provider ID for model override (e.g., `"poe"`). |
| `model` | No* | Model ID for model override (e.g., `"openai/gpt-5.4"`). |
| `timeout_seconds` | No | Per-profile request timeout. Overrides `OPENCODE_TIMEOUT` env var. |

*`provider` and `model` are optional as a pair: if either is set, both must be set. When both are omitted, the OpenCode agent's own configured defaults apply. Reasoning effort is not modeled in the hook TOML — configure it in OpenCode agent definitions.

#### `[[routes]]`

Routes are evaluated in declared order. First matching enabled route wins.

| Key | Required | Description |
|---|---|---|
| `name` | Yes | Human-readable route name (for logging). |
| `enabled` | Yes | `true` or `false`. Disabled routes are skipped. |
| `match_subagent` | Yes | Exact string match against `subagent_type`. Required on every route to prevent accidental catch-all routes. |
| `match_description_prefix` | No | Case-insensitive prefix match against `description`. If omitted, any description matches. |
| `profile` | Yes | Name of a profile defined in `[profiles.*]`. |

#### Validation Rules

The hook validates the config on load. Invalid config logs an error and falls through silently (the hook does nothing, Claude Agent proceeds). Validation checks:

- `version` must be `1`
- Every profile must have an `agent` field
- If a profile sets `provider`, it must also set `model` (and vice versa)
- Every route must have `match_subagent` (no catch-all routes)
- Every route must reference a profile that exists in `[profiles.*]`

### Environment Variables

Environment variables remain supported for operational overrides, settable in `settings.local.json` under `"env"`:

| Variable | Default | Description |
|---|---|---|
| `OPENCODE_PORT` | *(auto)* | Force-override port (skips per-project auto-selection) |
| `OPENCODE_SERVER_PASSWORD` | *(none)* | Auth password if configured |
| `OPENCODE_DEBUG` | `0` | Enable debug logging |
| `OPENCODE_LOG_FILE` | `/tmp/opencode-hook-debug.log` | Log file path |
| `OPENCODE_SKIP_POLLER` | `0` | Test-only: suppress background process spawning |

`OPENCODE_MODEL` is no longer supported. Model selection is configured via profiles in the TOML file.

---

## Extensibility

The router architecture is config-driven: adding a new route for a different agent type requires only a new `[[routes]]` entry and `[profiles.*]` definition in the TOML file. No code changes are needed to route additional `subagent_type` patterns to different OpenCode agents or provider/model combinations. The dispatch function is cleanly separated — it takes a resolved profile and a prompt and returns a task ID.

---

## File Layout

```
.claude/hooks/
  intercept-review-agents.py      # hook entry point — router, dispatch, poller
  opencode-router.toml            # TOML router config (profiles + routes)
  gemini-review-policy.toml       # retained from v1, unused
  archive/
    intercept-review-agents.sh     # v1 bash (already archived)
    intercept-review-agents-v1.py  # v1 python, archived when v2 ships

.opencode/                           # gitignored
  server.port                      # auto-selected port (plain text, atomic write)
  tasks/                           # created on first dispatch
    {task_id}.status               # PENDING | COMPLETE | FAILED
    {task_id}.prompt               # prompt text (hook → poller IPC)
    {task_id}.result.md            # agent output (written on POST completion)
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
- `POST /session/{id}/message` → blocks for `delay` seconds (simulating agent work time), then returns `{"info": {"finish": "stop", "time": {"created": ..., "completed": ...}, ...}, "parts": [...]}`.
- `GET /global/event` → SSE stream that emits a configurable sequence of `message.part.delta` and `message.part.updated` events then closes.

The `delay` parameter drives meaningful test scenarios: slow startup (2–3s), realistic agent work time (5–10s), and timeout cases (delay exceeding `OPENCODE_TIMEOUT`).

### Test Groups

| Group | Tests | What's Covered |
|---|---|---|
| Config loading | ~6 | Valid config parse, missing profile reference, missing `agent`, provider/model pair validation, disabled routes skipped, description-prefix normalization |
| Route matching | ~5 | Exact `subagent_type` match, description prefix match, first-match-wins on overlapping routes, no-match falls through, bypass flag short-circuits |
| Server lifecycle | ~5 | Health check success (`/global/health`), on-demand startup, startup failure with stderr capture, startup timeout, fail-fast on early exit |
| Dispatch payload | ~4 | `agent` always sent, `model` object sent when profile has provider/model, `model` omitted when profile only has `agent`, deny JSON structure |
| Background process | ~8 | Blocking POST with result on `finish=stop`, status transitions PENDING -> COMPLETE, timeout -> FAILED, HTTP error -> FAILED, empty body -> FAILED, invalid JSON -> FAILED, SSE deltas written to progress file, tool calls written to progress file |
| Fallback | ~3 | OpenCode binary not found, server unreachable after startup, missing TOML config falls through silently |
| Bypass | ~2 | `[BYPASS_HOOK]` in description passes through, normal descriptions still routed |

### Integration Tests (Manual)

Not in the automated suite. Documented steps:
1. Start OpenCode Server manually
2. Trigger a routed agent call from Claude Code (e.g., superpowers review)
3. Verify: hook matches route, dispatches, poller runs, result file appears, Claude reads it
4. Verify: kill OpenCode mid-task, confirm FAILED status and bypass retry

---

## Migration from v1

1. Archive `intercept-review-agents.py` to `archive/intercept-review-agents-v1.py`
2. Write new `intercept-review-agents.py` with router logic
3. Create `.claude/hooks/opencode-router.toml` with profiles and routes
4. Remove `OPENCODE_MODEL` from `.claude/settings.json` env (model selection is now in TOML profiles)
5. Add `.opencode/` to `.gitignore`
6. Ensure `opencode` is on PATH and authenticated (`opencode auth`)

v1's `gemini-review-policy.toml` is retained but unused. It can be removed later or kept for reference.

---

## Out of Scope

- **OpenCode TypeScript SDK** — adds a Node.js dependency for marginal benefit. Raw HTTP via `urllib` is sufficient for the endpoints we use.
- **Regex or glob route matching** — routes use exact `subagent_type` equality and optional prefix matching. More complex patterns are not needed at this stage.
- **Synchronous fallback mode** (`OPENCODE_ASYNC=0`) — noted as an escape hatch if Claude's async behaviour is unreliable, but not implemented.
- **OpenAI-compatible streaming endpoint** — OpenCode does not expose `/v1/chat/completions`. The native SSE stream at `/global/event` is the only streaming mechanism and is what we use.
- **Reasoning effort in hook TOML** — reasoning effort and other provider-specific passthrough options belong in OpenCode agent config, not the hook router.

---

## API Contract — Empirically Verified (2026-04-04)

All of the following were confirmed against OpenCode v1.3.13 via live probing.

- **Health check:** `GET /global/health` returns `{"healthy": true, "version": "1.3.13"}`. `GET /` also works (returns the web UI HTML), but `/global/health` is the correct endpoint.
- **Session creation:** `POST /session` with `{}` body returns `{"id": "ses_...", "slug": "...", "directory": "...", "title": "...", "time": {...}}`. The session ID field is `id`.
- **Prompt endpoint:** `POST /session/{id}/message` with `{"agent": "...", "parts": [{"type": "text", "text": "..."}]}`. The `agent` field selects which OpenCode agent handles the request. An optional `"model": {"providerID": "...", "modelID": "..."}` object overrides the agent's default provider/model. Blocks synchronously until the model finishes — including all internal tool calls. Returns `{"info": {...}, "parts": [...]}`. An invalid `agent` value returns an empty 200 response (not a 4xx error).
- **Completion signal:** `response["info"]["finish"] == "stop"`. Set only on the terminal message. `info.time.completed` is also set when done (absent while in-progress). Intermediate tool-call messages have `finish == "tool-calls"` and exist only in the session history — the blocking POST returns only the final message.
- **Text extraction:** Collect `part["text"]` for all `parts` where `part["type"] == "text"`.
- **Part types observed:** `step-start`, `step-finish`, `text`, `tool`. `step-finish` carries a `reason` field: `"stop"` (normal completion) or `"tool-calls"` (intermediate step, not returned by the POST).
- **SSE stream:** `GET /global/event` — Server-Sent Events, no auth required on an unsecured server. Each event is `data: {JSON}\n\n`. The JSON has a `payload` object with `type` and `properties` fields. Relevant event types: `message.part.delta` (token chunk in `properties.delta`, a raw string), `message.part.updated` (full part state including tool call input/output), `session.status` (`busy`/`idle`), `session.idle` (fires after POST completes). All events include a `sessionID` in `properties` — filter on this to isolate the active session.
- **No OpenAI-compatible endpoint:** `/v1/chat/completions`, `/v1/models`, and similar paths do not exist.
- **Auth header format:** `Authorization: Bearer {OPENCODE_SERVER_PASSWORD}`. Sent on health check, session creation, message POST, and SSE subscription. Verified in test suite.
