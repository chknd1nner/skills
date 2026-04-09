# Opencode Plugin for Claude Code — Design

**Date:** 2026-04-09
**Status:** Approved for implementation planning
**Repo location:** `plugins/opencode/` (intended for future extraction to its own distribution repo via `git subtree split`)
**Brainstorm transcript:** in-session, this document is the consolidated output

---

## 1. Purpose and Scope

A standalone Claude Code plugin that lets a user dispatch a code review to a separately-running Opencode server with one slash command. v1 ships a single user-invokable command, `/opencode:review`, that:

1. Connects to a running Opencode server (the user owns the server lifecycle)
2. Creates a session scoped to the current project directory
3. Sends a review prompt that points the agent at the working tree (or branch diff) and lets the agent read files via its own tools
4. Streams progress live in the terminal (status footer with spinner, activity label, tool counter, elapsed timer)
5. Writes a chat-transcript-style activity log AND a separate clean review file under `.opencode/reviews/`
6. Returns the final review verbatim to the user

The plugin is designed to be **standalone and distributable**. It does not depend on Superpowers, the OpenCode router hook, or any sibling tooling in the Skills monorepo. It exists in `plugins/opencode/` during development for ergonomic reasons but is shaped so that a future `git subtree split` produces a working standalone repo without surgery.

It is also designed to be **easily extensible** in the same shape as the Codex plugin (`openai/codex-plugin-cc`). Background mode, status/result/cancel commands, generic task dispatch, and adversarial-review variants are all explicitly accounted for as future additions, with v1 making three small structural choices that keep their addition cheap.

### Non-goals for v1

- Background-mode reviews (deferred; v1 makes their addition cheap — see §7).
- `/opencode:status`, `/opencode:result`, `/opencode:cancel` (deferred; same).
- `/opencode:task` and `/opencode:adversarial-review` (deferred; same).
- Auto-starting the Opencode server. The user owns the lifecycle.
- Project-local config overlays. v1 is global config only.
- Multi-machine job tracking, OAuth, marketplace publishing automation.

---

## 2. Architectural Decisions (Locked)

| Decision | Choice | Rationale |
|---|---|---|
| Primary caller | User-typed slash command | Matches the Codex plugin UX; not an MCP server. |
| Distribution model | Standalone, distributable plugin | No dependencies on Superpowers or sibling repo tooling. |
| Language | Node.js (ESM, no build step) | Universal runtime, matches Codex plugin shape, no Python version friction for installers. |
| Code reuse with router hook | None — fully separate | Router hook is a Superpowers extension; this plugin is generic. |
| Server lifecycle | User owns it | Plugin is a pure HTTP client. Errors point at `opencode serve`. |
| Review strategy | Pointer + agent reads files (Strategy B) | Avoids large-diff problem; GPT-5.4 is capable enough to navigate the repo. |
| Review target flags | `--base <ref>` and `--scope auto\|working-tree\|branch` | Matches Codex `/codex:review` flag set. ~20 LOC of parsing. |
| Progress UX | Live status footer on stderr | Spinner, activity label, tool counter, elapsed timer. ~250ms tick. |
| Transcript output | Two files per review under `.opencode/reviews/` | Activity log + clean review, both with matching frontmatter. |
| Configuration | TOML, user-global | `~/.config/opencode-plugin/config.toml`. Env vars only for operational overrides. |
| Reasoning text gating | Off by default, config switch on | Some users (the spec author included) want it on; sane default is off. |
| Internal architecture | Single companion script + dispatcher (Approach 2) | 1:1 parallel to Codex's `codex-companion.mjs` shape. |
| Plugin primitive | `skills/<name>/SKILL.md` with `disable-model-invocation: true` | Current Anthropic-recommended pattern. `commands/` is legacy. |
| State storage | YAML frontmatter in the log file | "The transcript IS the state." No separate `.job.json` files. |

### v1 shape accommodations for future background mode

Three structural choices that cost nothing in v1 but make adding background mode a contained patch later (see §7 for details):

1. **`executeReviewRun` is extracted from `handleReview`.** The CLI wrapper is thin glue; the review work is a pure function that takes a fully-resolved context and returns a result object. v1 has one caller; future background mode adds a second caller (the worker entry point) without touching the core logic.
2. **Log file frontmatter is the canonical state store.** No separate job state files. `/opencode:status` (when added) reads frontmatter via glob.
3. **`status: running` is written immediately at review start**, not at the end. Combined with reserved `pid` and `worker_args` frontmatter fields, this means v2's stale-job recovery logic can be added without schema migration.

---

## 3. Directory Layout

```
plugins/opencode/
├── .claude-plugin/
│   └── plugin.json                    # Plugin manifest
├── skills/
│   ├── review/
│   │   └── SKILL.md                   # /opencode:review
│   └── setup/
│       └── SKILL.md                   # /opencode:setup
├── scripts/
│   ├── opencode-companion.mjs         # Single entry, subcommand dispatcher
│   └── lib/
│       ├── config.mjs                 # TOML loading + validation + precedence
│       ├── client.mjs                 # HTTP: health, POST /session, POST message
│       ├── events.mjs                 # SSE subscriber + event interpreter
│       ├── render.mjs                 # Live status footer (TTY/non-TTY)
│       ├── transcript.mjs             # Log + review file writers
│       ├── args.mjs                   # CLI argument parser
│       └── git.mjs                    # --base / --scope target resolution
├── prompts/
│   └── review.md                      # Review prompt template
├── tests/
│   ├── args.test.mjs
│   ├── config.test.mjs
│   ├── events.test.mjs
│   ├── render.test.mjs
│   ├── transcript.test.mjs
│   ├── git.test.mjs
│   ├── fixtures/
│   │   └── fake-opencode-server.mjs
│   └── integration/
│       ├── client.test.mjs
│       └── review-flow.test.mjs
├── package.json                       # Self-contained, smol-toml as only runtime dep
├── README.md                          # User-facing install + usage
└── LICENSE
```

**Layout principles:**

- The directory contents are exactly what would ship as a standalone repo. Nothing references anything outside `plugins/opencode/`. When a future `git subtree split` projects the directory to its own repo, files land at the new repo's root unchanged.
- `skills/<name>/SKILL.md` is the current-best-practice plugin primitive per Anthropic's plugin reference (the legacy `commands/*.md` pattern is documented as "legacy; use `skills/` for new skills").
- `package.json` has exactly one runtime dependency: `smol-toml` (~10KB, spec-compliant). Everything else is Node stdlib.

---

## 4. SKILL.md Instructions

### `skills/review/SKILL.md`

```markdown
---
description: Run a code review via your running Opencode server
argument-hint: '[--base <ref>] [--scope auto|working-tree|branch] [--model <spec>] [--json]'
disable-model-invocation: true
allowed-tools: Bash(node:*)
---

Run an Opencode code review through the companion script.

Raw slash-command arguments:
`$ARGUMENTS`

Core constraint:
- This command is review-only. Do not fix issues, apply patches, or suggest
  that you are about to make changes.
- Your only job is to run the review and return the companion script's
  output verbatim to the user.

Execution:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/opencode-companion.mjs" review "$ARGUMENTS"
```

Return the command's stdout verbatim. Do not paraphrase or summarise.
```

### `skills/setup/SKILL.md`

```markdown
---
description: Verify Opencode plugin setup and create the config file if missing
disable-model-invocation: true
allowed-tools: Bash(node:*)
---

