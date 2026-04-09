# Opencode Plugin for Claude Code — Research Report

**Date:** 2026-04-07  
**Purpose:** Engineering reference for building a Claude Code plugin that delegates code review (and potentially tasks) to an Opencode server, modelled on the official Codex plugin (`openai/codex-plugin-cc`).

---

## 1. Reference Architecture: How the Codex Plugin Works

The Codex plugin (`openai/codex-plugin-cc`) is a Claude Code plugin with this structure:

```
plugins/codex/
├── commands/           # Slash command definitions (markdown with YAML frontmatter)
│   ├── review.md       # /codex:review — delegates to companion script
│   ├── adversarial-review.md
│   ├── status.md       # /codex:status — check job progress
│   ├── result.md       # /codex:result — retrieve completed job output
│   ├── cancel.md       # /codex:cancel — abort a running job
│   └── setup.md        # /codex:setup — verify prerequisites
├── scripts/
│   ├── codex-companion.mjs    # CLI entrypoint — subcommand router
│   └── lib/
│       ├── app-server.mjs     # Transport: JSON-RPC client (stdio + Unix socket)
│       ├── codex.mjs          # High-level API: thread/turn lifecycle + event interpreter
│       ├── git.mjs            # Diff collection and review target resolution
│       ├── render.mjs         # Output formatting for Claude Code consumption
│       ├── state.mjs          # Job persistence (filesystem-backed)
│       ├── tracked-jobs.mjs   # Job lifecycle tracking with log files
│       ├── job-control.mjs    # Job resolution, status snapshots
│       ├── broker-lifecycle.mjs # Persistent Codex process management
│       └── ...
├── hooks/              # Claude Code lifecycle hooks (SessionStart/End, Stop gate)
├── prompts/            # Review prompt templates with interpolation
├── schemas/            # Structured output JSON schemas
├── skills/             # Bundled Claude Code skills (prompting guidance, result handling)
└── agents/             # Agent definitions (e.g., codex-rescue)
```

### Key design patterns

**Two-layer communication:**
1. `app-server.mjs` — Transport layer. JSON-RPC over stdio (spawns `codex app-server`) or Unix domain socket (persistent broker). Handles request/response ID matching, notification routing, connection lifecycle.
2. `codex.mjs` — Event interpreter. `captureTurn()` registers a notification handler that translates Codex events into human-readable progress strings via `describeStartedItem()` / `describeCompletedItem()`. This is what produces the live "thinking" output visible in Claude Code's terminal.

**Foreground vs background execution:**
- Foreground: `node codex-companion.mjs review` blocks, streams progress to stdout. Claude Code shows output in real time.
- Background: Claude Code launches with `Bash({ command: "...", run_in_background: true })`. User checks progress via `/codex:status`.

**Command-level instruction control:**
- Commands use `disable-model-invocation: true` — Claude Code doesn't reason about the output, just runs the script and returns stdout verbatim.
- `allowed-tools` restricts what Claude Code can do during command execution.

**Job tracking:**
- Jobs are persisted to the filesystem with status, log files, thread IDs, and timestamps.
- Enables `/codex:status`, `/codex:result`, `/codex:cancel` as separate commands.

---

## 2. Opencode Server API — What We're Targeting

Source: `anomalyco/opencode` (TypeScript monorepo), OpenAPI spec at `packages/sdk/openapi.json`.

### Core session lifecycle

```
POST /session                              → Create session (returns { id: "ses..." })
POST /session/{sessionID}/message          → Send prompt, blocking (returns full response)
POST /session/{sessionID}/prompt_async     → Send prompt, fire-and-forget (returns 204)
POST /session/{sessionID}/abort            → Cancel active processing
GET  /session/status                       → All session statuses
GET  /session/{sessionID}/message          → Retrieve message history
GET  /global/event                         → SSE event stream (GlobalEvent)
```

### Query parameter scoping

Every endpoint accepts optional `?directory=` and `?workspace=` query params:
- `directory` — absolute path to the project on disk (scopes to a project)
- `workspace` — workspace ID (`wrk...`, scopes to a specific worktree/branch)

If Opencode is managing a single project with no worktrees, these can be omitted.

