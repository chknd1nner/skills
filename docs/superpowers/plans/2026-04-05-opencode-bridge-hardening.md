# OpenCode Bridge Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four issues identified by GPT-5.4 cross-model review: per-project server with auto-port selection, atomic file writes, SSE thread ordering, and test hardening.

**Architecture:** Primary code changes are in `.claude/hooks/intercept-review-agents.py` and its test file. The refactor also updates the parent spec and setup guide so the living documentation remains sufficient to reconstruct the implementation. Port resolution is a new function; atomic writes and SSE fix are surgical edits to existing functions. Tests are strengthened with new assertions and new test cases.

**Tech Stack:** Python 3 stdlib only (socket, os, hashlib, json, subprocess, threading)

---

### Task 1: Atomic file writes

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py:110-132` (write_status, write_result)
- Modify: `.claude/hooks/test_intercept_review_agents.py:328-370` (file helper tests)

- [ ] **Step 1: Write test for atomic write_status**

Add a test that verifies `write_status()` writes the new content to a temp file and only replaces the final file via `os.replace()`. The assertion should observe the system immediately before the replace call: temp file contains the new content, final file still contains the old content.

In `.claude/hooks/test_intercept_review_agents.py`, add after the existing `test_write_status_overwrites` test (line ~341):

```python
def test_write_status_atomic_replace(tmp_path, monkeypatch):
    """write_status writes to a temp file, then atomically replaces the final file."""
    import os

    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'atomic-test', 'PENDING')
    tasks = tmp_path / 'project' / '.opencode' / 'tasks'
    final = tasks / 'atomic-test.status'
    replace_calls = []
    real_replace = os.replace

    def fake_replace(src, dst):
        replace_calls.append((src, dst))
        assert src == str(final) + '.tmp'
        assert dst == str(final)
        assert final.read_text() == 'PENDING'
        assert (tasks / 'atomic-test.status.tmp').read_text() == 'COMPLETE'
        real_replace(src, dst)

    monkeypatch.setattr(_hook.os, 'replace', fake_replace)

    _hook.write_status(cwd, 'atomic-test', 'COMPLETE')

    assert replace_calls == [(str(final) + '.tmp', str(final))]
    assert final.read_text() == 'COMPLETE'
    assert not (tasks / 'atomic-test.status.tmp').exists()
```

- [ ] **Step 2: Write test for atomic write_result**

Add after the new test:

```python
def test_write_result_atomic_replace(tmp_path, monkeypatch):
    """write_result writes to a temp file, then atomically replaces the final file."""
    import os

    cwd = str(tmp_path / 'project')
    _hook.write_result(cwd, 'atomic-test', 'Old content')
    tasks = tmp_path / 'project' / '.opencode' / 'tasks'
    final = tasks / 'atomic-test.result.md'
    replace_calls = []
    real_replace = os.replace

    def fake_replace(src, dst):
        replace_calls.append((src, dst))
        assert src == str(final) + '.tmp'
        assert dst == str(final)
        assert final.read_text() == 'Old content'
        assert (tasks / 'atomic-test.result.md.tmp').read_text() == '## Review\n\nLooks good.'
        real_replace(src, dst)

    monkeypatch.setattr(_hook.os, 'replace', fake_replace)

    _hook.write_result(cwd, 'atomic-test', '## Review\n\nLooks good.')

    assert replace_calls == [(str(final) + '.tmp', str(final))]
    assert final.read_text() == '## Review\n\nLooks good.'
    assert not (tasks / 'atomic-test.result.md.tmp').exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py::test_write_status_atomic_replace .claude/hooks/test_intercept_review_agents.py::test_write_result_atomic_replace -v`

Expected: Both FAIL before the implementation, because the current code writes directly to the final path and never calls `os.replace()`. After the implementation change, both PASS and prove the temp-file-then-replace contract.

- [ ] **Step 4: Implement atomic write_status**

In `.claude/hooks/intercept-review-agents.py`, replace the `write_status` function (lines 110-115):

```python
def write_status(cwd: str, task_id: str, status: str) -> None:
    """Write status string to {task_id}.status file (atomic via rename)."""
    d = tasks_dir(cwd)
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, f'{task_id}.status')
    tmp = final + '.tmp'
    with open(tmp, 'w') as f:
        f.write(status)
    os.replace(tmp, final)