Run the Opencode plugin setup helper.

Execution:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/opencode-companion.mjs" setup
```

Return the command's stdout verbatim.
```

**Note for implementation:** verify during build that `argument-hint` and `allowed-tools` frontmatter fields are honoured on SKILL.md the same way they are on legacy command markdown. The Codex plugin uses both. If either has been renamed or scoped differently for skills, adapt at implementation time.

---

## 5. Core Components

The dispatcher is thin; the real work lives in seven library modules. Each is single-purpose, ~50–300 LOC, and unit-testable in isolation.

### 5.1 `opencode-companion.mjs` — entry point + dispatcher

Mirror of `codex-companion.mjs` at ~200 LOC. Parses the first argv as the subcommand and dispatches to a handler. Handlers do composition: load config, parse flags, check server, run the command, render output. No heavy lifting here.

```javascript
async function main() {
  const [subcommand, ...argv] = process.argv.slice(2);
  switch (subcommand) {
    case "review": return handleReview(argv);
    case "setup":  return handleSetup(argv);
    case "help": case "--help": case undefined: printUsage(); return;
    default: printUsage(); process.exitCode = 2;
  }
}

main().catch((err) => {
  if (err instanceof OpencodePluginError) {
    process.stderr.write(`Error: ${err.message}\n`);
    if (err.suggestion) process.stderr.write(`\n${err.suggestion}\n`);
    process.exitCode = err.exitCode;
  } else {
    process.stderr.write(`Unexpected error: ${err.message}\n${err.stack}\n`);
    process.stderr.write(`\nThis looks like a bug. Please report it.\n`);
    process.exitCode = 1;
  }
});
```

### 5.2 `lib/config.mjs` — TOML loading + schema validation

Loads `~/.config/opencode-plugin/config.toml`, validates the schema, applies CLI overrides, returns a single resolved config object. Creates the file from a default template if it doesn't exist (first-run bootstrap).

**Public API:**
```javascript
loadConfig({ overrides?: object, configPath?: string }) → ResolvedConfig
ensureDefaultConfig() → { created: boolean, path: string }
```

**TOML parsing:** `smol-toml` (~10KB, maintained, spec-compliant). The plugin's only runtime dependency.

