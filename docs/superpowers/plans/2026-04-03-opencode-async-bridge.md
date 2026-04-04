# OpenCode Async Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the synchronous Gemini CLI review hook with an asynchronous HTTP-based hook that dispatches reviews to OpenCode Server, runs in the background, and delivers results via file handshake — unblocking the main Claude session during reviews.

**Architecture:** Single Python file (`.claude/hooks/intercept-review-agents.py`) replaces v1 in-place. Same PreToolUse hook interface and detection logic, but instead of blocking on `gemini` CLI, it: (1) ensures OpenCode Server is running, (2) creates a session, (3) writes the prompt to a handshake file and spawns a detached background subprocess (`--poll` mode of the same script), (4) returns a deny with async coordination instructions. The background process sends a blocking `POST /session/{id}/message` (which blocks until the model finishes all tool calls) while concurrently subscribing to the SSE event stream to write a real-time progress transcript. When the POST returns, it writes results to `.opencode/tasks/{id}.result.md` and sets status to `COMPLETE`. All stdlib — no pip dependencies.

**Tech Stack:** Python 3 (stdlib: `json`, `subprocess`, `os`, `sys`, `logging`, `time`, `uuid`, `http.server`, `urllib.request`, `threading`), pytest

**Spec:** `docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `.claude/hooks/intercept-review-agents.py` | Rewrite | v2 hook — async OpenCode dispatch + poller |
| `.claude/hooks/test_intercept_review_agents.py` | Rewrite | v2 test suite with fake OpenCode server |
| `.claude/hooks/archive/intercept-review-agents-v1.py` | Create | Archived v1 Python hook |
| `.gitignore` | Modify | Add `.opencode/tasks/` |

No changes to `.claude/settings.json` — same hook path, same matcher.

---

### Task 1: Archive v1 and update gitignore

**Files:**
- Copy: `.claude/hooks/intercept-review-agents.py` → `.claude/hooks/archive/intercept-review-agents-v1.py`
- Modify: `.gitignore`

- [ ] **Step 1: Archive v1 hook**

```bash
cd /Users/martinkuek/Documents/Projects/skills
cp .claude/hooks/intercept-review-agents.py .claude/hooks/archive/intercept-review-agents-v1.py
```

- [ ] **Step 2: Add `.opencode/tasks/` to gitignore**

Open `.gitignore` and add after the existing entries:

```
# OpenCode async bridge handshake files
.opencode/tasks/
```

- [ ] **Step 3: Verify archive and gitignore**

```bash
diff .claude/hooks/archive/intercept-review-agents-v1.py .claude/hooks/intercept-review-agents.py
# Expected: no differences (identical copy)
grep -n 'opencode' .gitignore
# Expected: line with .opencode/tasks/
```

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/archive/intercept-review-agents-v1.py .gitignore
git commit -m "chore: archive v1 hook and gitignore opencode task files"
```

---

### Task 2: API contract — confirmed findings (pre-verified, no action required)

> **This task was completed before implementation began.** The OpenCode Server API was probed live against v1.3.13 on 2026-04-04. All field names and endpoint behaviours below are confirmed. Implementers should use these values directly — no further verification needed.

**Confirmed values for use in all subsequent tasks:**

| What | Confirmed value |
|---|---|
| Health endpoint | `GET /global/health` → `{"healthy": true, "version": "..."}` |
| Session ID field | `id` (e.g. `"ses_2a9a519..."`) |
| Prompt endpoint | `POST /session/{id}/message` — **synchronous**, blocks until model finishes |
| Request body | `{"parts": [{"type": "text", "text": "..."}], "modelID": "..."}` |
| Completion signal | `response["info"]["finish"] == "stop"` |
| Text extraction | `part["text"]` where `part["type"] == "text"` |
| No async endpoint | `prompt_async` does **not exist** — the blocking POST is the only prompt endpoint |
| SSE stream | `GET /global/event` — `data: {JSON}` lines; `payload.type` and `payload.properties` |
| SSE token event | `message.part.delta` — token string in `properties.delta` |
| SSE tool event | `message.part.updated` with `part.type == "tool"`, state in `part.state` |
| SSE completion events | `session.status` (`{"type":"idle"}`), `session.idle` — fire after POST returns |
| Auth header | Not yet verified — assumed Bearer; verify if `OPENCODE_SERVER_PASSWORD` is used |

- [x] **Verified** — full findings documented in spec section "API Contract — Empirically Verified (2026-04-04)"

---

### Task 3: Test infrastructure — fake OpenCode server fixture

**Files:**
- Rewrite: `.claude/hooks/test_intercept_review_agents.py`

This task creates the test infrastructure only — no test cases yet (those come in subsequent tasks). The v1 test file is being fully replaced.

- [ ] **Step 1: Write the fake server fixture and test helpers**

Rewrite `.claude/hooks/test_intercept_review_agents.py` with the new infrastructure:

```python
"""Tests for intercept-review-agents.py (v2 — OpenCode async bridge)"""
import http.server
import json
import os
import stat
import subprocess
import sys
import threading
import time

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), 'intercept-review-agents.py')
FAKE_CWD = '/tmp/fake-hook-cwd'


def run_hook(payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke the hook script with payload JSON piped to stdin."""
    merged = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=merged,
        timeout=15,
    )


def run_poller(
    session_id: str,
    task_id: str,
    port: int,
    cwd: str,
    env: dict | None = None,
    timeout: int = 10,
) -> subprocess.CompletedProcess:
    """Invoke the hook in --poll mode."""
    merged = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, SCRIPT, '--poll', session_id, task_id, str(port), cwd],
        capture_output=True,
        text=True,
        env=merged,
        timeout=timeout,
    )


def make_payload(
    subagent_type: str,
    description: str = 'Review implementation',
    prompt: str = 'Review this code for correctness.',
    cwd: str = FAKE_CWD,
) -> dict:
    return {
        'tool_name': 'Agent',
        'tool_input': {
            'subagent_type': subagent_type,
            'description': description,
            'prompt': prompt,
        },
        'cwd': cwd,
    }


# ---------------------------------------------------------------------------
# Fake OpenCode server
# ---------------------------------------------------------------------------

class FakeOpenCodeHandler(http.server.BaseHTTPRequestHandler):
    """Handler with class-level config dict set per-instance by the fixture.
    Records all requests to server.requests for test assertions."""

    def log_message(self, format, *args):
        pass  # suppress request logging

    def _record_request(self, method: str, body: bytes = b''):
        """Record request details for later assertion."""
        parsed_body = None
        if body:
            try:
                parsed_body = json.loads(body)
            except json.JSONDecodeError:
                parsed_body = body.decode(errors='replace')
        self.server.requests.append({
            'method': method,
            'path': self.path,
            'headers': dict(self.headers),
            'body': parsed_body,
        })

    def do_GET(self):
        self._record_request('GET')

        if self.path == '/global/health':
            if self.server.config.get('health_ok', True):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'healthy': True, 'version': 'test'}).encode())
            else:
                self.send_response(503)
                self.end_headers()
            return

        if self.path == '/global/event':
            # SSE stream — emit configured events then close
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            session_id = self.server.config.get('session_id', 'fake-session-123')
            for event in self.server.config.get('sse_events', []):
                line = json.dumps({'payload': event, 'directory': '/tmp'})
                self.wfile.write(f'data: {line}\n\n'.encode())
                self.wfile.flush()
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        self._record_request('POST', body)

        if self.path == '/session':
            session_id = self.server.config.get('session_id', 'fake-session-123')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'id': session_id}).encode())
            return

        if '/message' in self.path and self.path.endswith('/message'):
            # Blocking prompt endpoint — sleep to simulate review time, then return
            delay = self.server.config.get('message_delay', 0)
            if delay > 0:
                time.sleep(delay)
            if not self.server.config.get('prompt_accepted', True):
                self.send_response(500)
                self.end_headers()
                return
            result_text = self.server.config.get('result_text', '## Review\n\nLooks good.')
            response = {
                'info': {
                    'id': 'msg_fake123',
                    'sessionID': self.server.config.get('session_id', 'fake-session-123'),
                    'role': 'assistant',
                    'finish': 'stop',
                    'time': {'created': 1000000, 'completed': 1000001},
                    'modelID': 'anthropic/claude-haiku-4.5',
                    'providerID': 'poe',
                    'mode': 'build',
                    'agent': 'build',
                    'path': {'cwd': '/tmp', 'root': '/tmp'},
                    'cost': 0.001,
                    'tokens': {'total': 100, 'input': 90, 'output': 10, 'reasoning': 0,
                               'cache': {'read': 0, 'write': 0}},
                },
                'parts': [
                    {'type': 'step-start', 'id': 'prt_1', 'sessionID': 'fake', 'messageID': 'msg_fake123'},
                    {'type': 'text', 'text': result_text, 'id': 'prt_2',
                     'sessionID': 'fake', 'messageID': 'msg_fake123',
                     'time': {'start': 1000000, 'end': 1000001}},
                    {'type': 'step-finish', 'reason': 'stop', 'id': 'prt_3',
                     'sessionID': 'fake', 'messageID': 'msg_fake123',
                     'cost': 0.001, 'tokens': {'total': 100, 'input': 90, 'output': 10,
                                               'reasoning': 0, 'cache': {'read': 0, 'write': 0}}},
                ],
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            return

        self.send_response(404)
        self.end_headers()


class ConfigurableHTTPServer(http.server.HTTPServer):
    """HTTPServer subclass that carries a config dict and request log."""
    config: dict = {}
    requests: list = []


@pytest.fixture
def fake_opencode():
    """
    Factory fixture: creates a fake OpenCode server with configurable responses.

    Usage:
        server = fake_opencode(session_id='abc', result_text='## Review...')
        result = run_hook(payload, env={'OPENCODE_PORT': str(server.port)})
        server.shutdown()

    Config keys:
        health_ok (bool):       Whether GET /global/health returns 200. Default True.
        session_id (str):       ID returned by POST /session. Default 'fake-session-123'.
        prompt_accepted (bool): Whether POST /session/{id}/message returns 200. Default True.
        result_text (str):      Text content in the blocking POST response. Default '## Review...'.
        message_delay (float):  Seconds to sleep before returning the POST response. Default 0.
        sse_events (list):      Sequence of payload dicts emitted by GET /global/event. Default [].

    The returned ServerHandle exposes .requests — a list of dicts with keys:
        method, path, headers, body (parsed JSON or raw string).
    Use this to assert on what the hook actually sent.
    """
    servers = []

    def _make(**config):
        server = ConfigurableHTTPServer(('127.0.0.1', 0), FakeOpenCodeHandler)
        server.config = config
        server.requests = []  # fresh request log per server instance
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        class ServerHandle:
            def __init__(self):
                self.port = port
                self.url = f'http://127.0.0.1:{port}'
                self.requests = server.requests  # shared reference
            def shutdown(self):
                server.shutdown()

        handle = ServerHandle()
        servers.append(handle)
        return handle

    yield _make

    for s in servers:
        s.shutdown()
```

- [ ] **Step 2: Verify the fixture works**

Create one sanity test at the bottom of the file:

```python
# ---------------------------------------------------------------------------
# Fixture sanity
# ---------------------------------------------------------------------------

def test_fake_opencode_health(fake_opencode):
    """Sanity: fake server responds to health check."""
    import json
    from urllib.request import urlopen
    server = fake_opencode()
    resp = urlopen(f'{server.url}/global/health')
    assert resp.status == 200
    body = json.loads(resp.read())
    assert body['healthy'] is True
```

- [ ] **Step 3: Run the sanity test**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python3 -m pytest .claude/hooks/test_intercept_review_agents.py::test_fake_opencode_health -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/test_intercept_review_agents.py
git commit -m "test: v2 test infrastructure with fake OpenCode server fixture"
```

---

### Task 4: Detection with bypass flag

**Files:**
- Rewrite: `.claude/hooks/intercept-review-agents.py` (start fresh with v2 skeleton)
- Modify: `.claude/hooks/test_intercept_review_agents.py` (add detection tests)

This task builds the detection layer including the new bypass flag, and scaffolds the v2 hook file. The hook won't dispatch anything yet — non-bypass review calls just exit 0 (pass-through) until dispatch is wired in later tasks.

- [ ] **Step 1: Write detection tests**

Add to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_non_review_general_purpose_passes_through():
    """general-purpose + non-review description → pass through (exit 0, no output)."""
    result = run_hook(make_payload('general-purpose', 'Explore codebase for API endpoints'))
    assert result.returncode == 0
    assert result.stdout == ''


def test_explore_subagent_passes_through():
    """Explore subagent → pass through."""
    result = run_hook(make_payload('Explore', 'Find relevant files'))
    assert result.returncode == 0
    assert result.stdout == ''


def test_code_reviewer_subagent_detected():
    """subagent_type == 'superpowers:code-reviewer' → intercepted (non-empty output)."""
    result = run_hook(make_payload('superpowers:code-reviewer'))
    assert result.returncode == 0
    # Until dispatch is wired, interception still exits 0 but we can check stderr for log
    # For now, just verify it doesn't crash
    assert result.returncode == 0


def test_general_purpose_review_description_detected():
    """general-purpose + 'Review...' description → intercepted."""
    result = run_hook(make_payload('general-purpose', 'Review spec compliance for Task 1'))
    assert result.returncode == 0


def test_review_description_case_insensitive():
    """Detection is case-insensitive on 'review' prefix."""
    result = run_hook(make_payload('general-purpose', 'REVIEW the implementation'))
    assert result.returncode == 0


def test_bypass_flag_passes_through():
    """[BYPASS_HOOK] prefix in description → immediate pass-through, no interception."""
    result = run_hook(make_payload(
        'superpowers:code-reviewer',
        '[BYPASS_HOOK] Review implementation',
    ))
    assert result.returncode == 0
    assert result.stdout == ''


def test_bypass_flag_not_triggered_by_substring():
    """BYPASS_HOOK must be at the start of description, not embedded."""
    result = run_hook(make_payload(
        'superpowers:code-reviewer',
        'Please review [BYPASS_HOOK] this code',
    ))
    assert result.returncode == 0
    # This SHOULD be intercepted (bypass only works as prefix)
    # Until dispatch is wired, we can't distinguish — just verify no crash
```