```

- [ ] **Step 5: Implement atomic write_result**

Replace the `write_result` function (lines 127-132):

```python
def write_result(cwd: str, task_id: str, content: str) -> None:
    """Write review content to {task_id}.result.md file (atomic via rename)."""
    d = tasks_dir(cwd)
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, f'{task_id}.result.md')
    tmp = final + '.tmp'
    with open(tmp, 'w') as f:
        f.write(content)
    os.replace(tmp, final)
```

- [ ] **Step 6: Run all tests**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v`

Expected: All tests pass (existing tests still work with atomic writes).

- [ ] **Step 7: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "fix: atomic file writes for status and result (temp file + os.replace)"
```

---

### Task 2: SSE thread ordering fix

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py:344-346` (run_background_process)

- [ ] **Step 1: Fix the ordering**

In `.claude/hooks/intercept-review-agents.py`, find the success path in `run_background_process` (lines 344-346):

```python
    # Wait for SSE thread to drain naturally (server closes stream); then signal stop
    sse.join(timeout=5)
    stop_event.set()
```

Replace with:

```python
    # Signal SSE thread to exit, then wait briefly for clean shutdown
    stop_event.set()
    sse.join(timeout=2)
```

- [ ] **Step 2: Run all tests**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v`

Expected: All tests pass. The fake server closes SSE immediately, so the ordering doesn't affect test results — but the fix eliminates a 5-second delay in production.

- [ ] **Step 3: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py
git commit -m "fix: reverse SSE thread stop/join ordering to eliminate 5s completion delay"
```

---

### Task 3: Port resolution — `is_port_free` and `resolve_port`

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (add new functions after `ensure_server`, before HTTP dispatch section)
- Modify: `.claude/hooks/test_intercept_review_agents.py` (add port resolution tests)

- [ ] **Step 1: Write test for `is_port_free`**

Add to the test file in a new section after the server lifecycle tests:

```python
# ---------------------------------------------------------------------------
# Port resolution
# ---------------------------------------------------------------------------

def test_is_port_free_unused_port():
    """A port with nothing listening is free."""
    assert _hook.is_port_free(59999) is True


def test_is_port_free_used_port(fake_opencode):
    """A port with a server listening is not free."""
    server = fake_opencode()
    assert _hook.is_port_free(server.port) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py::test_is_port_free_unused_port .claude/hooks/test_intercept_review_agents.py::test_is_port_free_used_port -v`

Expected: FAIL with `AttributeError: module 'hook' has no attribute 'is_port_free'`

- [ ] **Step 3: Implement `is_port_free`**

Add to `.claude/hooks/intercept-review-agents.py` after the `ensure_server` function, before the HTTP dispatch section. Also add `import socket` and `import hashlib` to the imports at the top of the file:

```python
import hashlib
import socket
```

```python
def is_port_free(port: int) -> bool:
    """Check if a port is free by attempting a TCP connect."""
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return False  # something is listening
    except (ConnectionRefusedError, OSError):
        return True  # nothing listening — port is free
```

- [ ] **Step 4: Run `is_port_free` tests**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py::test_is_port_free_unused_port .claude/hooks/test_intercept_review_agents.py::test_is_port_free_used_port -v`

Expected: Both PASS.

- [ ] **Step 5: Write test for `resolve_port` with `OPENCODE_PORT` override**

```python
def test_resolve_port_env_override():
    """OPENCODE_PORT set → return that port, skip auto-selection."""
    port, source = _hook.resolve_port('/tmp/test-project')
    # When OPENCODE_PORT is not set in env, this won't be 'override'
    # We test the override path by calling with env set
    import os
    old = os.environ.get('OPENCODE_PORT')
    try:
        os.environ['OPENCODE_PORT'] = '12345'
        port, source = _hook.resolve_port('/tmp/test-project')
        assert port == 12345
        assert source == 'env'
    finally:
        if old is None:
            os.environ.pop('OPENCODE_PORT', None)
        else:
            os.environ['OPENCODE_PORT'] = old
```

- [ ] **Step 6: Write test for `resolve_port` with port file**

```python
def test_resolve_port_from_file(fake_opencode, tmp_path):
    """Port file exists and server is healthy → return port from file."""
    server = fake_opencode()
    cwd = str(tmp_path / 'project')
    port_dir = tmp_path / 'project' / '.opencode'
    port_dir.mkdir(parents=True)
    (port_dir / 'server.port').write_text(str(server.port))

    import os
    old = os.environ.pop('OPENCODE_PORT', None)
    try:
        port, source = _hook.resolve_port(cwd)
        assert port == server.port
        assert source == 'file'
    finally:
        if old is not None:
            os.environ['OPENCODE_PORT'] = old