**Validation rules:**
- `server.url` parses as a URL (`new URL()` doesn't throw)
- `commands.review.agent` is a non-empty string
- `commands.review.provider` and `commands.review.model` are either both set or both unset
- `transcript.directory` is a relative path (not absolute, not `..`-traversing)
- `transcript.include_reasoning` is a boolean

**Precedence layering:** `mergeConfig(defaults, tomlConfig, cliOverrides)` — each layer is a partial object, later layers win. CLI flags become entries in `cliOverrides` before merging.

**Error handling:** validation failures throw `ConfigError` with a field path and a description of what was expected. TOML parser errors are wrapped with line numbers from the underlying error.

### 5.3 `lib/client.mjs` — HTTP client for the Opencode server

Thin wrapper over Node's built-in `fetch`. v1 uses three operations; one additional endpoint is documented as a contract for v2 use.

**Public API (v1):**
```javascript
healthCheck(config) → { healthy: boolean, version?: string }
createSession(config, { directory }) → { id: string }
sendMessage(config, sessionId, { directory, prompt, agent, model, signal }) → { info, parts }
```

**Endpoint contracts:**

| Method | Path | Request | Response | Used in |
|---|---|---|---|---|
| GET | `/global/health` | (none) | `{ healthy: boolean, version?: string }` | v1 — `healthCheck` |
| POST | `/session?directory=<absCwd>` | `{}` | `{ id: "ses_..." }` | v1 — `createSession` |
| POST | `/session/{id}/message?directory=<absCwd>` | `{ parts, agent, model? }` (see below) | `{ info: { finish, ... }, parts: [...] }` | v1 — `sendMessage` |
| GET | `/global/event` | (none) | SSE stream | v1 — `events.mjs` (subscribed separately) |
| POST | `/session/{id}/abort?directory=<absCwd>` | `{}` | (204 / status object) | **v2 only** — reserved for `/opencode:cancel` |

**Implementation notes:**
- Auth via `Authorization: Bearer ${config.server.password}` when set.
- Every request carries `?directory=${absoluteCwd}` to scope the session to the user's project (per the Opencode API research doc).
- `sendMessage` is a blocking POST. Progress comes from `events.mjs` running in parallel. Return value is the final consolidated assistant message — extract `response.parts.filter(p => p.type === 'text').map(p => p.text).join('\n\n')` as the final review text.
- `sendMessage` accepts an `AbortSignal` (`{ signal }`) so a `SIGINT` handler can cancel the in-flight request cleanly. The signal also flows through to the underlying `fetch`.
- **`model` payload shape:** the Opencode `/session/{id}/message` endpoint expects `model` as an **object**: `{ providerID: string, modelID: string }`. The TOML field names (`provider`, `model`) and the API field names (`providerID`, `modelID`) intentionally differ — the TOML names are friendlier for users, the client maps them at the boundary. Sending the API a flat string is silently ignored (verified in platform research).
- **Empty response body handling:** Opencode v1.3.x returns HTTP 200 with `Content-Length: 0` when the agent name is invalid. Treat empty body as `OpencodeResponseError` with "likely unknown agent" hint.
- On `ECONNREFUSED` or DNS failure: throw `OpencodeUnreachableError` with the URL and the `opencode serve` suggestion.

### 5.4 `lib/events.mjs` — SSE subscriber + event interpreter

Subscribes to `GET /global/event`, parses the SSE line stream, filters by session ID, and emits semantic events that drive the renderer and transcript writer in parallel.

**Public API:**
```javascript
class EventStream extends EventEmitter {
  constructor(config, sessionId);
  start() → Promise<void>;          // resolves when SSE connection is established
  stop() → Promise<void>;           // aborts fetch + waits for reader to drain
  waitForDone({ timeoutMs }) → Promise<void>;  // waits for 'done' event or quiescence window
  get toolCount();                  // public read-only counter, accumulated as 'tool-end' fires
  get isDone();                     // true once 'done' has been emitted
  // Events emitted:
  //   'phase'       { label: 'thinking'|'reading'|'running'|'searching'|'writing'|'finalizing' }
  //   'tool-start'  { tool, input, callId }
  //   'tool-end'    { tool, callId, toolCount }
  //   'text-delta'  { text }
  //   'reasoning'   { text }    // only if include_reasoning
  //   'done'        { }
  //   'error'       { error }
}
```

**`start()` is awaited before `sendMessage()` is called.** This is critical: a slow SSE connect must not race past the start of the review and miss early `tool-start` events. `start()` performs the `fetch` to `/global/event`, awaits the response headers (the 200 OK arrival is the "connected" signal), then begins reading the body in a detached background task. The Promise resolves at that point. If the connect fails, `start()` rejects and the whole review fails fast with `OpencodeApiError`.

**`stop()` triggers an `AbortController`** wired into the SSE `fetch` call. The reader sees the abort, exits its loop, releases the underlying socket, and `stop()` resolves. Idempotent — safe to call multiple times.

**`waitForDone({ timeoutMs })`** is the drain mechanism, called by the runner after `sendMessage` resolves. It returns immediately if `isDone` is already true; otherwise it awaits either the `done` event or a timeout (default 2s — long enough for late `session.idle` arrival, short enough not to feel hung). This prevents the `finally` block from cutting off late events that arrive after the POST returns.

**SSE parsing — chunk-to-line buffering:**

Web `ReadableStream` from `fetch` yields arbitrary byte chunks, not lines. The parser maintains a string buffer:

```javascript
const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
let buffer = "";
while (!aborted) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += value;
  // SSE message terminator is a blank line (\n\n). Accumulate complete messages.
  let sepIdx;
  while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
    const rawMessage = buffer.slice(0, sepIdx);
    buffer = buffer.slice(sepIdx + 2);
    parseAndDispatch(rawMessage);   // parse `data: <JSON>` lines, JSON.parse, emit
  }
}
```

`parseAndDispatch` handles a single SSE message — possibly multi-line — extracts the `data:` field(s), concatenates, `JSON.parse`s, filters by `payload.properties.sessionID`, and emits the appropriate semantic event. Malformed messages are silently dropped (logged at debug level if `OPENCODE_PLUGIN_DEBUG=1`).

The buffer is flushed on stream end — any final partial message left in the buffer is parsed before exit.

**Event interpreter is a state machine** translating Opencode events to higher-level semantic events:

| Opencode event | Becomes |
|---|---|
| `message.part.updated` + `part.type === 'tool'` + `state.status === 'running'` | `tool-start` + `phase` (label derived from `part.tool`) |
| `message.part.updated` + `part.type === 'tool'` + `state.status === 'completed'` | `tool-end` + counter increment |
| `message.part.updated` + `part.type === 'reasoning'` | `phase { label: 'thinking' }`; if `include_reasoning`, also `reasoning { text }` |
| `message.part.updated` + `part.type === 'text'` + delta | First delta: `phase { label: 'writing' }`. All deltas: `text-delta { text }` |
| `session.idle` | `done` |
| `session.error` | `error` |

Phase labels for tool calls:
- `read` → `'reading'` (with file path in renderer)
- `bash` → `'running'` (with command in renderer)
- `grep` → `'searching'` (with pattern in renderer)
- anything else → `'working'` (with tool name)

The module emits structured events only — no rendering, no file I/O. This makes it unit-testable by feeding it canned SSE lines and asserting on emitted events.

### 5.5 `lib/render.mjs` — live status footer on stderr

Subscribes to `EventStream` events and maintains a one-line status footer on stderr, updated ~250ms.

**Public API:**
```javascript
class StatusRenderer {
  constructor({ stream = process.stderr });
  attach(eventStream);
  start();
  stop();
}
```

**TTY mode:**
- Maintain state: `{ activity, toolCount, startTime, spinnerFrame }`.
- Tick every ~250ms. Build footer string: `${spinner} Opencode reviewing · ${activity} · Tool calls: ${count} · ${elapsed}`.
- Write `\r\x1b[2K` + footer to stderr. `\r` returns cursor to line start; `\x1b[2K` clears the line.
- On `stop()`, write `\r\x1b[2K` once more to clear, then let the caller print the final result cleanly.
- Spinner: braille unicode `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` rotated at ~100ms.
- Elapsed format: `M:SS` under 1 minute, `MM:SS` under 1 hour, `HhMMm` at 1 hour and beyond.

**Non-TTY fallback:** if `stream.isTTY` is false (piped, CI, redirected), fall back to plain log lines — emit each state change as a single timestamped line so logs aren't corrupted by ANSI escapes.

**`--json` mode:** the renderer is not instantiated at all.

### 5.6 `lib/transcript.mjs` — log + review file writers

Subscribes to `EventStream` events and writes the log file incrementally. The review file is written only on successful finish. Independent of the renderer — both consume the event stream in parallel.

**Public API:**
```javascript
class TranscriptWriter {
  constructor({ reviewId, workspaceRoot, config });
  attach(eventStream);
  start({ metadata }) → Promise<void>;
  finish({ finalReviewText, status, duration, toolCount, completedAt }) → Promise<void>;
}
```

**File lifecycle (clarified):**

| File | When created | When written | When finalized |
|---|---|---|---|
| `<id>.log.md` | At `start()` | Continuously as events arrive | At `finish()` — frontmatter rewritten with terminal state, `## Final Review` section appended with the canonical text |
| `<id>.review.md` | **Only at `finish()` if `status === 'completed'`** | n/a | Written once with the final review text + matching frontmatter |

**Files live under `<workspaceRoot>/<config.transcript.directory>/`.**

**At `start()`:** create only `<id>.log.md`. Write YAML frontmatter (with `status: running`, `started_at`, `tool_calls: 0`) followed by the `# Opencode Review — ...` header. Frontmatter is written immediately so a crashed or `SIGINT`-killed review still has a meaningful state file. The `<id>.review.md` file does NOT exist until the review completes successfully.

**For each event:** append to `{id}.log.md` using `fs.appendFile`:

```markdown
_Thinking…_

● Read(`src/auth/session.ts`)
  ⎿ (output hidden)

● Bash(`git diff HEAD`)
  ⎿ (output hidden)

● Grep(`useAuth`, glob: `**/*.ts`)
  ⎿ (output hidden)

_Writing report…_

<text deltas appended here as they arrive, so the log streams the final text>
```

Markers:
- `●` for tool calls, followed by `Tool(primary_arg)`.
- `⎿ (output hidden)` beneath each tool call (default). If `transcript.include_reasoning` is also extended later for tool output, this can become the first 3 lines of output.
- `_Thinking…_` italicized for `step-start` and reasoning phases. One marker per phase, not one per token.
- `_Writing report…_` when `text-delta` events start.
- Reasoning text is only expanded when `transcript.include_reasoning = true`. Default is the marker only.

**At `finish()`:**

1. **Always backfill the final review text into `<id>.log.md`'s `## Final Review` section** using the canonical `finalReviewText` parameter passed by the runner. The text deltas streamed during the review may be incomplete (SSE drops, late events arriving after `stop()`, the `--json` flag suppressing renderer attachment but not transcript), so the log can never rely on streamed deltas being authoritative. The streamed-text section in the body of the log is a "live preview"; the canonical review text always lands in `## Final Review` at finalization.
2. **Rewrite the log file's frontmatter atomically** to set `completed_at`, `duration`, `status`, and `tool_calls`.
3. **If `status === 'completed'`:** create `<id>.review.md` with matching frontmatter and the full final review text verbatim. If `status` is `error` / `interrupted` / `cancelled`, the review file is NOT created — `.log.md` is the only artifact for failed reviews.
4. **If status is non-completed**, also append a `## Error` section to `<id>.log.md` with the error message and any partial state.

**Frontmatter rewrite is atomic:** write the updated header to a `.tmp` file, append the rest of the existing content, `rename` over the original. The append-only nature of the rest of the log file means all writes outside frontmatter rewrites are pure `fs.appendFile` calls — no read-modify-write races.

**`tool_calls` frontmatter field — when it's actually written.** Frontmatter is rewritten only at `finish()`, not on every tool event. The `tool_calls` count in frontmatter is the **final** count at completion. During an in-flight review, the live count is held in `EventStream.toolCount` (memory only). The renderer reads it from there for the live footer. Anyone tailing `.log.md` mid-review counts `●` markers if they want a live count — frontmatter is not the source of truth until `finish()` runs. This avoids race conditions between append-only event writes and atomic frontmatter rewrites.

### 5.7 `lib/args.mjs` — CLI argument parser

~100 LOC utility. Parses argv against a schema (`valueOptions`, `booleanOptions`, `aliasMap`) and returns `{ options, positionals }`. Same shape as Codex's `args.mjs` — the file can be ported essentially unchanged.

### 5.7.1 `prompts/review.md` — the review prompt template

Strategy B (the agent reads files itself) means the prompt has to give the Opencode agent enough deterministic information to scope its review correctly. The plugin doesn't ship the diff text; it ships an instruction set that names exactly what to review and how. The template uses `{{VARIABLE}}` interpolation filled in by `buildReviewPrompt(target, cwd)`.

```markdown
You are performing a code review on a project at `{{WORKSPACE}}`.

## Review target

**Mode:** {{TARGET_MODE}}
{{#if TARGET_MODE == "working-tree"}}
**Scope:** All uncommitted changes — staged, unstaged, and untracked files.

To enumerate the changes, run from `{{WORKSPACE}}`:
- `git status --short --untracked-files=all`
- `git diff --cached`  (staged changes)
- `git diff`           (unstaged changes)
- For untracked files, read each one directly with your Read tool.
{{/if}}
{{#if TARGET_MODE == "branch"}}
**Scope:** Commits between `{{BASE_REF}}` and `HEAD`.

To enumerate the changes, run from `{{WORKSPACE}}`:
- `git log --oneline {{BASE_REF}}..HEAD`
- `git diff {{BASE_REF}}...HEAD --stat`
- `git diff {{BASE_REF}}...HEAD`  (full diff if you need it; use --name-only first to scope)
{{/if}}

**Review label:** {{TARGET_LABEL}}

## What to do

1. Use your Bash, Read, and Grep tools to inspect the code under review.
2. For each issue you find, look at the surrounding code via additional Read calls so your review reflects the broader context, not just the changed lines.
3. Group findings by severity: **Critical** (bugs, security, data loss), **High** (correctness, performance, design flaws), **Medium** (maintainability, testability), **Low** (style, naming, documentation).
4. For each finding, cite the file and line number using the form `path/to/file.ts:42`.
5. Be specific about the *fix*. Don't say "consider X" — say what to change and why.

## Output format

Return your review as Markdown with these sections, in order:

```
# Code Review

## Summary
<2-3 sentence high-level assessment>

## Findings

### Critical
- **`path/to/file.ts:42`** — <one-line title>
  <Multi-paragraph explanation of the issue and the fix>

### High
...

### Medium
...

### Low
...

## What's good
<Brief positive observations — what the change does well>

## Recommendation
<Approve / Approve with changes / Request changes — and why>
```

## Constraints

- Review only the target scope above. Do not make broader recommendations about the codebase.
- Do not modify any files. This is a read-only review.
- If a finding requires running code or tests to verify, note that explicitly rather than guessing.
- If the target scope is empty (no actual changes), say so and stop — do not invent issues.
```

**Interpolation variables filled by `buildReviewPrompt`:**

| Variable | Source | Example |
|---|---|---|
| `WORKSPACE` | absolute `cwd` | `/Users/foo/projects/auth-service` |
| `TARGET_MODE` | `target.mode` | `working-tree` or `branch` |
| `BASE_REF` | `target.baseRef` | `origin/main` (only when mode is `branch`) |
| `TARGET_LABEL` | `target.label` | `working tree (5 files modified, 2 untracked)` |

The `{{#if ...}}` blocks are simple conditional sections — `buildReviewPrompt` strips one branch based on `target.mode`. No template engine; the interpolation logic is ~30 LOC inside `prompts.mjs` (a small helper module not in the lib list because it's a single function).

### 5.8 `lib/git.mjs` — review target resolution

Resolves `--base` and `--scope` flags into a canonical review target. No diff collection (Strategy B); the target is interpolated into the prompt template so the agent knows what to look at.

**Public API:**
```javascript
resolveReviewTarget(cwd, { base?: string, scope?: string }) → ReviewTarget

// ReviewTarget shape:
// { mode: 'working-tree' | 'branch', baseRef?: string, label: string }
```

**Resolution rules:**

- `--scope auto` (default): if `git status --porcelain` is non-empty, mode is `working-tree`. Else if HEAD is ahead of upstream, mode is `branch` with `baseRef = upstream`. Else throw `GitError`: "Nothing to review."
- `--scope working-tree`: force working-tree mode; ignore `--base`.
- `--scope branch`: force branch mode. Default `baseRef` is upstream (`git rev-parse --abbrev-ref HEAD@{upstream}`); if no upstream, fall back to `main`/`master`; if neither exists, throw `GitError`.
- `--base <ref>` with `--scope auto`: implies `--scope branch` with that base.
- `--base <ref>` with `--scope working-tree`: ignored with a stderr warning.

**Validation:** check that `baseRef` resolves (`git rev-parse --verify <ref>`) before returning. Missing ref → `GitError` with a "git fetch" hint.

**Label** is human-readable for the review header: `"working tree (5 files modified, 2 untracked)"` or `"HEAD…origin/main (12 commits)"`.

---

## 6. Configuration Schema

### File location

`~/.config/opencode-plugin/config.toml` — XDG-style, cross-platform via `path.join(os.homedir(), '.config', 'opencode-plugin', 'config.toml')`. Created on first run with the default template if missing.

### Schema

```toml
# ~/.config/opencode-plugin/config.toml

[server]
url = "http://localhost:4096"
# password = "your-bearer-token-if-set"

[commands.review]
agent    = "code-reviewer"
provider = "poe"
model    = "openai/gpt-5.4"

[transcript]
directory         = ".opencode/reviews"
include_reasoning = false
```

### Field reference

| Section | Field | Required | Type | Default | Notes |
|---|---|---|---|---|---|
| `server` | `url` | yes | URL string | `http://localhost:4096` | Where Opencode is listening |
| `server` | `password` | no | string | (none) | Bearer token if Opencode is running with auth |
| `commands.review` | `agent` | yes | string | `code-reviewer` | Opencode agent name |
| `commands.review` | `provider` | no¹ | string | (none) | Pairs with `model` |
| `commands.review` | `model` | no¹ | string | (none) | Pairs with `provider` |
| `transcript` | `directory` | yes | relative path | `.opencode/reviews` | Where log + review files go |
| `transcript` | `include_reasoning` | yes | boolean | `false` | Expand `_Thinking…_` markers into full reasoning text |

¹ `provider` and `model` form a pair. Set both or neither.

### Precedence (highest wins)

1. CLI flag (`--model`, `--agent`, `--base`, `--scope`, `--json`)
2. TOML config values
3. Hardcoded defaults shipped with the plugin

### Environment variables (operational only)

Reserved for testing/debugging, not user config:

- `OPENCODE_PLUGIN_CONFIG=/path/to/custom.toml` — override config file location
- `OPENCODE_PLUGIN_DEBUG=1` — verbose logging to a troubleshooting log file

No `OPENCODE_URL`, no `OPENCODE_PASSWORD`. Those go in TOML.

### State storage principle

The `.opencode/reviews/{reviewId}.log.md` frontmatter is the canonical source of truth for review status. No separate `.job.json` files. v1 already needs to write that frontmatter; future commands like `/opencode:status` and `/opencode:cancel` will read it.

Frontmatter fields written by v1:

```yaml
---
id: 2026-04-09T14-32-15-487Z-a3f1
command: /opencode:review --scope working-tree
agent: code-reviewer
provider: poe
model: openai/gpt-5.4
session_id: ses_abc123
workspace: /Users/martinkuek/Documents/Projects/skills
target: working tree (5 files modified)
status: running          # → "completed" | "error" | "interrupted" on finish
started_at: 2026-04-09T14:32:15Z
completed_at: null       # → ISO timestamp on finish
duration: null           # → "15m 08s" on finish
tool_calls: 0            # → final count written at finish() (not updated mid-review)
---
```

**Reserved (not written by v1, future-only):** `pid` (background workers), `worker_args` (background context handoff). Reserving them now means v2's frontmatter parser does not need a schema migration.

### Future overrides (forward reference, NOT in v1)

- Project-local override: `<repo-root>/.config/opencode-plugin/config.toml`, overlays global. Same schema. Loaded by `loadConfig` between TOML global and CLI overrides.
- Per-command sections: `[commands.task]`, `[commands.adversarial-review]`. Schema is already namespaced under `[commands.<name>]` for this expansion.
- Profile indirection: `[profiles.<name>]` blocks for multi-profile use cases like `--profile gpt54-strict`.

---

## 7. Data Flow for `/opencode:review`

End-to-end trace of a foreground invocation.

### Step 0 — Slash command launch

User types `/opencode:review --scope working-tree`. Claude Code reads `skills/review/SKILL.md`, executes the embedded bash command with `$ARGUMENTS` substituted:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/opencode-companion.mjs" review "--scope working-tree"
```

Stdout from this command is returned to the conversation verbatim (per the SKILL.md instruction: "return verbatim").

### Step 1 — Dispatch

`opencode-companion.mjs:main()` switches on the first argv and calls `handleReview(argv)`.

### Step 2 — `handleReview`: thin CLI glue

`handleReview` is intentionally thin: parse flags, load config, resolve target, generate review ID, then call `executeReviewRun` and format its result for stdout. The split between `handleReview` (CLI shell) and `executeReviewRun` (review core) is the v1 shape accommodation that makes background mode cheap to add later.

```javascript
async function handleReview(argv) {
  const { options, positionals } = parseArgs(argv, {
    valueOptions: ["base", "scope", "model", "agent"],
    booleanOptions: ["json"],
  });

  const config = loadConfig({
    overrides: {
      commands: { review: {
        ...(options.model && { model: options.model }),
        ...(options.agent && { agent: options.agent }),
      }},
    },
  });

  const cwd = process.cwd();
  const target = resolveReviewTarget(cwd, {
    base: options.base, scope: options.scope,
  });
  const reviewId = makeReviewId();
  // makeReviewId() format: `2026-04-09T14-32-15-487Z-a3f1` —
  //   ISO timestamp with millisecond precision PLUS a 4-char random hex suffix.
  //   The combo guarantees uniqueness even for two simultaneous reviews started
  //   in the same millisecond. Sorts chronologically in `ls` thanks to the
  //   leading timestamp.

  const result = await executeReviewRun({
    config, reviewId, cwd, target, jsonMode: options.json, command: argv,
  });

  if (options.json) {
    process.stdout.write(JSON.stringify(result, null, 2));
  } else {
    process.stdout.write(result.finalReviewText);
    process.stdout.write(`\n\n— saved to ${result.reviewPath}\n`);
  }
}
```

### Step 3 — `executeReviewRun`: the review core

`executeReviewRun` is the review runner core — no `process.exit`, no argv parsing, no CLI shell logic. It performs network I/O (HTTP + SSE) and filesystem I/O (transcript writes), so it isn't pure in the functional sense, but it's *self-contained*: it takes a fully-resolved context, returns a result object, and throws typed errors. Future background mode adds a worker subcommand that calls this same function — zero changes to its body.

```javascript
async function executeReviewRun({ config, reviewId, cwd, target, jsonMode, command }) {
  // 3a. Health check — fail fast with friendly error if server is down
  const health = await healthCheck(config).catch(() => ({ healthy: false }));
  if (!health.healthy) {
    throw new OpencodeUnreachableError(
      `Can't reach Opencode at ${config.server.url}.`,
      { suggestion: `Start the server in another terminal:\n  opencode serve\n\nThen re-run the command.` }
    );
  }

  // 3b. Create session scoped to the project directory
  const { id: sessionId } = await createSession(config, { directory: cwd });

  // 3c. Build prompt from template
  const prompt = buildReviewPrompt(target, cwd);

  // 3d. Wire up event stream + parallel consumers
  const stream = new EventStream(config, sessionId);
  const renderer = jsonMode ? null : new StatusRenderer();
  const transcript = new TranscriptWriter({ reviewId, workspaceRoot: cwd, config });

  transcript.attach(stream);
  renderer?.attach(stream);

  // 3e. Write transcript frontmatter (status: running) BEFORE any HTTP work
  // so a Ctrl-C between here and the connect still leaves a meaningful state file.
  const startedAt = new Date();
  await transcript.start({
    metadata: {
      id: reviewId,
      command: `/opencode:review ${command.join(" ")}`,
      agent: config.commands.review.agent,
      provider: config.commands.review.provider,
      model: config.commands.review.model,
      sessionId,
      workspace: cwd,
      target: target.label,
      startedAt: startedAt.toISOString(),
      status: "running",
    },
  });

  // 3f. Open the SSE stream BEFORE sending the prompt — and AWAIT it.
  // This ensures we don't miss early `tool-start` events from a slow SSE connect.
  await stream.start();
  renderer?.start();

  // 3g. Wire SIGINT to graceful cancellation. The handler aborts both the
  // SSE stream and the in-flight POST so the `finally` block can finalize
  // the transcript with status: cancelled. v1 only handles SIGINT once —
  // a second Ctrl-C terminates the process immediately.
  const abortController = new AbortController();
  let cancelledByUser = false;
  const sigintHandler = () => {
    if (cancelledByUser) {
      // Second SIGINT — give up on graceful cleanup and exit hard.
      process.exit(130);
    }
    cancelledByUser = true;
    process.stderr.write("\nCancelling… (press Ctrl-C again to force-quit)\n");
    abortController.abort();
  };
  process.on("SIGINT", sigintHandler);

  // 3h. BLOCKING: send the prompt and wait for the final message
  let response;
  let runError = null;
  try {
    response = await sendMessage(config, sessionId, {
      directory: cwd,
      prompt,
      agent: config.commands.review.agent,
      model: config.commands.review.provider && config.commands.review.model
        ? { providerID: config.commands.review.provider, modelID: config.commands.review.model }
        : undefined,
      signal: abortController.signal,
    });
    if (response.info.finish !== "stop") {
      throw new OpencodeResponseError(
        `Opencode review ended unexpectedly (finish: '${response.info.finish}').`,
        { suggestion: `Transcript: ${config.transcript.directory}/${reviewId}.log.md` }
      );
    }
  } catch (err) {
    runError = err;
  } finally {
    process.off("SIGINT", sigintHandler);

    // Drain the SSE stream — wait for `done` or a quiescence window so late
    // events (e.g. final `session.idle`) aren't lost when we stop the stream.
    try {
      await stream.waitForDone({ timeoutMs: 2000 });
    } catch { /* timeout is fine — proceed to stop */ }

    renderer?.stop();
    await stream.stop();

    // Map error class to terminal status. Order matters — most specific first.
    const resultStatus = (() => {
      if (cancelledByUser) return "cancelled";
      if (!runError) return "completed";
      if (runError instanceof OpencodeUnreachableError) return "error";
      if (runError instanceof OpencodeApiError)         return "error";
      if (runError instanceof OpencodeResponseError)    return "error";
      // Anything else (network drop mid-stream, unexpected) is "interrupted"
      return "interrupted";
    })();

    // Canonical final review text — extracted from the response if we got one,
    // empty string otherwise. The transcript writer ALWAYS uses this value
    // (not streamed deltas) as the source of truth for the `## Final Review`
    // section in the log file.
    const finalReviewText = response
      ? response.parts.filter(p => p.type === "text" && p.text).map(p => p.text).join("\n\n")
      : "";

    const completedAt = new Date();
    await transcript.finish({
      finalReviewText,
      status: resultStatus,
      duration: formatDuration(completedAt - startedAt),
      toolCount: stream.toolCount,
      completedAt: completedAt.toISOString(),
      errorMessage: runError?.message,
    });

    if (runError) throw runError;  // re-throw after transcript is finalized
  }

  // 3g. Build and return result object
  const finalReviewText = response.parts
    .filter(p => p.type === "text" && p.text)
    .map(p => p.text)
    .join("\n\n");

  return {
    reviewId,
    sessionId,
    target,
    finalReviewText,
    logPath: `.opencode/reviews/${reviewId}.log.md`,
    reviewPath: `.opencode/reviews/${reviewId}.review.md`,
    status: "completed",
    durationMs: new Date() - startedAt,
    toolCount: stream.toolCount,
  };
}
```

### Step 4 — Concurrency model during the blocking POST

Critical sequencing: SSE connection must be **fully established** before the prompt is sent, so no early `tool-start` events are missed during the SSE handshake. After the prompt is sent, three things run concurrently until the POST returns, then a brief drain phase ensures late events are captured:

```
  T=0  await stream.start()
       │   GET /global/event → 200 OK headers
       │   reader detached, parsing chunks
       │
  T=Δ  Promise resolves; SSE is connected and reading
       │
       │ Now safe to send the prompt:
       ▼
  T=Δ  sendMessage(...) launched (returns Promise)
       │
       │   ┌──────────────────────────┬─────────────────────────┐
       │   │ Main thread              │ SSE reader (background) │  Renderer tick
       │   │ POST blocked, waiting    │ pulls + parses chunks   │  setInterval 250ms
       │   │                          │       │                  │       │
       │   │                          │       ▼                  │       │
       │   │                          │ filter by sessionID      │       │
       │   │                          │ emit semantic event      │       │
       │   │                          │       │                  │       │
       │   │                          │       ├─→ renderer state │       │
       │   │                          │       │                  │       │
       │   │                          │       └─→ transcript     │       ▼
       │   │                          │           append .log.md │  write footer
       │   │                          │                          │  to stderr
       │   ▼                          │                          │
       │ response arrives             │                          │
       │ (15+ minutes later)          │                          │
       │   │                          │                          │
       │   ▼                          │                          │
  T=N  await stream.waitForDone({ timeoutMs: 2000 })
       │   waits for 'done' event or 2s quiescence so late
       │   `session.idle` / `tool-end` events aren't lost
       │   │
       │   ▼
  T=N+ε renderer.stop()
       │ await stream.stop()
       │ await transcript.finish({ finalReviewText: <from response> })
       │
       ▼
  handler writes final review to stdout