- [ ] **Step 2: Run detection tests to see them fail**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_non_review or test_explore or test_code_reviewer_detected or test_general_purpose_review or test_review_description_case or test_bypass" -v
```

Expected: FAIL — the v2 hook doesn't exist yet (file still has v1 code which won't handle bypass).

- [ ] **Step 3: Write v2 hook skeleton with detection**

Rewrite `.claude/hooks/intercept-review-agents.py` entirely:

```python
#!/usr/bin/env python3
"""
intercept-review-agents.py (v2 — OpenCode Async Bridge)

PreToolUse hook: intercepts review-type Agent calls and dispatches them
to OpenCode Server asynchronously. Results delivered via file handshake.

Detection patterns:
  - description.startswith('[BYPASS_HOOK]') → pass through immediately
  - subagent_type == "superpowers:code-reviewer" → intercept
  - subagent_type == "general-purpose" AND description starts with "review" → intercept
  - Everything else → pass through

Environment variables:
  OPENCODE_PORT              OpenCode Server port (default: 4096)
  OPENCODE_TIMEOUT           Background process HTTP timeout in seconds (default: 300)
  OPENCODE_STARTUP_TIMEOUT   Server startup timeout in seconds (default: 10)
  OPENCODE_MODEL             Override model for reviews (passed as modelID)
  OPENCODE_SERVER_PASSWORD   Auth password if configured
  OPENCODE_DEBUG=1           Enable debug logging (default: off)
  OPENCODE_LOG_FILE          Log file path (default: /tmp/opencode-hook-debug.log)
  OPENCODE_SKIP_POLLER=1     Test-only: suppress background process spawning
"""
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Logging — no-op unless OPENCODE_DEBUG=1
# ---------------------------------------------------------------------------
_LOG_FILE = os.environ.get('OPENCODE_LOG_FILE', '/tmp/opencode-hook-debug.log')
_DEBUG = os.environ.get('OPENCODE_DEBUG', '0') == '1'

if _DEBUG:
    logging.basicConfig(
        filename=_LOG_FILE,
        level=logging.DEBUG,
        format='[%(asctime)s] %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S',
    )
else:
    logging.disable(logging.CRITICAL)

log = logging.debug


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def is_bypass(description: str) -> bool:
    """Check for [BYPASS_HOOK] prefix — must be the very first check."""
    return description.startswith('[BYPASS_HOOK]')


def is_review_call(subagent_type: str, description: str) -> bool:
    """Detect review-type agent calls."""
    if subagent_type == 'superpowers:code-reviewer':
        return True
    if subagent_type == 'general-purpose' and description.lower().startswith('review'):
        return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    payload = json.loads(sys.stdin.read())
    tool_input = payload.get('tool_input', {})
    subagent_type = tool_input.get('subagent_type', '')
    description = tool_input.get('description', '')

    # Bypass check — first thing, before all other logic
    if is_bypass(description):
        log(f'bypass flag detected, passing through | desc={description[:60]}')
        sys.exit(0)

    if not is_review_call(subagent_type, description):
        log(f'pass-through | type={subagent_type} | desc={description[:60]}')
        sys.exit(0)

    log(f'intercepted | type={subagent_type} | desc={description[:60]}')

    # TODO: dispatch to OpenCode (wired in Task 8)
    # For now, fall through so tests pass without a server
    sys.exit(0)


if __name__ == '__main__':
    main()
```

Make it executable:
```bash
chmod +x .claude/hooks/intercept-review-agents.py
```

- [ ] **Step 4: Run detection tests to verify they pass**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_non_review or test_explore or test_code_reviewer_detected or test_general_purpose_review or test_review_description_case or test_bypass" -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py
git commit -m "feat(v2): hook skeleton with detection and bypass flag"
```

---

### Task 5: File helpers — task directory and status management

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (add file helper functions)
- Modify: `.claude/hooks/test_intercept_review_agents.py` (add file helper tests)

- [ ] **Step 1: Write file helper tests**

Add to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# File helpers (tested via import, not subprocess)
# ---------------------------------------------------------------------------

# Import the hook module for unit testing internal functions
import importlib.util
_spec = importlib.util.spec_from_file_location('hook', SCRIPT)
_hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hook)


def test_tasks_dir_path():
    assert _hook.tasks_dir('/project') == '/project/.opencode/tasks'


def test_write_status_creates_directory(tmp_path):
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'abc123', 'PENDING')
    status_file = tmp_path / 'project' / '.opencode' / 'tasks' / 'abc123.status'
    assert status_file.exists()
    assert status_file.read_text() == 'PENDING'


def test_write_status_overwrites(tmp_path):
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'abc123', 'PENDING')
    _hook.write_status(cwd, 'abc123', 'COMPLETE')
    status_file = tmp_path / 'project' / '.opencode' / 'tasks' / 'abc123.status'
    assert status_file.read_text() == 'COMPLETE'


def test_write_result_creates_file(tmp_path):
    cwd = str(tmp_path / 'project')
    _hook.write_result(cwd, 'abc123', '## Review\n\nLooks good.')
    result_file = tmp_path / 'project' / '.opencode' / 'tasks' / 'abc123.result.md'
    assert result_file.exists()
    assert '## Review' in result_file.read_text()


def test_read_status_returns_content(tmp_path):
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'abc123', 'COMPLETE')
    assert _hook.read_status(cwd, 'abc123') == 'COMPLETE'


def test_read_status_missing_file(tmp_path):
    cwd = str(tmp_path / 'project')
    assert _hook.read_status(cwd, 'nonexistent') == ''


def test_append_progress_creates_and_appends(tmp_path):
    cwd = str(tmp_path / 'project')
    _hook.append_progress(cwd, 'abc123', 'token one')
    _hook.append_progress(cwd, 'abc123', 'token two')
    progress_file = tmp_path / 'project' / '.opencode' / 'tasks' / 'abc123.progress.md'
    assert progress_file.exists()
    content = progress_file.read_text()
    assert 'token one' in content
    assert 'token two' in content
```

- [ ] **Step 2: Run to see them fail**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_tasks_dir or test_write_status or test_write_result or test_read_status" -v
```

Expected: FAIL — functions don't exist yet.

- [ ] **Step 3: Implement file helpers**

Add to `.claude/hooks/intercept-review-agents.py` after the detection section:

```python
# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def tasks_dir(cwd: str) -> str:
    """Path to .opencode/tasks/ under the project root."""
    return os.path.join(cwd, '.opencode', 'tasks')


def write_status(cwd: str, task_id: str, status: str) -> None:
    """Write status string to {task_id}.status file."""
    d = tasks_dir(cwd)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f'{task_id}.status'), 'w') as f:
        f.write(status)


def read_status(cwd: str, task_id: str) -> str:
    """Read status file, return empty string if missing."""
    try:
        with open(os.path.join(tasks_dir(cwd), f'{task_id}.status')) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ''


def write_result(cwd: str, task_id: str, content: str) -> None:
    """Write review content to {task_id}.result.md file."""
    d = tasks_dir(cwd)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f'{task_id}.result.md'), 'w') as f:
        f.write(content)


def append_progress(cwd: str, task_id: str, line: str) -> None:
    """Append a line to {task_id}.progress.md (create if absent)."""
    d = tasks_dir(cwd)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f'{task_id}.progress.md'), 'a') as f:
        f.write(line)
```