```

- [ ] **Step 7: Write test for `resolve_port` with stale port file**

```python
def test_resolve_port_stale_file(tmp_path):
    """Port file exists but server is not healthy → auto-select new port."""
    cwd = str(tmp_path / 'project')
    port_dir = tmp_path / 'project' / '.opencode'
    port_dir.mkdir(parents=True)
    (port_dir / 'server.port').write_text('19999')  # nothing listening here

    import os
    old = os.environ.pop('OPENCODE_PORT', None)
    try:
        port, source = _hook.resolve_port(cwd)
        assert port != 19999
        assert source == 'auto'
        assert 49152 <= port <= 65535
    finally:
        if old is not None:
            os.environ['OPENCODE_PORT'] = old
```

- [ ] **Step 8: Write test for hash collision (port in use)**

```python
def test_resolve_port_skips_used_ports(fake_opencode, tmp_path, monkeypatch):
    """If the hash-derived port is in use, increment to find a free one."""
    server = fake_opencode()
    cwd = str(tmp_path / 'project')

    # Force the hash to land on the fake server's port
    monkeypatch.setattr(_hook, '_hash_port', lambda _cwd: server.port)

    import os
    old = os.environ.pop('OPENCODE_PORT', None)
    try:
        port, source = _hook.resolve_port(cwd)
        assert port != server.port  # should have skipped the used port
        assert source == 'auto'
    finally:
        if old is not None:
            os.environ['OPENCODE_PORT'] = old
```

- [ ] **Step 9: Run tests to verify they fail**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "resolve_port" -v`

Expected: All FAIL with `AttributeError: module 'hook' has no attribute 'resolve_port'`

- [ ] **Step 10: Implement `_hash_port`, `write_port_file`, `read_port_file`, and `resolve_port`**

Add after `is_port_free` in `.claude/hooks/intercept-review-agents.py`:

```python
def _hash_port(cwd: str) -> int:
    """Deterministic starting port in ephemeral range based on cwd hash."""
    h = int(hashlib.md5(cwd.encode()).hexdigest(), 16)
    return (h % 16384) + 49152


def read_port_file(cwd: str) -> int | None:
    """Read .opencode/server.port, return port int or None if missing/invalid."""
    try:
        path = os.path.join(cwd, '.opencode', 'server.port')
        with open(path) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def write_port_file(cwd: str, port: int) -> None:
    """Write port to .opencode/server.port (atomic via rename)."""
    d = os.path.join(cwd, '.opencode')
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, 'server.port')
    tmp = final + '.tmp'
    with open(tmp, 'w') as f:
        f.write(f'{port}\n')
    os.replace(tmp, final)


def resolve_port(cwd: str) -> tuple[int, str]:
    """
    Resolve which port to use for this project's OpenCode server.
    Returns (port, source) where source is 'env', 'file', or 'auto'.
    """
    # 1. Force override from env
    env_port = os.environ.get('OPENCODE_PORT', '')
    if env_port:
        try:
            p = int(env_port)
            if p > 0:
                return p, 'env'
        except ValueError:
            pass

    # 2. Port file fast path
    password = os.environ.get('OPENCODE_SERVER_PASSWORD', '') or None
    file_port = read_port_file(cwd)
    if file_port and health_check(file_port, password):
        return file_port, 'file'

    # 3. Auto-select: hash-seeded scan for free port
    start = _hash_port(cwd)
    for i in range(50):
        candidate = start + i
        if candidate > 65535:
            candidate = 49152 + (candidate - 65535 - 1)
        if is_port_free(candidate):
            return candidate, 'auto'

    # Fallback — shouldn't happen in practice
    return _hash_port(cwd), 'auto'
```

- [ ] **Step 11: Run port resolution tests**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "resolve_port or is_port_free" -v`

Expected: All PASS.

- [ ] **Step 12: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat: port resolution with auto-selection, port file, and env override"
```

---