```

**Why the drain matters:** Opencode emits `session.idle` (and possibly final `tool-end`s) *after* the blocking POST returns its body. Without `waitForDone`, the `finally` block tears down the SSE stream the instant the POST resolves, dropping those late events. The transcript would undercount tools and the log would stop a fraction of a second too early.

User sees:

**On stderr (ephemeral, rewritten in place):**
```
⠙ Opencode reviewing · Reading src/auth/session.ts · Tool calls: 12 · 2m34s
```

**On stdout (when the POST returns):**
```markdown
# Code Review

## Findings
...

— saved to .opencode/reviews/2026-04-09T14-32-15-487Z-a3f1.review.md
```

**`tail -f .opencode/reviews/2026-04-09T14-32-15-487Z-a3f1.log.md`** in another terminal during the review shows the chat-transcript log filling up live.

### Step 5 — Exit codes

| Code | Meaning |
|---|---|
| 0 | Review completed (`finish === "stop"`) |
| 1 | Runtime/IO failure (server unreachable, network drop, malformed response, git error) |
| 2 | Misuse/configuration (invalid CLI args, malformed TOML, schema violation) |

---

## 8. Error Handling

### Error class taxonomy

Five typed error classes plus a base. All extend `OpencodePluginError` so the dispatcher's top-level catch can format them uniformly.

```javascript
class OpencodePluginError extends Error {
  constructor(message, { exitCode = 1, suggestion } = {}) {
    super(message);
    this.exitCode = exitCode;
    this.suggestion = suggestion;
  }
}

