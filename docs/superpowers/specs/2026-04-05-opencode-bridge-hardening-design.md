# OpenCode Async Bridge — Hardening Spec

> **Date:** 2026-04-05
> **Parent spec:** 2026-04-03-opencode-async-bridge-design.md
> **Trigger:** GPT-5.4 cross-model review of v2 implementation (first live integration test)

This spec addresses four issues identified during review, plus spec gaps and documentation updates. All changes are to the existing `intercept-review-agents.py` and its test suite.

---

## 1. Per-Project Server with Auto-Port Selection

### Problem

The v2 hook reuses any healthy OpenCode server on the configured port without verifying it's rooted at the correct project directory. Sessions inherit the server's working directory — if the server was started from a different project, the review agent reads the wrong codebase. The `POST /session` API has no `directory` field, so directory binding must happen at the server level.

### Design

Each project gets its own OpenCode server instance. Port selection is automatic with manual override preserved.

#### Port Resolution (`resolve_port(cwd)`)

New function replacing the static `OPENCODE_PORT` lookup. Called before `ensure_server()`.

1. **Force override:** If `OPENCODE_PORT` is set, return it immediately (current behaviour preserved for power users who start their own server).
2. **Port file fast path:** Read `.opencode/server.port` in the project root. If the file exists and a health check passes on that port, return it.
3. **Auto-select:** If the file is missing or stale (server not healthy on that port):
   a. Hash `cwd` (e.g., `hash(cwd) % 16384 + 49152`) to get a starting port in the ephemeral range (49152–65535).
   b. For each candidate port starting from the hash: attempt a TCP connect to `127.0.0.1:<port>`. If connection is refused (nothing listening), the port is free — use it. If connection succeeds (something is listening, whether OpenCode or not), increment and try the next. Cap at 50 attempts before failing. This is a raw socket check, not an OpenCode health check — we just need a free port.
   c. Start `opencode serve --port <picked>` with `cwd=<project root>`.
   d. Write the port number to `.opencode/server.port`.
   e. Return the port.

#### Port file format

Plain text file containing just the port number (e.g., `51423\n`). No JSON, no metadata. Written atomically (temp file + `os.replace()`).

#### `ensure_server()` changes

Signature gains a `cwd` parameter (already partially done in the session fix). The port is resolved before `ensure_server()` is called — `ensure_server()` only handles health check and on-demand startup, not port selection.

#### `OPENCODE_PORT` semantics change

| Before | After |
|---|---|
| Required config (default 4096) | Optional force-override |
| Single global server | Per-project server (auto-selected port) |
| Must be set per project | Only set if you want to pin a specific port |

When `OPENCODE_PORT` is set, the hook skips auto-selection entirely — no port file, no hash. This preserves the current workflow for users who manually start their server.

---

## 2. Atomic File Writes

### Problem

`write_status()` and `write_result()` use `open('w')` + write. A reader polling `.status` can observe empty or partial content during the write window. For a polled IPC protocol, this is a correctness issue.

### Design

Both functions switch to write-to-temp-then-rename:

```python
def write_status(cwd: str, task_id: str, status: str) -> None:
    d = tasks_dir(cwd)
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, f'{task_id}.status')
    tmp = final + '.tmp'
    with open(tmp, 'w') as f:
        f.write(status)
    os.replace(tmp, final)
```

Same pattern for `write_result()` and the new `write_port_file()`.

`os.replace()` is atomic on POSIX (single rename syscall). Readers see either the old content or the new content, never partial.

`append_progress()` is unchanged — it's append-only, readers tolerate partial trailing lines, and atomicity would require rewriting the entire file on each append.

---

## 3. SSE Thread Ordering Fix

### Problem

The current completion path does:

```python
sse.join(timeout=5)   # waits 5s for thread that has no reason to exit
stop_event.set()       # signals after waiting
```

The SSE thread checks `stop_event.is_set()` in its loop, but the event isn't set until *after* the join times out. Every successful review incurs a fixed 5-second delay before `COMPLETE` is written. The test suite masks this because the fake server closes the SSE stream immediately.