### Task 4: Wire `resolve_port` into `main()`

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py:387-400` (main function)

- [ ] **Step 1: Update `main()` to use `resolve_port`**

In `.claude/hooks/intercept-review-agents.py`, find the config section in `main()`:

```python
    # Read config
    port = _int_env('OPENCODE_PORT', 4096)
    startup_timeout = _int_env('OPENCODE_STARTUP_TIMEOUT', 10)
    model = os.environ.get('OPENCODE_MODEL', '') or None
    password = os.environ.get('OPENCODE_SERVER_PASSWORD', '') or None

    # Ensure server is running (cwd sets working directory for on-demand starts)
    ok, err = ensure_server(port, startup_timeout, password, cwd=cwd)
```

Replace with:

```python
    # Read config
    startup_timeout = _int_env('OPENCODE_STARTUP_TIMEOUT', 10)
    model = os.environ.get('OPENCODE_MODEL', '') or None
    password = os.environ.get('OPENCODE_SERVER_PASSWORD', '') or None

    # Resolve port (env override → port file → auto-select)
    port, port_source = resolve_port(cwd)
    log(f'port resolved | port={port} | source={port_source}')

    # Ensure server is running (cwd sets working directory for on-demand starts)
    ok, err = ensure_server(port, startup_timeout, password, cwd=cwd)
    if not ok:
        # Always log startup failures regardless of debug mode
        _always_log_failure(err)
        sys.exit(0)

    # Write port file on successful startup (only for auto-selected ports)
    if port_source == 'auto':
        write_port_file(cwd, port)
```

Note: Remove the duplicate `if not ok` block that was already there — the replacement above includes it.

- [ ] **Step 2: Run all tests**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v`

Expected: All tests pass. Existing tests that set `OPENCODE_PORT` in env will hit the `'env'` path. Tests that don't set it will auto-select.

- [ ] **Step 3: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py
git commit -m "feat: wire resolve_port into main hook flow, write port file on auto-select"
```

---

### Task 5: Detection test hardening

**Files:**
- Modify: `.claude/hooks/test_intercept_review_agents.py:271-310` (detection tests)

- [ ] **Step 1: Strengthen interception assertions**

Replace the detection tests that currently only check `returncode == 0`. Find each test and update:

Replace `test_code_reviewer_subagent_detected` (lines 271-277):

```python
def test_code_reviewer_subagent_detected(fake_opencode, tmp_path):
    """subagent_type == 'superpowers:code-reviewer' → intercepted with deny JSON."""
    server = fake_opencode(session_id='sess-detect')
    cwd = str(tmp_path / 'project')
    result = run_hook(
        make_payload('superpowers:code-reviewer', cwd=cwd),
        env={
            'OPENCODE_PORT': str(server.port),
            'OPENCODE_STARTUP_TIMEOUT': '2',
            'OPENCODE_SKIP_POLLER': '1',
        },
    )
    assert result.returncode == 0
    deny = json.loads(result.stdout)
    assert deny['hookSpecificOutput']['permissionDecision'] == 'deny'
```

Replace `test_general_purpose_review_description_detected` (lines 280-283):

```python
def test_general_purpose_review_description_detected(fake_opencode, tmp_path):
    """general-purpose + 'Review...' description → intercepted with deny JSON."""
    server = fake_opencode(session_id='sess-detect-gp')
    cwd = str(tmp_path / 'project')
    result = run_hook(
        make_payload('general-purpose', 'Review spec compliance for Task 1', cwd=cwd),
        env={
            'OPENCODE_PORT': str(server.port),
            'OPENCODE_STARTUP_TIMEOUT': '2',
            'OPENCODE_SKIP_POLLER': '1',
        },
    )
    assert result.returncode == 0
    deny = json.loads(result.stdout)
    assert deny['hookSpecificOutput']['permissionDecision'] == 'deny'
```

Replace `test_review_description_case_insensitive` (lines 286-289):

```python
def test_review_description_case_insensitive(fake_opencode, tmp_path):
    """Detection is case-insensitive on 'review' prefix."""
    server = fake_opencode(session_id='sess-detect-case')
    cwd = str(tmp_path / 'project')
    result = run_hook(
        make_payload('general-purpose', 'REVIEW the implementation', cwd=cwd),
        env={
            'OPENCODE_PORT': str(server.port),
            'OPENCODE_STARTUP_TIMEOUT': '2',
            'OPENCODE_SKIP_POLLER': '1',
        },
    )
    assert result.returncode == 0
    deny = json.loads(result.stdout)
    assert deny['hookSpecificOutput']['permissionDecision'] == 'deny'