class ConfigError              extends OpencodePluginError { /* exitCode = 2 */ }
class CliArgumentError         extends OpencodePluginError { /* exitCode = 2 */ }
class GitError                 extends OpencodePluginError { /* exitCode = 1 */ }
class OpencodeUnreachableError extends OpencodePluginError { /* exitCode = 1 */ }
class OpencodeApiError         extends OpencodePluginError { /* exitCode = 1 */ }
class OpencodeResponseError    extends OpencodePluginError { /* exitCode = 1 */ }
```

`suggestion` is the actionable guidance — separated from `message` so error rendering can format it distinctly.

### Failure mode mapping

| Stage | Failure | Class | Terminal status | User sees |
|---|---|---|---|---|
| args.mjs | Unknown flag | `CliArgumentError` | n/a (pre-transcript) | Suggested correction; exit 2 |
| args.mjs | Invalid value | `CliArgumentError` | n/a | Expected values listed; exit 2 |
| config.mjs | TOML parse failure | `ConfigError` | n/a | File path + line number; exit 2 |
| config.mjs | Schema validation | `ConfigError` | n/a | Field path + what was expected; exit 2 |
| config.mjs | Paired-field violation | `ConfigError` | n/a | Both-or-neither rule explained; exit 2 |
| git.mjs | Not a git repo | `GitError` | n/a | "Run from inside a git repo"; exit 1 |
| git.mjs | Nothing to review | `GitError` | n/a | "Working tree clean and HEAD matches upstream"; exit 1 |
| git.mjs | Unknown ref | `GitError` | n/a | "git fetch" hint; exit 1 |
| client.mjs | Health check failure (pre-session) | `OpencodeUnreachableError` | n/a (no transcript) | Exact `opencode serve` command; exit 1 |
| client.mjs | 401 Unauthorized | `OpencodeApiError` | `error` | "Set [server].password in config.toml"; exit 1 |
| client.mjs | 5xx on session create | `OpencodeApiError` | `error` | "Check opencode serve logs"; exit 1 |
| client.mjs | Network drop mid-POST | `OpencodeApiError` | `error` | "Partial transcript saved to ..."; exit 1 |
| client.mjs | Empty response body | `OpencodeResponseError` | `error` | "Likely unknown agent name"; exit 1 |
| client.mjs | `finish !== "stop"` | `OpencodeResponseError` | `error` | Transcript path included; exit 1 |
| client.mjs | Anything else thrown mid-stream | (uncaught propagated) | `interrupted` | Generic message; partial transcript; exit 1 |
| executeReviewRun | User pressed Ctrl-C | (AbortError from signal) | `cancelled` | "Cancelled by user"; partial transcript; exit 130 |
| handleReview | Empty `finalReviewText` | (warning, not error) | `completed` | Stderr warning, exit 0, transcript saved |

**Class → terminal status mapping** (used in `executeReviewRun`'s `finally` block):

```
cancelledByUser ............ → "cancelled"   (always wins)
runError == null ........... → "completed"
OpencodeUnreachableError ... → "error"       (rare here — usually pre-transcript)
OpencodeApiError ........... → "error"
OpencodeResponseError ...... → "error"
anything else .............. → "interrupted"
```

The `error` vs `interrupted` distinction matters for future `/opencode:status`: `error` means "the review failed for an identifiable reason"; `interrupted` means "the review's state is unknown — partial output may or may not be salvageable."

### Exemplary error: server unreachable

This is the failure every new user hits on first run. Format:

```
Error: Can't reach Opencode at http://localhost:4096.