- [ ] **Step 4: Run file helper tests**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_tasks_dir or test_write_status or test_write_result or test_read_status" -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat(v2): file helpers for task status and result handshake"
```

---

### Task 6: Server health check

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (add `health_check()`)
- Modify: `.claude/hooks/test_intercept_review_agents.py` (add health check tests)

- [ ] **Step 1: Write health check tests**

Add to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# Server health check
# ---------------------------------------------------------------------------

def test_health_check_success(fake_opencode):
    """health_check returns True when server responds 200."""
    server = fake_opencode(health_ok=True)
    assert _hook.health_check(server.port) is True


def test_health_check_server_down():
    """health_check returns False when nothing is listening."""
    assert _hook.health_check(19999) is False


def test_health_check_server_error(fake_opencode):
    """health_check returns False when server returns 503."""
    server = fake_opencode(health_ok=False)
    assert _hook.health_check(server.port) is False
```

- [ ] **Step 2: Run to see them fail**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_health_check" -v
```

Expected: FAIL — `health_check` not defined.

- [ ] **Step 3: Implement health check**

Add to `.claude/hooks/intercept-review-agents.py` after file helpers:

```python
# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------
def health_check(port: int, password: str | None = None) -> bool:
    """GET /global/health — True if server responds {"healthy": true}."""
    try:
        req = Request(f'http://127.0.0.1:{port}/global/health')
        if password:
            req.add_header('Authorization', f'Bearer {password}')
        with urlopen(req, timeout=2) as resp:
            if resp.status != 200:
                return False
            body = json.loads(resp.read())
            return body.get('healthy') is True
    except (URLError, OSError, json.JSONDecodeError):
        return False
```

**Endpoint confirmed:** `GET /global/health` returns `{"healthy": true, "version": "..."}` on OpenCode v1.3.13.

- [ ] **Step 4: Run health check tests**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_health_check" -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat(v2): server health check via HTTP"
```

---

### Task 7: On-demand server startup

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (add `start_server()`, `ensure_server()`)
- Modify: `.claude/hooks/test_intercept_review_agents.py` (add startup tests)

The startup tests use a fake `opencode` binary (same pattern as v1's `fake_gemini`) since we need to test subprocess management. The fake binary is a short bash script that either starts an HTTP server or exits with an error.

- [ ] **Step 1: Write startup tests**

Add to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_opencode_binary(tmp_path):
    """
    Factory: creates a fake 'opencode' binary that behaves predictably.

    Usage:
        bin_env = fake_opencode_binary(mode='healthy', port=server.port)
        # bin_env is a PATH string with the fake binary directory prepended
    """
    def _make(mode='healthy', port=None, exit_code=0, stderr_msg=''):
        script = tmp_path / 'opencode'
        if mode == 'healthy':
            # Start a tiny Python HTTP server on the requested port
            body = f'''#!/usr/bin/env bash
python3 -c "
import http.server, threading, time, sys
port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 4096
server = http.server.HTTPServer(('127.0.0.1', port), http.server.BaseHTTPRequestHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
time.sleep(300)  # keep alive
" "$@" &
'''
        elif mode == 'fail':
            body = f'#!/usr/bin/env bash\necho "{stderr_msg}" >&2\nexit {exit_code}\n'
        elif mode == 'hang':
            body = '#!/usr/bin/env bash\nsleep 999\n'
        else:
            body = f'#!/usr/bin/env bash\nexit {exit_code}\n'
        script.write_text(body)
        script.chmod(
            stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
        )
        return f'{tmp_path}:{os.environ.get("PATH", "")}'

    return _make


def test_ensure_server_already_running(fake_opencode):
    """If server is already healthy, ensure_server returns immediately."""
    server = fake_opencode(health_ok=True)
    ok, err = _hook.ensure_server(server.port, startup_timeout=2)
    assert ok is True
    assert err == ''


def test_start_server_binary_not_found():
    """Missing opencode binary → returns failure."""
    ok, err = _hook.start_server(19999, startup_timeout=2, path_override='/nonexistent')
    assert ok is False
    assert 'not found' in err.lower() or 'No such file' in err.lower()


def test_start_server_exits_immediately_with_error(fake_opencode_binary, tmp_path, monkeypatch):
    """opencode exits with error → fail fast with error from log file."""
    log_file = str(tmp_path / 'startup-test.log')
    monkeypatch.setenv('OPENCODE_LOG_FILE', log_file)
    bin_path = fake_opencode_binary(mode='fail', exit_code=1, stderr_msg='Not authenticated')
    ok, err = _hook.start_server(19999, startup_timeout=5, path_override=bin_path)
    assert ok is False
    assert 'Not authenticated' in err or 'exited' in err.lower()


def test_start_server_forwards_password(monkeypatch):
    """start_server passes password to health_check during the startup polling loop."""
    calls = []

    def fake_health_check(port, pw=None):
        calls.append(pw)
        return True  # succeed immediately

    monkeypatch.setattr(_hook, 'health_check', fake_health_check)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **kw: type('P', (), {'poll': lambda s: None})())

    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.log', delete=False) as f:
        log = f.name
    monkeypatch.setenv('OPENCODE_LOG_FILE', log)

    ok, _ = _hook.start_server(19999, startup_timeout=5, password='s3cr3t')
    assert ok is True
    assert calls and calls[0] == 's3cr3t'


def test_start_server_nonexistent_log_dir(fake_opencode_binary, tmp_path, monkeypatch):
    """OPENCODE_LOG_FILE under missing parent dir → dir created, no misleading 'not found on PATH' error."""
    log_file = str(tmp_path / 'logs' / 'opencode.log')
    monkeypatch.setenv('OPENCODE_LOG_FILE', log_file)
    bin_path = fake_opencode_binary(mode='fail', exit_code=1, stderr_msg='startup failed')
    ok, err = _hook.start_server(19999, startup_timeout=5, path_override=bin_path)
    assert ok is False
    assert 'not found on PATH' not in err
    assert os.path.isdir(str(tmp_path / 'logs'))
```

- [ ] **Step 2: Run to see them fail**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_ensure_server or test_start_server" -v
```

Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement start_server and ensure_server**

Add to `.claude/hooks/intercept-review-agents.py` after `health_check`:

```python
def start_server(port: int, startup_timeout: int, password: str | None = None, path_override: str | None = None) -> tuple[bool, str]:
    """
    Start opencode serve and wait until healthy or failure.
    Returns (success, error_message).

    Server stderr is redirected to OPENCODE_LOG_FILE (not PIPE) to prevent
    deadlock — the server is long-lived and PIPE buffers would fill and block it.
    On early exit, the tail of the log file is read for the error message.
    """
    log_file = os.environ.get('OPENCODE_LOG_FILE', '/tmp/opencode-hook-debug.log')
    env = None
    if path_override:
        env = {**os.environ, 'PATH': path_override}
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    try:
        log_fh = open(log_file, 'a')
        proc = subprocess.Popen(
            ['opencode', 'serve', '--port', str(port)],
            stdout=subprocess.DEVNULL,
            stderr=log_fh,
            start_new_session=True,
            env=env,
        )
    except FileNotFoundError:
        return False, 'opencode not found on PATH'

    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        ret = proc.poll()
        if ret is not None:
            log_fh.close()
            # Read tail of log file for error context
            stderr = ''
            try:
                with open(log_file) as f:
                    lines = f.readlines()
                stderr = ''.join(lines[-10:]).strip()
            except OSError:
                pass
            return False, f'opencode exited with code {ret}: {stderr}'
        if health_check(port, password):
            return True, ''
        time.sleep(0.5)

    # Timeout — kill the process
    proc.kill()
    log_fh.close()
    return False, f'opencode did not become healthy within {startup_timeout}s'


def ensure_server(port: int, startup_timeout: int, password: str | None = None, path_override: str | None = None) -> tuple[bool, str]:
    """Health check first, start if needed."""
    if health_check(port, password):
        return True, ''
    return start_server(port, startup_timeout, password, path_override)
```

- [ ] **Step 4: Run startup tests**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_ensure_server or test_start_server" -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat(v2): on-demand server startup with fail-fast"
```

---

### Task 8: HTTP dispatch — create session

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (add `create_session()`)
- Modify: `.claude/hooks/test_intercept_review_agents.py` (add session creation tests)

The hook creates the session then immediately passes the session ID to the background process. The blocking prompt is sent by the background process (Task 10), not the hook.

- [ ] **Step 1: Write session creation tests**

Add to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# HTTP dispatch
# ---------------------------------------------------------------------------

def test_create_session_returns_id(fake_opencode):
    """POST /session returns session ID from the 'id' field."""
    server = fake_opencode(session_id='test-session-789')
    session_id = _hook.create_session(server.port)
    assert session_id == 'test-session-789'
    session_reqs = [r for r in server.requests if r['path'] == '/session' and r['method'] == 'POST']
    assert len(session_reqs) == 1


def test_create_session_server_down():
    """create_session returns None when server is unreachable."""
    session_id = _hook.create_session(19999)
    assert session_id is None
```

- [ ] **Step 2: Run to see them fail**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_create_session" -v
```

Expected: FAIL — function not defined.

- [ ] **Step 3: Implement create_session**

Add to `.claude/hooks/intercept-review-agents.py` after server management:

```python
# ---------------------------------------------------------------------------
# HTTP dispatch
# ---------------------------------------------------------------------------
def create_session(port: int, password: str | None = None) -> str | None:
    """POST /session → session_id, or None on failure."""
    url = f'http://127.0.0.1:{port}/session'
    data = json.dumps({}).encode()
    req = Request(url, data=data, headers={'Content-Type': 'application/json'})
    if password:
        req.add_header('Authorization', f'Bearer {password}')
    try:
        with urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
            return body.get('id')
    except (URLError, OSError, json.JSONDecodeError):
        return None
```

- [ ] **Step 4: Run session creation tests**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_create_session" -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat(v2): HTTP dispatch — session creation"
```

---

### Task 9: Main hook flow — dispatch, spawn poller, return deny

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (wire `main()` to use server + dispatch)
- Modify: `.claude/hooks/test_intercept_review_agents.py` (add end-to-end hook tests)

This is where the hook's main function gets fully wired. On intercepting a review call: ensure server → create session → write prompt to file → write PENDING → spawn background process → print deny JSON. The prompt is written to `{task_id}.prompt` in the tasks dir so the background process can read it without long argv.

- [ ] **Step 1: Write main flow tests**

Add to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# Main hook flow (end-to-end via subprocess)
# ---------------------------------------------------------------------------