### Prompt payload structure

```json
{
  "parts": [
    { "type": "text", "text": "Review this code..." },
    { "type": "file", "mime": "text/plain", "url": "file:///path/to/file" }
  ],
  "model": {
    "providerID": "anthropic",
    "modelID": "claude-sonnet-4-20250514"
  },
  "agent": "optional-agent-name",
  "system": "optional system prompt override",
  "format": { "type": "text" },
  "noReply": false
}
```

The `noReply` flag is useful for injecting context without triggering a response.

### Response structure

```json
{
  "info": {
    "id": "msg...",
    "sessionID": "ses...",
    "role": "assistant",
    "tokens": { "input": 0, "output": 0, "reasoning": 0, "cache": { "read": 0, "write": 0 } },
    "cost": 0.0
  },
  "parts": [ ... ]
}
```

---

## 3. SSE Event Stream — The Progress Layer

**This is the critical finding.** The blocking `/session/{id}/message` endpoint would cause Claude Code to appear hung. The non-blocking path is:

1. `POST /session/{id}/prompt_async` — returns 204 immediately
2. `GET /global/event` — SSE stream of `GlobalEvent` objects

### GlobalEvent envelope

```typescript
type GlobalEvent = {
  directory: string      // project path — use to filter for your project
  payload: Event         // discriminated union on `type` field
}
```

### Event types relevant to progress display

| Event type | Discriminant | Key fields | Use |
|---|---|---|---|
| `session.status` | `properties.status.type` = `"busy"` / `"idle"` / `"retry"` | `sessionID`, `status` | Detect start/end of processing |
| `message.part.updated` | `properties.part.type` (see below) | `part`, `delta?` | **Primary progress source** — streams text, tool calls, reasoning |
| `session.idle` | — | `sessionID` | Session finished processing |
| `session.error` | — | `sessionID`, `error` | Error occurred |
| `file.edited` | — | `file` (path) | A file was modified |
| `command.executed` | — | `name`, `arguments`, `sessionID` | A command was executed |

### Part types within `message.part.updated`

The `part` field is a discriminated union on `type`. These are the ones that drive progress output:

| Part type | Key fields | Progress display |
|---|---|---|
| `"text"` | `text`, streaming via `delta` | The actual response text being generated |
| `"tool"` | `tool` (name), `state` (see below), `callID` | Tool invocation lifecycle |
| `"reasoning"` | `text` | Model's thinking (if reasoning model) |
| `"step-start"` | `snapshot?` | New reasoning step began |
| `"step-finish"` | `reason`, `cost`, `tokens` | Step completed with token accounting |
| `"subtask"` | `prompt`, `agent`, `description` | Subagent delegation |

### Tool state machine

Tool parts transition through states, each emitted as a `message.part.updated`:

```
ToolStatePending   → { status: "pending", input: {...}, raw: "..." }
ToolStateRunning   → { status: "running", input: {...}, title?: "...", time: { start } }
ToolStateCompleted → { status: "completed", input: {...}, output: "...", title: "...", time: { start, end } }
ToolStateError     → { status: "error", input: {...}, error: "...", time: { start, end } }
```

**This is richer than Codex's event model.** You can show tool name + status transitions, giving Claude Code users visibility into what Opencode is doing at each step.

---

## 4. Proposed Plugin Architecture

```
plugins/opencode/
├── commands/
│   ├── review.md           # /opencode:review
│   ├── status.md           # /opencode:status
│   ├── result.md           # /opencode:result
│   └── cancel.md           # /opencode:cancel
├── scripts/
│   ├── opencode-companion.mjs   # CLI entrypoint
│   └── lib/
│       ├── client.mjs           # HTTP + SSE client for Opencode server
│       ├── events.mjs           # Event interpreter (SSE → progress strings)
│       ├── git.mjs              # Review target resolution (diff collection)
│       ├── render.mjs           # Output formatting
│       └── state.mjs            # Job tracking (optional, for background mode)
├── prompts/
│   └── review.md                # Review prompt template
└── hooks/                       # Optional lifecycle hooks
```

### Simplifications vs Codex plugin