Start the server in another terminal:
  opencode serve

Then re-run: /opencode:review --scope working-tree

If your server runs on a different URL, set [server].url in
~/.config/opencode-plugin/config.toml.
```

### Empty response body — special case

Per platform-knowledge research on Opencode v1.3.15: the server returns HTTP 200 with `Content-Length: 0` when the agent name is invalid (instead of a 4xx). `client.mjs` checks `if (!body || body.length === 0)` and throws `OpencodeResponseError` with "likely unknown agent name '${agent}'" as the leading hint, since this is the most common cause >90% of the time.

### Partial-transcript preservation

When a review fails mid-flight (network drop, malformed response), the transcript writer's events have already accumulated in the log file. The `finally` block calls `transcript.finish()` with `status: error` or `status: interrupted`, which:

1. Updates frontmatter with `completed_at` (timestamp of failure), `status`, and `tool_calls: <last known count>`.
2. Appends a `## Error` section to the log file with the error message.
3. Does NOT write `.review.md` (no completed review to save).

A user whose 12-minute review crashes at minute 11 still has 11 minutes of activity log to understand what the agent was doing.

### SIGINT handling (v1)

15-30 minute reviews make Ctrl-C likely. v1 ships with a minimal `SIGINT` handler that does the right thing without bloating scope:

1. **First Ctrl-C:** abort the in-flight `sendMessage` POST via `AbortController`, print "Cancelling…" to stderr, let the `finally` block in `executeReviewRun` run. The transcript is finalized with `status: cancelled`, `completedAt`, and `tool_calls = <whatever was captured>`. Exit 130 (standard for "terminated by SIGINT").
2. **Second Ctrl-C (within the cleanup window):** `process.exit(130)` immediately. The transcript may end up with stale frontmatter (`status: running`), accepted as the price of impatience. The user knows what they did.

This is one signal handler, ~15 LOC, integrated into `executeReviewRun` (see step 3g of §7). It eliminates the most common stranded-state scenario without expanding the v1 surface area.

### Deliberately not handled in v1

- **Automatic retries.** No retry on network drop. The error tells the user to re-run; they decide. Auto-retry is a foot-gun for 15-30 minute reviews (silently doubling cost on a flaky network).
- **Backoff for transient 5xx.** Same reason. Surfacing failure quickly is better than hiding it.
- **`SIGTERM` and other signals.** Only `SIGINT` is handled. `SIGTERM` (e.g. from a parent killing the process) lets the OS terminate immediately. Acceptable for a foreground command — `SIGTERM` is rare in interactive use.
- **Stale-state recovery.** If a `SIGINT` cleanup fails or the process is killed via `SIGKILL`, the transcript is left at `status: running`. v2's `/opencode:status` will add a stale-detection pass (look for `status: running` log files where `started_at` is older than N hours and no PID is alive).
- **Server-side errors during the review.** `events.mjs` propagates `session.error` as an error event, which terminates the stream cleanly. The blocking POST eventually returns with `finish !== "stop"`, handled in 3h above.

---

## 9. Testing Strategy

Three layers, smallest to largest. Mock the Opencode server entirely; integration testing against real Opencode is opt-in and manual.

### Test runner

`node:test` (built-in to Node 18+). Zero dev dependencies. Built-in `mock` API for the few places that need to mock `fetch` and `child_process`. Tests live at `tests/<module>.test.mjs` mirroring `scripts/lib/<module>.mjs`, plus a `tests/integration/` folder for end-to-end tests against a fake server.

### Layer 1 — Pure unit tests (the bulk)

For modules with no I/O.

| File | Covers |
|---|---|
| `tests/args.test.mjs` | argv parsing, alias resolution (`-m` → `--model`), boolean vs value, unknown options, missing values, end-of-options `--` |
| `tests/config.test.mjs` | TOML parsing, every validation rule, CLI override merging, default merging, error class + field path on failure |
| `tests/events.test.mjs` | Canned SSE → semantic events. Every Opencode event type, session-ID filtering, tool state transitions, text delta accumulation, reasoning gating, malformed-event handling |
| `tests/render.test.mjs` | Phase label transitions, counter formatting, elapsed timer formatting (M:SS, MM:SS, HhMMm crossover), spinner rotation, `--json` mode disabling, non-TTY fallback |
| `tests/transcript.test.mjs` | Frontmatter shape, chat-transcript markers, reasoning gating, atomic frontmatter rewrite, partial-state preservation on error, both files (`.log.md` and `.review.md`) created |
| `tests/git.test.mjs` | Real git fixture repos in `os.tmpdir()`. Clean working tree → "nothing to review", dirty → working-tree mode, branch ahead → branch mode, missing ref → GitError, scope/base flag interactions |

### Layer 2 — Integration with a fake Opencode server

`tests/fixtures/fake-opencode-server.mjs` is an in-process HTTP server with configurable handlers for:

- `GET /global/health` — defaults to `{healthy: true, version: 'fake'}`; configurable to return 500 or hang
- `POST /session` — defaults to `{id: 'ses_test123'}`; configurable empty body, 401, 500
- `POST /session/:id/message` — configurable: blocking delay, response body, error injection
- `GET /global/event` — SSE stream with configurable events to emit, controllable timing

```javascript
const server = await startFakeServer({
  health: { healthy: true },
  message: {
    delayMs: 100,
    response: { info: { finish: 'stop' }, parts: [{type: 'text', text: '...'}] },
  },
  events: [
    { delayMs: 10, type: 'session.status', properties: { sessionID: 'ses_test123', status: { type: 'busy' } } },
    { delayMs: 50, type: 'message.part.updated', properties: { sessionID: 'ses_test123', part: { type: 'tool', tool: 'read', state: { status: 'running' } } } },
  ],
});
```

| File | Covers |
|---|---|
| `tests/integration/client.test.mjs` | `healthCheck`, `createSession`, `sendMessage` against the fake. Empty-body-means-bad-agent edge case. Directory query param. Bearer auth header forwarding. |
| `tests/integration/review-flow.test.mjs` | Full `executeReviewRun` against fake server with canned event stream. Asserts on: transcript files written, renderer final state, returned result object shape, failure injection at each stage produces the right error class. |