def test_hook_dispatches_and_returns_deny(fake_opencode, tmp_path):
    """Full interception: server healthy → dispatch → deny JSON with task info."""
    server = fake_opencode(
        session_id='sess-abc',
        result_text='## Review\n\nLooks good.',
    )
    cwd = str(tmp_path / 'project')
    result = run_hook(
        make_payload('superpowers:code-reviewer', cwd=cwd),
        env={
            'OPENCODE_PORT': str(server.port),
            'OPENCODE_STARTUP_TIMEOUT': '2',
            'OPENCODE_SKIP_POLLER': '1',  # don't spawn background process
        },
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    hs = output['hookSpecificOutput']
    assert hs['hookEventName'] == 'PreToolUse'
    assert hs['permissionDecision'] == 'deny'
    reason = hs['permissionDecisionReason']
    assert '.opencode/tasks/' in reason
    assert '.status' in reason
    assert '.result.md' in reason
    assert 'BYPASS_HOOK' in reason


def test_hook_writes_pending_status(fake_opencode, tmp_path):
    """After dispatch, PENDING status file exists in cwd."""
    server = fake_opencode(session_id='sess-abc', prompt_accepted=True)
    cwd = str(tmp_path / 'project')
    result = run_hook(
        make_payload('superpowers:code-reviewer', cwd=cwd),
        env={
            'OPENCODE_PORT': str(server.port),
            'OPENCODE_STARTUP_TIMEOUT': '2',
            'OPENCODE_SKIP_POLLER': '1',  # don't spawn background poller
        },
    )
    assert result.returncode == 0
    # Extract task_id from deny reason
    output = json.loads(result.stdout)
    reason = output['hookSpecificOutput']['permissionDecisionReason']
    # Parse task_id from ".opencode/tasks/{task_id}.status"
    import re
    match = re.search(r'\.opencode/tasks/([a-f0-9]+)\.status', reason)
    assert match, f'Could not find task_id in reason: {reason}'
    task_id = match.group(1)
    status_file = tmp_path / 'project' / '.opencode' / 'tasks' / f'{task_id}.status'
    assert status_file.exists()
    assert status_file.read_text().strip() == 'PENDING'


def test_hook_falls_through_when_server_unreachable(tmp_path):
    """If no server is running, hook exits 0 with no stdout (Claude agent fallback)
    but prints a warning to stderr and logs to file."""
    cwd = str(tmp_path / 'project')
    log_file = str(tmp_path / 'fallback-test.log')
    result = run_hook(
        make_payload('superpowers:code-reviewer', cwd=cwd),
        env={
            'OPENCODE_PORT': '19999',
            'OPENCODE_STARTUP_TIMEOUT': '1',
            'OPENCODE_LOG_FILE': log_file,
            'PATH': '/nonexistent',
        },
    )
    assert result.returncode == 0
    assert result.stdout == ''
    # Verify stderr warning is always printed (regardless of debug mode)
    assert 'server startup failed' in result.stderr.lower()
    assert 'Falling back to Claude agent' in result.stderr
    # Verify log file was written (always, not just in debug mode)
    import pathlib
    assert pathlib.Path(log_file).exists()
    log_content = pathlib.Path(log_file).read_text()
    assert 'STARTUP FAILURE' in log_content


def test_hook_bypass_still_works_with_server_running(fake_opencode, tmp_path):
    """[BYPASS_HOOK] passes through even when server is healthy."""
    server = fake_opencode()
    cwd = str(tmp_path / 'project')
    result = run_hook(
        make_payload(
            'superpowers:code-reviewer',
            '[BYPASS_HOOK] Review implementation',
            cwd=cwd,
        ),
        env={'OPENCODE_PORT': str(server.port)},
    )
    assert result.returncode == 0
    assert result.stdout == ''
```

- [ ] **Step 2: Run to see them fail**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_hook_dispatches or test_hook_writes_pending or test_hook_falls_through or test_hook_bypass_still" -v
```

Expected: FAIL — `main()` still has the TODO placeholder.

- [ ] **Step 3: Wire main() with full dispatch flow**

Replace the `main()` function in `.claude/hooks/intercept-review-agents.py`:

```python
def main() -> None:
    payload = json.loads(sys.stdin.read())
    tool_input = payload.get('tool_input', {})
    subagent_type = tool_input.get('subagent_type', '')
    description = tool_input.get('description', '')
    cwd = payload.get('cwd', '')
    prompt = tool_input.get('prompt', '')

    # Bypass check — first thing, before all other logic
    if is_bypass(description):
        log(f'bypass flag detected, passing through | desc={description[:60]}')
        sys.exit(0)

    if not is_review_call(subagent_type, description):
        log(f'pass-through | type={subagent_type} | desc={description[:60]}')
        sys.exit(0)

    log(f'intercepted | type={subagent_type} | desc={description[:60]}')

    # Read config
    port = _int_env('OPENCODE_PORT', 4096)
    startup_timeout = _int_env('OPENCODE_STARTUP_TIMEOUT', 10)
    model = os.environ.get('OPENCODE_MODEL', '') or None
    password = os.environ.get('OPENCODE_SERVER_PASSWORD', '') or None

    # Ensure server is running
    ok, err = ensure_server(port, startup_timeout, password)
    if not ok:
        # Always log startup failures regardless of debug mode
        _always_log_failure(err)
        sys.exit(0)

    # Generate task ID and create session
    task_id = uuid.uuid4().hex[:12]

    session_id = create_session(port, password)
    if not session_id:
        log('failed to create session | falling back to Claude agent')
        sys.exit(0)

    # Write prompt to file (background process reads it)
    write_status(cwd, task_id, 'PENDING')  # also creates tasks dir
    prompt_file = os.path.join(tasks_dir(cwd), f'{task_id}.prompt')
    with open(prompt_file, 'w') as f:
        f.write(prompt)

    # Spawn background process (skip in tests via OPENCODE_SKIP_POLLER=1)
    if os.environ.get('OPENCODE_SKIP_POLLER', '0') != '1':
        subprocess.Popen(
            [sys.executable, __file__, '--poll', session_id, task_id, str(port), cwd],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Build and return deny response
    reason = (
        'A PreToolUse hook dispatched this review to OpenCode Server (async). '
        'The review is running in the background. When you\'re ready for the result, read '
        f'`.opencode/tasks/{task_id}.status`. When it says COMPLETE, read '
        f'`.opencode/tasks/{task_id}.result.md` and continue the workflow as normal. '
        'If it says FAILED, re-invoke the original agent call with [BYPASS_HOOK] '
        'prepended to the description field \u2014 the hook will let it through to the '
        'Claude agent this time.\n\n'
        'The review typically takes 30\u201360 seconds. Continue with your current work '
        'and check back after completing your next task.'
    )

    response = {
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': reason,
        }
    }

    log(f'dispatched | task={task_id} | session={session_id}')
    print(json.dumps(response))
```

Also add a config helper near the top of the file (after the `log` assignment):

```python
def _int_env(name: str, default: int) -> int:
    """Read an env var as int, fall back to default on missing/invalid."""
    try:
        val = int(os.environ.get(name, str(default)))
        return val if val > 0 else default
    except ValueError:
        return default


def _always_log_failure(err: str) -> None:
    """Log startup failure to file AND stderr, regardless of debug mode.
    Debug mode controls verbose per-request logging; startup failures
    are exceptional events that are always recorded."""
    log_file = os.environ.get('OPENCODE_LOG_FILE', '/tmp/opencode-hook-debug.log')
    # Always append to log file
    try:
        with open(log_file, 'a') as f:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            f.write(f'[{ts}] STARTUP FAILURE: {err}\n')
    except OSError:
        pass
    # Always print to stderr (visible in terminal, not captured by Claude)
    summary = err.split('\n')[0][:200] if err else 'unknown error'
    print(
        f'OpenCode hook: server startup failed — {summary}. '
        f'Falling back to Claude agent. Details: {log_file}',
        file=sys.stderr,
    )
```

- [ ] **Step 4: Run main flow tests**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_hook_dispatches or test_hook_writes_pending or test_hook_falls_through or test_hook_bypass_still" -v
```

Expected: all PASS

- [ ] **Step 5: Run ALL tests so far**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat(v2): wire main hook flow — dispatch, spawn poller, return deny"
```

---

### Task 10: Background process — blocking POST and SSE transcript

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (add `run_background_process()` and `--poll` entry point)
- Modify: `.claude/hooks/test_intercept_review_agents.py` (add background process tests)

The background process runs as a detached subprocess invoked with `--poll`. It does two things concurrently: sends a blocking `POST /session/{id}/message` (main thread), and subscribes to `GET /global/event` SSE to write a progress transcript (SSE thread). When the POST returns with `info.finish == "stop"`, it extracts text parts, writes the result and progress files, and updates status to `COMPLETE`.

- [ ] **Step 1: Write background process tests**

Add to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# Background process
# ---------------------------------------------------------------------------

def test_background_writes_complete_on_success(fake_opencode, tmp_path):
    """Blocking POST returns finish=stop → COMPLETE + result file written."""
    server = fake_opencode(
        session_id='sess-abc',
        result_text='## Review\n\nCode looks good. Ready to merge.',
    )
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'bg-test-1', 'PENDING')
    # Write the prompt file (normally done by main hook)
    import pathlib
    prompt_file = tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-1.prompt'
    prompt_file.write_text('Review this implementation.')

    result = run_poller(
        session_id='sess-abc',
        task_id='bg-test-1',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
    )
    assert result.returncode == 0

    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-1.status').read_text()
    assert status.strip() == 'COMPLETE'

    result_content = (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-1.result.md').read_text()
    assert '## Review' in result_content
    assert 'Ready to merge' in result_content


def test_background_timeout_writes_failed(fake_opencode, tmp_path):
    """POST takes longer than OPENCODE_TIMEOUT → FAILED."""
    server = fake_opencode(message_delay=5)  # delay exceeds timeout
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'bg-test-2', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-2.prompt').write_text('Review this.')

    result = run_poller(
        session_id='sess-abc',
        task_id='bg-test-2',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '2'},
        timeout=15,
    )
    assert result.returncode == 0

    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-2.status').read_text()
    assert status.strip() == 'FAILED'