- **No JSON-RPC layer.** Opencode uses plain HTTP REST + SSE. No request ID matching, no broker lifecycle.
- **No broker management.** Opencode server is assumed to be already running (user starts it separately or it's a daemon).
- **Simpler transport.** `fetch()` for REST calls, `EventSource` or readline on an HTTP stream for SSE.
- **No `codex app-server` spawning.** The server is external.

### Core flow: `/opencode:review`

```
1. Collect review context (git diff, working tree state)
2. POST /session — create session
3. Connect to GET /global/event — start listening for SSE events, filtered by sessionID
4. POST /session/{id}/prompt_async — fire the review prompt
5. Stream progress to stdout as events arrive:
   - session.status → "Opencode is processing..."
   - message.part.updated (tool, running) → "Running: read_file src/auth.ts"
   - message.part.updated (tool, completed) → "✓ read_file completed"
   - message.part.updated (text, delta) → stream response text
   - session.idle → done, print final output, exit
6. On error → print error, exit non-zero
```

---

## 5. Open Questions / Verification Needed

These should be validated against a live Opencode server instance:

### SSE event format
- **What is the actual wire format?** Standard SSE (`data: {...}\n\n`) or something custom? Need to confirm the JSON parsing path.
- **Event filtering:** Does the SSE stream support filtering by session ID, or do we receive all events globally and filter client-side? (The `GlobalEvent` wrapper suggests client-side filtering via `directory` and then `properties.sessionID`.)

### Session scoping
- **Does `prompt_async` require the session to exist first?** Or can we create-and-prompt in one step?
- **Agent configuration:** How are agents defined in Opencode? The `agent` field on the prompt payload — what are valid values? Is there a built-in reviewer agent, or do we need to provide review instructions via the system prompt?

### Permission handling
- **Tool permissions:** The `PermissionRuleset` on session creation — what does this look like? For a read-only review, we'd want to restrict to read-only tools.
- **`EventPermissionUpdated`** — does Opencode pause and wait for permission grants? If so, the plugin needs to either pre-approve or auto-respond.

### Server discovery
- **How does the plugin find the Opencode server?** Options: environment variable (`OPENCODE_URL`), config file, or convention (`localhost:3000`). Need to check Opencode's default port and whether it exposes a health endpoint for verification (`GET /global/health`).

### Model selection
- **Does Opencode respect the `model` field on prompts?** Or is the model fixed in server config? If configurable per-prompt, the plugin should expose `--model` as a flag.

### Diff strategy
- **Pass the diff as text in the prompt** (like the Codex adversarial review does — `collectReviewContext()` in `git.mjs`), or **let Opencode read the files itself** via its own tools? The former is more deterministic; the latter leverages Opencode's file access.

---

## 6. Source References

| File | What it tells you |
|---|---|
| `opencode/packages/sdk/js/src/gen/types.gen.ts` | All TypeScript types including Event union, Part union, ToolState, SessionStatus |
| `opencode/packages/sdk/openapi.json` | Full REST API spec (endpoints, request/response schemas) |
| `opencode/packages/opencode/src/control-plane/sse.ts` | Server-side SSE implementation |
| `opencode/packages/opencode/src/session/` | Session lifecycle, message processing |
| `codex-plugin-cc/plugins/codex/scripts/lib/app-server.mjs` | Codex transport layer (reference for equivalent) |
| `codex-plugin-cc/plugins/codex/scripts/lib/codex.mjs` | Codex event interpreter (`captureTurn`, progress emission) |
| `codex-plugin-cc/plugins/codex/commands/review.md` | Codex review command definition (reference for command structure) |

---

## 7. Recommended Next Steps

1. **Probe a live Opencode server** — hit `/global/health`, create a session, send a prompt via `prompt_async`, and capture the raw SSE stream to confirm event shapes.
2. **Map the SSE events to progress strings** — build the event interpreter once the wire format is confirmed.
3. **Prototype the minimal `/opencode:review` command** — hardcoded server URL, working-tree diff, foreground-only. Get the SSE→stdout pipeline working end to end.
4. **Add background mode and job tracking** — only after foreground works.
5. **Add `/opencode:status`, `/opencode:cancel`** — leveraging `GET /session/status` and `POST /session/{id}/abort`.