### Layer 3 — Smoke test against real Opencode (opt-in)

One test, gated behind `OPENCODE_PLUGIN_REAL_SMOKE=1`. Runs `opencode serve` in a child process, executes a tiny review against a 5-line throwaway file in a temp git repo, asserts non-empty output. Skipped in CI by default.

### What we deliberately don't test in v1

- Actual review quality (non-deterministic GPT-5.4 outputs).
- SKILL.md rendering inside Claude Code (Anthropic's parser; if `claude --plugin-dir ... --debug` shows it, we trust it).
- Background mode (doesn't exist).
- Long-running reviews (Layer 2 uses 100ms responses; nothing about the code path differs at 30 minutes).
- Opencode SDK upgrades (we don't use the SDK; integration tests catch API drift).

### CI

GitHub Actions, single workflow: checkout, setup Node 20, `npm install`, `node --test`. No matrix across Node versions in v1 (Node 20+ floor). No publish step until distribution is set up.

---

## 10. Extensibility (Forward References)

Each capability lists the v1 hook that makes it cheap and what specifically would change. None of these are in v1 scope.

### Background-mode reviews (`--background`)

**v1 hooks:** `executeReviewRun` extracted from `handleReview`; frontmatter as canonical state; `pid` and `worker_args` reserved frontmatter fields.

**To add:**
- New `review-worker` subcommand in `opencode-companion.mjs` that reads worker context from a temp file and calls `executeReviewRun` unchanged. ~50 LOC.
- New `--background` flag in `handleReview` that spawns the detached worker via `child_process.spawn(..., { detached: true, stdio: 'ignore' }).unref()`, writes the context file, prints `{reviewId, logPath}` and exits. ~30 LOC.

Zero changes to `executeReviewRun`.

### `/opencode:status`, `/opencode:result`, `/opencode:cancel`

**v1 hooks:** "frontmatter is the state" principle. Every review writes its full state to `.opencode/reviews/{id}.log.md` frontmatter incrementally.

**To add:**
- `handleStatus(argv)` — globs `.opencode/reviews/*.log.md`, parses frontmatter, prints a sorted table. ~60 LOC.
- `handleResult(argv)` — reads `.opencode/reviews/{id}.review.md`, prints to stdout. ~20 LOC.
- `handleCancel(argv)` — reads `pid` and `session_id` from frontmatter, calls the `POST /session/{id}/abort` endpoint documented in §5.3's endpoint contracts table (reserved for v2 use), sends SIGTERM to the worker PID, updates frontmatter to `status: cancelled`. ~50 LOC.
- Three new SKILL.md files. ~20 LOC each.

### `/opencode:task` (generic prompt dispatch)

**v1 hooks:** `[commands.<name>]` namespacing in TOML. v1 ships `[commands.review]`; adding `[commands.task]` is purely additive.

**To add:** `skills/task/SKILL.md` + `handleTask(argv)` + `executeTaskRun` (sister function to `executeReviewRun`, same composition pattern with a different prompt template). Transcript, event stream, renderer, client all reused unchanged.

### `/opencode:adversarial-review`

Same as `/opencode:review` but uses a different prompt template that interpolates user-provided focus text. ~30 LOC delta.

### Project-local config overlay

**v1 hook:** `loadConfig` already takes a `configPath` parameter (used for testing). Generalising to layered loading is a small change.

**To add:** `loadConfig` accepts `projectRoot`. If `<projectRoot>/.config/opencode-plugin/config.toml` exists, it's loaded as an additional overlay between TOML global and CLI overrides. ~20 LOC.

### Profile indirection

**v1 hook:** `[profiles.<name>]` reservation in §4.

**To add:** `--profile <name>` CLI flag. Profile lookup in `loadConfig` after per-command defaults but before CLI overrides. ~40 LOC.

### Streaming text deltas to terminal

**v1 hook:** `events.mjs` already emits `text-delta` events; renderer doesn't render them (deliberate UX choice).

**To add:** opt-in CLI flag or config field. Renderer subscribes to `text-delta` and prints above the status footer (footer pinned via cursor save/restore). ~30 LOC plus careful ANSI handling.

### Distribution polish (marketplace publishing)

**v1 hook:** directory is already self-contained per §3 design. `package.json` is minimal and complete.

**To add:** `scripts/dist/opencode-plugin.sh` (the `git subtree split` workflow), `.github/workflows/release.yml`, marketplace metadata files. ~30 lines of YAML/shell plus marketplace submission paperwork.

### Explicitly NOT prepared for in v1

- Multiple concurrent reviews from one user.
- Multi-machine job tracking.
- Opencode plugin / sub-agent orchestration from the plugin side.
- OAuth flows for the Opencode server password.

These would require non-trivial v1 changes if added later, and we accept that cost rather than over-design now.

---

## 11. Distribution Strategy (Forward Reference)

The plugin is designed for monorepo development with on-demand standalone-repo projection via `git subtree split`. Not in v1 scope but the directory layout supports it without modification.

**One-time setup per distributable:**

```bash
# Create the empty github repo first, then:
git remote add dist-opencode git@github.com:martinkuek/opencode-plugin-cc.git
```

**Sync script — `scripts/dist/opencode-plugin.sh`:**

```bash
#!/usr/bin/env bash
set -euo pipefail
git subtree split --prefix=plugins/opencode -b dist/opencode-plugin
git push -f dist-opencode dist/opencode-plugin:main
git branch -D dist/opencode-plugin
```

The skills monorepo is the source of truth. Distribution repos are projections. Force-push is correct because the projection always reflects the monorepo's current state.

**Contribution flow:** redirect contributors to the monorepo via `CONTRIBUTING.md` in the distribution repo. If accepting external PRs becomes worthwhile later, `git subtree pull --prefix=plugins/opencode dist-opencode main` brings them back in.

---

## 12. Open Questions for Implementation

These are deliberately deferred to implementation time, not blockers for the spec:

1. **`argument-hint` and `allowed-tools` frontmatter on SKILL.md** — verify these fields work the same way they do on legacy command markdown. The Codex plugin uses both. If renamed/scoped differently for skills, adapt.
2. **Spinner frame rate vs renderer tick** — 100ms spinner inside a 250ms tick is fine in principle, but verify the visual feel. If the spinner stutters, drop to 250ms throughout.
3. **`smol-toml` vs alternatives** — `@iarna/toml` is the most popular but unmaintained. `smol-toml` is the maintained replacement. If `smol-toml` has any blocker we discover during implementation, fall back to writing a minimal TOML reader (the v1 schema is simple enough to parse by hand if needed).
4. **`fetch` + AbortController on Node 20** — Node's built-in `fetch` supports `signal: AbortController.signal`. Verify the abort actually closes the underlying TCP socket (not just rejects the Promise) on Node 20 specifically — if not, fall back to `https.request` with manual stream reading and `req.destroy()` on abort.
5. **Opencode `session.idle` timing** — the §7 drain mechanism (`waitForDone({ timeoutMs: 2000 })`) assumes `session.idle` arrives within ~2s of the blocking POST returning. If real-world testing shows it sometimes arrives later (or sometimes never), adjust the timeout or change the drain to "stop after N seconds with no events" instead of "wait for done."

None of these block writing the implementation plan.

---

**End of design.**