```

Replace `test_bypass_flag_not_triggered_by_substring` (lines 302-310):

```python
def test_bypass_flag_not_triggered_by_substring(fake_opencode, tmp_path):
    """BYPASS_HOOK must be at the start of description, not embedded."""
    server = fake_opencode(session_id='sess-detect-bypass')
    cwd = str(tmp_path / 'project')
    result = run_hook(
        make_payload(
            'superpowers:code-reviewer',
            'Please review [BYPASS_HOOK] this code',
            cwd=cwd,
        ),
        env={
            'OPENCODE_PORT': str(server.port),
            'OPENCODE_STARTUP_TIMEOUT': '2',
            'OPENCODE_SKIP_POLLER': '1',
        },
    )
    assert result.returncode == 0
    deny = json.loads(result.stdout)
    assert deny['hookSpecificOutput']['permissionDecision'] == 'deny'
```

- [ ] **Step 2: Run detection tests**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "detected or case_insensitive or substring" -v`

Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add .claude/hooks/test_intercept_review_agents.py
git commit -m "test: strengthen detection tests with deny JSON assertions"
```

---

### Task 6: Auth forwarding test and environment isolation

**Files:**
- Modify: `.claude/hooks/test_intercept_review_agents.py`

- [ ] **Step 1: Write auth forwarding test for message POST (poller path)**

Add a new test in the "Logging and configuration" section. Note: the poller only calls `/message`, not `/session` — session creation happens in the main hook. This test covers auth on the message POST:

```python
def test_auth_header_forwarded_to_message(fake_opencode, tmp_path):
    """OPENCODE_SERVER_PASSWORD is sent as Bearer token on /message POST."""
    server = fake_opencode(session_id='sess-auth', result_text='## Review\n\nOk.')
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'auth-test', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'auth-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-auth',
        task_id='auth-test',
        port=server.port,
        cwd=cwd,
        env={
            'OPENCODE_TIMEOUT': '10',
            'OPENCODE_MODEL': '',
            'OPENCODE_SERVER_PASSWORD': 'test-secret-123',
        },
    )

    # Check /message POST has auth header
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    assert msg_reqs[0]['headers'].get('Authorization') == 'Bearer test-secret-123'
```

Write a second test for auth on session creation via the main hook path:

```python
def test_auth_header_forwarded_to_session_creation(fake_opencode, tmp_path):
    """OPENCODE_SERVER_PASSWORD is sent as Bearer token on /session POST (main hook path)."""
    server = fake_opencode(session_id='sess-auth-hook')
    cwd = str(tmp_path / 'project')
    result = run_hook(
        make_payload('superpowers:code-reviewer', cwd=cwd),
        env={
            'OPENCODE_PORT': str(server.port),
            'OPENCODE_STARTUP_TIMEOUT': '2',
            'OPENCODE_SKIP_POLLER': '1',
            'OPENCODE_SERVER_PASSWORD': 'test-secret-456',
        },
    )
    assert result.returncode == 0

    session_reqs = [r for r in server.requests if r['path'] == '/session' and r['method'] == 'POST']
    assert len(session_reqs) >= 1
    assert session_reqs[0]['headers'].get('Authorization') == 'Bearer test-secret-456'