def test_background_server_crash_writes_failed(tmp_path):
    """POST can't reach server → FAILED."""
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'bg-test-3', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-3.prompt').write_text('Review this.')

    result = run_poller(
        session_id='sess-abc',
        task_id='bg-test-3',
        port=19999,  # nothing listening
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '3'},
        timeout=10,
    )
    assert result.returncode == 0

    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-3.status').read_text()
    assert status.strip() == 'FAILED'


def test_background_extracts_multiple_text_parts(fake_opencode, tmp_path):
    """Multiple text parts in response are joined in result file."""
    server = fake_opencode(result_text='## Strengths\n\nClean.\n\n## Issues\n\nMissing error handling.')
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'bg-test-4', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-4.prompt').write_text('Review this.')

    run_poller(session_id='sess-abc', task_id='bg-test-4', port=server.port,
               cwd=cwd, env={'OPENCODE_TIMEOUT': '10'})

    result_content = (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-4.result.md').read_text()
    assert 'Clean.' in result_content
    assert 'Missing error handling' in result_content


def test_background_sse_events_written_to_progress(fake_opencode, tmp_path):
    """SSE delta events are written to the progress transcript file."""
    sse_events = [
        {'type': 'message.part.delta',
         'properties': {'sessionID': 'sess-abc', 'delta': 'This '}},
        {'type': 'message.part.delta',
         'properties': {'sessionID': 'sess-abc', 'delta': 'looks good.'}},
        {'type': 'message.part.updated',
         'properties': {'sessionID': 'sess-abc',
                        'part': {'type': 'tool', 'tool': 'read',
                                 'state': {'status': 'completed',
                                           'input': {'filePath': '/tmp/test.py'},
                                           'output': 'content'}}}},
    ]
    server = fake_opencode(session_id='sess-abc', result_text='Looks good.', sse_events=sse_events)
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'bg-test-5', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-5.prompt').write_text('Review this.')

    run_poller(session_id='sess-abc', task_id='bg-test-5', port=server.port,
               cwd=cwd, env={'OPENCODE_TIMEOUT': '10'})

    progress_file = tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-5.progress.md'
    assert progress_file.exists()
    content = progress_file.read_text()
    assert 'This ' in content
    assert 'looks good.' in content
    assert '[TOOL: read]' in content
    assert '/tmp/test.py' in content


def test_background_prompt_not_accepted(fake_opencode, tmp_path):
    """Server returns error on POST /message → FAILED."""
    server = fake_opencode(prompt_accepted=False)
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'bg-test-6', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-6.prompt').write_text('Review this.')

    run_poller(session_id='sess-abc', task_id='bg-test-6', port=server.port,
               cwd=cwd, env={'OPENCODE_TIMEOUT': '5'})

    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-6.status').read_text()
    assert status.strip() == 'FAILED'
```

- [ ] **Step 2: Run to see them fail**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_background" -v
```

Expected: FAIL — `run_background_process` and `--poll` entry point not implemented.

- [ ] **Step 3: Implement background process and --poll entry point**

Add to `.claude/hooks/intercept-review-agents.py` after the dispatch section. Note `threading` must be imported at the top.

```python
# ---------------------------------------------------------------------------
# Background process
# ---------------------------------------------------------------------------

def _sse_thread(port: int, session_id: str, task_id: str, cwd: str,
                stop_event: threading.Event, password: str | None = None) -> None:
    """
    Subscribe to GET /global/event and write token deltas and tool call events
    to {task_id}.progress.md. Runs until stop_event is set.
    """
    url = f'http://127.0.0.1:{port}/global/event'
    try:
        req = Request(url)
        if password:
            req.add_header('Authorization', f'Bearer {password}')
        with urlopen(req, timeout=None) as resp:
            for raw_line in resp:
                if stop_event.is_set():
                    break
                line = raw_line.decode('utf-8', errors='replace').strip()
                if not line.startswith('data:'):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                    payload = event.get('payload', {})
                    ptype = payload.get('type', '')
                    props = payload.get('properties', {})
                    if props.get('sessionID') != session_id:
                        continue
                    if ptype == 'message.part.delta':
                        delta = props.get('delta', '')
                        if delta:
                            append_progress(cwd, task_id, delta)
                    elif ptype == 'message.part.updated':
                        part = props.get('part', {})
                        if part.get('type') == 'tool':
                            state = part.get('state', {})
                            if state.get('status') == 'completed':
                                tool = part.get('tool', '?')
                                inp = state.get('input', {})
                                # Show primary input path/command
                                detail = (inp.get('filePath') or inp.get('command')
                                          or inp.get('pattern') or json.dumps(inp)[:60])
                                append_progress(cwd, task_id, f'\n[TOOL: {tool}] {detail}\n')
                except (json.JSONDecodeError, KeyError):
                    pass
    except (URLError, OSError):
        pass  # server gone or stop requested


def run_background_process(
    port: int,
    session_id: str,
    task_id: str,
    cwd: str,
    timeout: int,
    model: str | None = None,
    password: str | None = None,
) -> None:
    """
    Main thread: send blocking POST /session/{id}/message, wait for finish=stop.
    SSE thread: subscribe to /global/event, write progress transcript.
    On completion, write result.md and set status to COMPLETE.
    """
    # Read prompt from file written by hook
    prompt_file = os.path.join(tasks_dir(cwd), f'{task_id}.prompt')
    try:
        with open(prompt_file) as f:
            prompt = f.read()
    except OSError:
        log(f'bg: prompt file not found | task={task_id}')
        write_status(cwd, task_id, 'FAILED')
        return

    # Start SSE thread
    stop_event = threading.Event()
    sse = threading.Thread(
        target=_sse_thread,
        args=(port, session_id, task_id, cwd, stop_event, password),
        daemon=True,
    )
    sse.start()

    # Send blocking POST
    url = f'http://127.0.0.1:{port}/session/{session_id}/message'
    body: dict = {'parts': [{'type': 'text', 'text': prompt}]}
    if model:
        body['modelID'] = model
    data = json.dumps(body).encode()
    req = Request(url, data=data, headers={'Content-Type': 'application/json'})
    if password:
        req.add_header('Authorization', f'Bearer {password}')

    try:
        with urlopen(req, timeout=timeout) as resp:
            response = json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError) as e:
        log(f'bg: POST failed | task={task_id} | err={e}')
        stop_event.set()
        write_status(cwd, task_id, 'FAILED')
        return
    finally:
        stop_event.set()

    # Verify terminal state
    finish = response.get('info', {}).get('finish', '')
    if finish != 'stop':
        log(f'bg: unexpected finish={finish!r} | task={task_id}')
        write_status(cwd, task_id, 'FAILED')
        return

    # Extract text parts and write result
    text_parts = [
        p['text']
        for p in response.get('parts', [])
        if p.get('type') == 'text' and p.get('text')
    ]
    result_text = '\n\n'.join(text_parts)
    write_result(cwd, task_id, result_text)
    write_status(cwd, task_id, 'COMPLETE')
    log(f'bg: complete | task={task_id} | bytes={len(result_text)}')
```

Update the `if __name__ == '__main__'` block at the bottom:

```python
def main_poll(session_id: str, task_id: str, port: int, cwd: str) -> None:
    """Entry point for --poll mode (background process subprocess)."""
    timeout = _int_env('OPENCODE_TIMEOUT', 300)
    model = os.environ.get('OPENCODE_MODEL', '') or None
    password = os.environ.get('OPENCODE_SERVER_PASSWORD', '') or None
    run_background_process(port, session_id, task_id, cwd, timeout, model, password)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--poll':
        if len(sys.argv) != 6:
            print(
                f'Usage: {sys.argv[0]} --poll <session_id> <task_id> <port> <cwd>',
                file=sys.stderr,
            )
            sys.exit(1)
        main_poll(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5])
    else:
        main()
```

- [ ] **Step 4: Run background process tests**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_background" -v
```

Expected: all PASS

- [ ] **Step 5: Run ALL tests**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat(v2): background process — blocking POST with SSE progress transcript"
```

---

### Task 11: Debug logging and configuration edge cases

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (verify logging paths work)
- Modify: `.claude/hooks/test_intercept_review_agents.py` (add logging + config tests)

- [ ] **Step 1: Write logging and config tests**

Add to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# Logging and configuration
# ---------------------------------------------------------------------------

def test_debug_logging_writes_to_file(fake_opencode, tmp_path):
    """OPENCODE_DEBUG=1 writes log entries to OPENCODE_LOG_FILE."""
    server = fake_opencode(session_id='sess-log', prompt_accepted=True)
    cwd = str(tmp_path / 'project')
    log_file = str(tmp_path / 'hook-test.log')
    result = run_hook(
        make_payload('superpowers:code-reviewer', cwd=cwd),
        env={
            'OPENCODE_PORT': str(server.port),
            'OPENCODE_STARTUP_TIMEOUT': '2',
            'OPENCODE_DEBUG': '1',
            'OPENCODE_LOG_FILE': log_file,
            'OPENCODE_SKIP_POLLER': '1',
        },
    )
    assert result.returncode == 0
    import pathlib
    log_content = pathlib.Path(log_file).read_text()
    assert 'intercepted' in log_content
    assert 'dispatched' in log_content


def test_invalid_port_uses_default():
    """Non-integer OPENCODE_PORT doesn't crash the hook."""
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={
            'OPENCODE_PORT': 'not-a-number',
            'OPENCODE_STARTUP_TIMEOUT': '1',
            'PATH': '/nonexistent',
        },
    )
    # Should not crash — either dispatches or falls back
    assert result.returncode == 0


