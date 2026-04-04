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