```

- [ ] **Step 2: Fix environment isolation on all poller tests**

Find every `run_poller` call that sets `env={'OPENCODE_TIMEOUT': '...'}` without also setting `'OPENCODE_MODEL': ''`. Add `'OPENCODE_MODEL': ''` to each one. The affected tests (check each and add if missing):

- `test_background_process_completes_review` (line ~633)
- `test_background_timeout_writes_failed` (line ~658)
- `test_background_server_crash_writes_failed` (line ~679)
- `test_background_extracts_multiple_text_parts` (line ~697)
- `test_background_sse_events_written_to_progress` (line ~725)
- `test_background_prompt_not_accepted` (line ~745)

For each, change `env={'OPENCODE_TIMEOUT': 'N'}` to `env={'OPENCODE_TIMEOUT': 'N', 'OPENCODE_MODEL': ''}`.

- [ ] **Step 3: Run all tests**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v`

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/test_intercept_review_agents.py
git commit -m "test: auth forwarding coverage and OPENCODE_MODEL env isolation on all poller tests"
```

---

### Task 7: Documentation and gitignore updates

**Files:**
- Modify: `.gitignore`
- Modify: `docs/superpowers/opencode-review-hook-setup.md`
- Modify: `docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md`

- [ ] **Step 1: Update `.gitignore`**

Change the existing `.opencode/tasks/` entry to `.opencode/` to cover both `tasks/` and `server.port`:

Find:
```
.opencode/tasks/
```

Replace with:
```
.opencode/
```

- [ ] **Step 2: Update setup guide**

In `docs/superpowers/opencode-review-hook-setup.md`:

Change the `OPENCODE_PORT` row in the env vars table from:

```
| `OPENCODE_PORT` | No | `4096` | Port for OpenCode Server |
```

To:

```
| `OPENCODE_PORT` | No | (auto-selected) | Force-override port (skips auto-selection) |
```

Add after the env vars table paragraph ("For most setups..."):

```markdown
**Port auto-selection:** When `OPENCODE_PORT` is not set, the hook automatically selects a free port for each project and writes it to `.opencode/server.port`. The server persists across sessions — subsequent invocations reuse the same port via the file. Set `OPENCODE_PORT` explicitly if you prefer to manage the server yourself.
```

- [ ] **Step 3: Update parent design spec**

In `docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md`:

Update the Configuration table (line ~271): change `OPENCODE_PORT` default from `4096` to `*(auto)* ` and description to `Force-override port (skips per-project auto-selection)`. Change `OPENCODE_TIMEOUT` default from `300` to `1800`.

In the Server Lifecycle > Discovery section (line ~79-81), replace:

```markdown
On each invocation, the hook tries `GET http://127.0.0.1:{port}/global/health` as a health check. Returns `{"healthy": true, "version": "..."}` when ready. Port is configurable via `OPENCODE_PORT` (default `4096`).
```

With:

```markdown
On each invocation, the hook resolves the port via `resolve_port(cwd)`: first checks `OPENCODE_PORT` env var (force override), then reads `.opencode/server.port` and health-checks that port, then auto-selects a free port by hashing the cwd into the ephemeral range (49152–65535). Health check is `GET http://127.0.0.1:{port}/global/health`, expecting `{"healthy": true}`.
```

In the File Layout section (line ~298), add `.opencode/server.port` to the file listing:

```
.opencode/
  server.port                      # auto-selected port (plain text, atomic write)
  tasks/                           # gitignored, created on first dispatch
    {task_id}.status               # PENDING | COMPLETE | FAILED
    ...
```

In the Result Files section (line ~54-58), add after the file list:

```markdown
Status and result files are written atomically via temp file + `os.replace()`. Readers polling these files are guaranteed to see either the previous state or the new state, never partial content.
```

In the Background Process > Write Result section (line ~218-223), fix the SSE ordering to show `stop_event.set()` before `sse.join()`.

In the API Contract section (line ~399), replace:

```markdown
- **Auth header format:** Not yet tested with `OPENCODE_SERVER_PASSWORD`. Assumed to be a standard header — verify during build.
```

With:

```markdown
- **Auth header format:** `Authorization: Bearer {OPENCODE_SERVER_PASSWORD}`. Sent on health check, session creation, message POST, and SSE subscription. Verified in test suite.
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore docs/superpowers/opencode-review-hook-setup.md docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md
git commit -m "docs: per-project server, atomic writes, auth verification, timeout default"
```

---

### Task 8: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v`

Expected: All tests pass (should be ~45+ tests now).

- [ ] **Step 2: Verify no regressions in hook behaviour**

Run a quick smoke test:

```bash
# Non-review call — should pass through (exit 0, no output)
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","description":"Find files","prompt":"test"},"cwd":"/tmp"}' | python3 .claude/hooks/intercept-review-agents.py
echo "Exit: $?"

# Review call with no server — should fall through gracefully
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"superpowers:code-reviewer","description":"Review","prompt":"test"},"cwd":"/tmp"}' | OPENCODE_STARTUP_TIMEOUT=1 python3 .claude/hooks/intercept-review-agents.py
echo "Exit: $?"
```

Expected: Both exit 0 with no crash.

- [ ] **Step 3: Verify port file is created on dispatch**

After running a real review dispatch (with OpenCode running), check:

```bash
cat .opencode/server.port
```

Expected: Contains a port number in the 49152–65535 range (or the manually configured port if `OPENCODE_PORT` is set).