def test_model_override_included_in_prompt(fake_opencode, tmp_path):
    """OPENCODE_MODEL env var appears as modelID in the background process POST body."""
    server = fake_opencode(session_id='sess-model', result_text='## Review\n\nLooks good.')
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'model-test', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'model-test.prompt').write_text('Review this.')

    result = run_poller(
        session_id='sess-model',
        task_id='model-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10', 'OPENCODE_MODEL': 'gemini-2.5-pro'},
    )
    assert result.returncode == 0
    # Verify modelID was sent in the POST body
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    assert msg_reqs[0]['body']['modelID'] == 'gemini-2.5-pro'
    parts = msg_reqs[0]['body']['parts']
    assert any(p['type'] == 'text' and p['text'] for p in parts)


def test_prompt_without_model_override(fake_opencode, tmp_path):
    """Without OPENCODE_MODEL, POST body has no modelID field."""
    server = fake_opencode(session_id='sess-nomodel', result_text='## Review\n\nLooks good.')
    cwd = str(tmp_path / 'project')
    _hook.write_status(cwd, 'nomodel-test', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'nomodel-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-nomodel',
        task_id='nomodel-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
    )
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    assert 'modelID' not in msg_reqs[0]['body']
```

- [ ] **Step 2: Run to verify**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -k "test_debug_logging or test_invalid_port or test_model_override" -v
```

Expected: all PASS (these test existing code paths)

- [ ] **Step 3: Run full test suite**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v --tb=short
```

Expected: all PASS. Count should be approximately 25-30 tests.

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/test_intercept_review_agents.py
git commit -m "test(v2): logging, config edge cases, and model override"
```

---

### Task 12: Final verification and cleanup

**Files:**
- Verify: `.claude/hooks/intercept-review-agents.py` (permissions, shebang)
- Verify: `.claude/settings.json` (no changes needed)
- Verify: `.gitignore` (has `.opencode/tasks/`)

- [ ] **Step 1: Verify file permissions**

```bash
ls -la .claude/hooks/intercept-review-agents.py
# Expected: -rwxr-xr-x (executable)
# If not:
chmod +x .claude/hooks/intercept-review-agents.py
```

- [ ] **Step 2: Verify settings.json unchanged**

```bash
grep -A5 'intercept-review-agents' .claude/settings.json
```

Expected: still points to `.claude/hooks/intercept-review-agents.py` — same path as v1.

- [ ] **Step 3: Verify gitignore**

```bash
grep 'opencode' .gitignore
```

Expected: `.opencode/tasks/`

- [ ] **Step 4: Run complete test suite one final time**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v --tb=long
```

Expected: all PASS

- [ ] **Step 5: Verify the hook doesn't crash with real stdin**

Quick smoke test — pipe a fake payload and verify clean output:

```bash
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","description":"Find files","prompt":"test"},"cwd":"/tmp"}' | python3 .claude/hooks/intercept-review-agents.py
echo "Exit code: $?"
# Expected: no output, exit code 0 (pass-through for non-review call)

echo '{"tool_name":"Agent","tool_input":{"subagent_type":"superpowers:code-reviewer","description":"Review","prompt":"test"},"cwd":"/tmp"}' | OPENCODE_PORT=19999 OPENCODE_STARTUP_TIMEOUT=1 python3 .claude/hooks/intercept-review-agents.py
echo "Exit code: $?"
# Expected: no output, exit code 0 (server unreachable → fall through)
```

- [ ] **Step 6: Final commit**

```bash
git add -A
git status
# Review — only expect: intercept-review-agents.py, test file, archive, .gitignore
git commit -m "feat: OpenCode Async Bridge v2 — async review dispatch via OpenCode Server

Replaces synchronous Gemini CLI hook with async HTTP dispatch to OpenCode Server.
Background process sends blocking POST (confirmed synchronous API), subscribes to
SSE event stream for real-time progress transcript, writes results via file handshake.
Falls back to Claude agent if OpenCode is unavailable."
```

---

## Post-Implementation: Manual Integration Test

After all tasks are complete, test the full end-to-end flow manually:

1. Ensure OpenCode is authenticated: `opencode auth`
2. Start a Claude Code session in this project
3. Trigger a review (e.g., complete a task using a superpowers workflow that dispatches a code-reviewer agent)
4. Verify: hook intercepts, deny JSON appears in Claude's context, poller runs in background
5. Verify: `.opencode/tasks/{id}.status` transitions from PENDING to COMPLETE
6. Verify: `.opencode/tasks/{id}.result.md` contains the review
7. Verify: `.opencode/tasks/{id}.progress.md` contains token stream and tool call entries
8. Verify: Claude reads the result and incorporates it

**Failure case:** Kill OpenCode mid-review, verify FAILED status and that Claude retries with `[BYPASS_HOOK]`.