### Design

Reverse the order:

```python
stop_event.set()       # signal the thread to exit
sse.join(timeout=2)    # wait briefly for clean shutdown
```

The SSE thread's loop checks `stop_event.is_set()` after processing each event. Once set, it breaks out and the join completes quickly. The 2-second join timeout is a safety net — if the thread is stuck in a blocking `read()`, the daemon flag ensures it dies with the process anyway.

---

## 4. Test Hardening

### Problem

The review identified three test weaknesses:

1. Detection tests assert only `returncode == 0` — doesn't prove whether the hook intercepted or passed through.
2. Auth forwarding is only tested on health check, not on session creation or message POST.
3. `OPENCODE_MODEL` leaks from the host environment into tests that assume no model override.

### Design

#### Detection assertion strengthening

Tests that exercise interception must assert stdout contains valid deny JSON with `permissionDecision: deny`. Tests that exercise pass-through must assert stdout is empty. The returncode check remains but is no longer sufficient alone.

```python
# Interception test
result = run_hook(make_payload('superpowers:code-reviewer', 'Review code', 'test'))
assert result.returncode == 0
deny = json.loads(result.stdout)
assert deny['hookSpecificOutput']['permissionDecision'] == 'deny'

# Pass-through test
result = run_hook(make_payload('Explore', 'Find files', 'test'))
assert result.returncode == 0
assert result.stdout.strip() == ''
```

#### Auth forwarding coverage

New test: set `OPENCODE_SERVER_PASSWORD`, run a full poller cycle, assert the `Authorization: Bearer <password>` header appears on both `/session` POST and `/session/{id}/message` POST requests. The fake server already records headers — this is new assertions only.

#### Environment isolation

All poller tests that don't explicitly test model override must include `'OPENCODE_MODEL': ''` in their env dict. This prevents the host's `OPENCODE_MODEL` from leaking in and causing false failures (already partially done for one test).

#### Port auto-selection tests

New tests for `resolve_port()`:

- Port file exists, server healthy on that port -> returns port from file (no startup)
- Port file exists, server not healthy -> picks new port, starts server, overwrites file
- Port file missing -> hash-based selection, starts server, writes file
- `OPENCODE_PORT` set -> returns that port, ignores file and hash
- Hash collision (port in use by non-OpenCode) -> increments to next free port

---

## 5. Spec and Documentation Updates

### Parent spec updates

Apply to `2026-04-03-opencode-async-bridge-design.md`:

- **Server Lifecycle:** Document per-project server architecture. Replace fixed port with `resolve_port()` flow. Add `.opencode/server.port` to file layout.
- **Result Files:** Add atomic write semantics to the file-handshake contract: "Status and result files are written atomically via temp file + `os.replace()`. Readers are guaranteed to see either the previous state or the new state, never partial content."
- **Configuration:** Change `OPENCODE_PORT` description from "Port for OpenCode Server" to "Force-override port (skips auto-selection). If unset, port is auto-selected per project." Change `OPENCODE_TIMEOUT` default from `300` to `1800`.
- **API Contract:** Remove the "Auth header format: Not yet tested" caveat — replace with confirmed behaviour from new tests.
- **Background Process:** Fix the SSE thread ordering in the "Write Result" section to show `stop_event.set()` before `sse.join()`.

### Setup guide updates

Apply to `docs/superpowers/opencode-review-hook-setup.md`:

- Add `.opencode/server.port` to the file descriptions.
- Document that `OPENCODE_PORT` is now a force-override (auto-selection is default when unset).
- Add note that `.opencode/` should be gitignored.
- Update `OPENCODE_TIMEOUT` default to `1800`.

### Gitignore

Verify `.opencode/` is in project `.gitignore`. Add if missing.

---

## Out of Scope

- **Server shutdown/cleanup** — servers persist until manually killed or machine sleeps. No lifecycle management beyond startup.
- **Multi-server coordination** — each project is independent. No registry of running servers.
- **Server directory validation on reuse** — when `OPENCODE_PORT` is force-set, the hook trusts the user. No check that the server's cwd matches the project.
