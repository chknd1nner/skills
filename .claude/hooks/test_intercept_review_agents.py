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
    config_path: str = '',
    profile_name: str = '',
) -> subprocess.CompletedProcess:
    """Invoke the hook in --poll mode."""
    merged = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, SCRIPT, '--poll', session_id, task_id, str(port), cwd,
         config_path, profile_name],
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

            # Support raw_response_body for malformed response testing
            raw_body = self.server.config.get('raw_response_body', None)
            if raw_body is not None:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(raw_body if isinstance(raw_body, bytes) else raw_body.encode())
                return

            result_text = self.server.config.get('result_text', '## Review\n\nLooks good.')
            finish = self.server.config.get('finish', 'stop')
            response = {
                'info': {
                    'id': 'msg_fake123',
                    'sessionID': self.server.config.get('session_id', 'fake-session-123'),
                    'role': 'assistant',
                    'finish': finish,
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

            # Allow removing keys for malformed response tests
            for key in self.server.config.get('response_omit_keys', []):
                response.pop(key, None)

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


def test_bypass_flag_passes_through():
    """[BYPASS_HOOK] prefix in description → immediate pass-through, no interception."""
    result = run_hook(make_payload(
        'superpowers:code-reviewer',
        '[BYPASS_HOOK] Review implementation',
    ))
    assert result.returncode == 0
    assert result.stdout == ''


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
# Port resolution
# ---------------------------------------------------------------------------

def test_is_port_free_unused_port():
    """A port with nothing listening is free."""
    assert _hook.is_port_free(59999) is True


def test_is_port_free_used_port(fake_opencode):
    """A port with a server listening is not free."""
    server = fake_opencode()
    assert _hook.is_port_free(server.port) is False


def test_resolve_port_env_override():
    """OPENCODE_PORT set → return that port, skip auto-selection."""
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
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
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
        config_path=config_path,
        profile_name='minimal',
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
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
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
        config_path=config_path,
        profile_name='minimal',
    )
    assert result.returncode == 0

    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-2.status').read_text()
    assert status.strip() == 'FAILED'


def test_background_server_crash_writes_failed(tmp_path):
    """POST can't reach server → FAILED."""
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
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
        config_path=config_path,
        profile_name='minimal',
    )
    assert result.returncode == 0

    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-3.status').read_text()
    assert status.strip() == 'FAILED'


def test_background_extracts_multiple_text_parts(fake_opencode, tmp_path):
    """Multiple text parts in response are joined in result file."""
    server = fake_opencode(result_text='## Strengths\n\nClean.\n\n## Issues\n\nMissing error handling.')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    _hook.write_status(cwd, 'bg-test-4', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'bg-test-4.prompt').write_text('Review this.')

    run_poller(session_id='sess-abc', task_id='bg-test-4', port=server.port,
               cwd=cwd, env={'OPENCODE_TIMEOUT': '10'},
               config_path=config_path, profile_name='minimal')

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

    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    run_poller(session_id='sess-abc', task_id='bg-test-5', port=server.port,
               cwd=cwd, env={'OPENCODE_TIMEOUT': '10'},
               config_path=config_path, profile_name='minimal')

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

    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    run_poller(session_id='sess-abc', task_id='bg-test-6', port=server.port,
               cwd=cwd, env={'OPENCODE_TIMEOUT': '5'},
               config_path=config_path, profile_name='minimal')

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


def test_model_override_included_in_body(fake_opencode, tmp_path):
    """Profile with provider+model sends agent and model object in POST body."""
    server = fake_opencode(session_id='sess-model', result_text='## Review\n\nLooks good.')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _FULL_PROFILE_TOML)
    _hook.write_status(cwd, 'model-test', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'model-test.prompt').write_text('Review this.')

    result = run_poller(
        session_id='sess-model',
        task_id='model-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='review_gpt54',
    )
    assert result.returncode == 0
    # Verify agent and model object were sent in the POST body
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    body = msg_reqs[0]['body']
    assert body['agent'] == 'code-reviewer'
    assert body['model'] == {'providerID': 'poe', 'modelID': 'openai/gpt-5.4'}
    assert 'modelID' not in body  # no flat modelID field
    parts = body['parts']
    assert any(p['type'] == 'text' and p['text'] for p in parts)


def test_prompt_without_model_override(fake_opencode, tmp_path):
    """Profile with agent only (no provider/model) → agent sent, no model object."""
    server = fake_opencode(session_id='sess-nomodel', result_text='## Review\n\nLooks good.')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    _hook.write_status(cwd, 'nomodel-test', 'PENDING')
    import pathlib
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'nomodel-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-nomodel',
        task_id='nomodel-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='minimal',
    )
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    body = msg_reqs[0]['body']
    assert body['agent'] == 'code-reviewer'
    assert 'model' not in body
    assert 'modelID' not in body


def test_auth_header_forwarded_to_message(fake_opencode, tmp_path):
    """OPENCODE_SERVER_PASSWORD is sent as Bearer token on /message POST."""
    server = fake_opencode(session_id='sess-auth', result_text='## Review\n\nOk.')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
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
            'OPENCODE_SERVER_PASSWORD': 'test-secret-123',
        },
        config_path=config_path,
        profile_name='minimal',
    )

    # Check /message POST has auth header
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    assert msg_reqs[0]['headers'].get('Authorization') == 'Bearer test-secret-123'


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


# ---------------------------------------------------------------------------
# TOML config loading
# ---------------------------------------------------------------------------

_VALID_TOML = """\
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
"""


def _write_toml(tmp_path, content: str) -> str:
    """Write TOML content to a temp file and return its path."""
    p = tmp_path / 'opencode-router.toml'
    p.write_text(content)
    return str(p)


# Minimal TOML with agent-only profile (no provider/model override)
_AGENT_ONLY_TOML = """\
version = 1

[profiles.minimal]
agent = "code-reviewer"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "minimal"
"""

# TOML with full provider+model override
_FULL_PROFILE_TOML = """\
version = 1

[profiles.review_gpt54]
agent = "code-reviewer"
provider = "poe"
model = "openai/gpt-5.4"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "review_gpt54"
"""


def test_config_valid_parse(tmp_path):
    """Valid TOML config is parsed and normalized correctly."""
    path = _write_toml(tmp_path, _VALID_TOML)
    cfg = _hook.load_config(path)
    assert cfg is not None

    # Defaults
    assert cfg['defaults']['startup_timeout_seconds'] == 10

    # Profiles
    assert 'review_gpt54' in cfg['profiles']
    assert cfg['profiles']['review_gpt54']['agent'] == 'code-reviewer'
    assert cfg['profiles']['review_gpt54']['provider'] == 'poe'
    assert cfg['profiles']['review_gpt54']['model'] == 'openai/gpt-5.4'
    assert cfg['profiles']['review_gpt54']['timeout_seconds'] == 1200

    assert 'implementor_sonnet' in cfg['profiles']
    assert cfg['profiles']['implementor_sonnet']['agent'] == 'implementor'
    assert cfg['profiles']['implementor_sonnet']['timeout_seconds'] == 3600

    # Routes
    assert len(cfg['routes']) == 2
    r0 = cfg['routes'][0]
    assert r0['name'] == 'superpowers-review'
    assert r0['enabled'] is True
    assert r0['match_subagent'] == 'superpowers:code-reviewer'
    assert r0['match_description_prefix'] is None
    assert r0['profile'] == 'review_gpt54'

    r1 = cfg['routes'][1]
    assert r1['name'] == 'general-review-prefix'
    assert r1['match_subagent'] == 'general-purpose'
    assert r1['match_description_prefix'] == 'review'
    assert r1['profile'] == 'review_gpt54'


def test_config_missing_file_returns_none(tmp_path):
    """Missing config file returns None silently (no error logged)."""
    cfg = _hook.load_config(str(tmp_path / 'nonexistent.toml'))
    assert cfg is None


def test_config_missing_profile_reference(tmp_path, capsys):
    """Route references a profile that doesn't exist -> returns None with error."""
    toml_content = """\
version = 1

[profiles.real_profile]
agent = "code-reviewer"

[[routes]]
name = "bad-route"
match_subagent = "superpowers:code-reviewer"
profile = "nonexistent_profile"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is None
    captured = capsys.readouterr()
    assert 'nonexistent_profile' in captured.err


def test_config_missing_agent_field(tmp_path, capsys):
    """Profile missing 'agent' field -> returns None with error."""
    toml_content = """\
version = 1

[profiles.bad_profile]
provider = "poe"
model = "openai/gpt-5.4"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "bad_profile"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is None
    captured = capsys.readouterr()
    assert "missing required field 'agent'" in captured.err


def test_config_provider_without_model(tmp_path, capsys):
    """Profile sets 'provider' without 'model' -> returns None with error."""
    toml_content = """\
version = 1

[profiles.bad_profile]
agent = "code-reviewer"
provider = "poe"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "bad_profile"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is None
    captured = capsys.readouterr()
    assert "'provider' without 'model'" in captured.err


def test_config_model_without_provider(tmp_path, capsys):
    """Profile sets 'model' without 'provider' -> returns None with error."""
    toml_content = """\
version = 1

[profiles.bad_profile]
agent = "code-reviewer"
model = "openai/gpt-5.4"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "bad_profile"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is None
    captured = capsys.readouterr()
    assert "'model' without 'provider'" in captured.err


def test_config_route_missing_match_subagent(tmp_path, capsys):
    """Route missing match_subagent -> returns None with error."""
    toml_content = """\
version = 1

[profiles.review_gpt54]
agent = "code-reviewer"

[[routes]]
name = "no-subagent-route"
profile = "review_gpt54"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is None
    captured = capsys.readouterr()
    assert "missing required field 'match_subagent'" in captured.err


def test_config_disabled_routes_preserved(tmp_path):
    """Disabled routes are preserved in the structure (filtering happens at match time)."""
    toml_content = """\
version = 1

[profiles.review_gpt54]
agent = "code-reviewer"

[[routes]]
name = "disabled-route"
enabled = false
match_subagent = "superpowers:code-reviewer"
profile = "review_gpt54"

[[routes]]
name = "enabled-route"
enabled = true
match_subagent = "general-purpose"
profile = "review_gpt54"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is not None
    assert len(cfg['routes']) == 2
    assert cfg['routes'][0]['enabled'] is False
    assert cfg['routes'][0]['name'] == 'disabled-route'
    assert cfg['routes'][1]['enabled'] is True
    assert cfg['routes'][1]['name'] == 'enabled-route'


def test_config_description_prefix_stored_as_is(tmp_path):
    """Description prefix is stored as-is; case-insensitive matching is at match time."""
    toml_content = """\
version = 1

[profiles.review_gpt54]
agent = "code-reviewer"

[[routes]]
name = "mixed-case-route"
match_subagent = "general-purpose"
match_description_prefix = "Review"
profile = "review_gpt54"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is not None
    assert cfg['routes'][0]['match_description_prefix'] == 'Review'


def test_config_unsupported_version(tmp_path, capsys):
    """Unsupported version -> returns None with error."""
    toml_content = """\
version = 99

[profiles.review_gpt54]
agent = "code-reviewer"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "review_gpt54"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is None
    captured = capsys.readouterr()
    assert 'unsupported config version' in captured.err


def test_config_missing_version(tmp_path, capsys):
    """Missing version field -> returns None with error (version is None, not in supported set)."""
    toml_content = """\
[profiles.review_gpt54]
agent = "code-reviewer"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "review_gpt54"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is None
    captured = capsys.readouterr()
    assert 'unsupported config version' in captured.err


def test_config_invalid_toml_syntax(tmp_path, capsys):
    """Malformed TOML -> returns None with error."""
    path = _write_toml(tmp_path, 'this is not [valid toml = }}}')
    cfg = _hook.load_config(path)
    assert cfg is None
    captured = capsys.readouterr()
    assert 'failed to parse' in captured.err


def test_config_profile_with_agent_only(tmp_path):
    """Profile with only 'agent' (no provider/model) is valid."""
    toml_content = """\
version = 1

[profiles.minimal]
agent = "code-reviewer"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "minimal"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is not None
    assert cfg['profiles']['minimal']['agent'] == 'code-reviewer'
    assert cfg['profiles']['minimal']['provider'] is None
    assert cfg['profiles']['minimal']['model'] is None


def test_config_provider_model_pair_valid(tmp_path):
    """Profile with both provider and model is valid."""
    toml_content = """\
version = 1

[profiles.full]
agent = "code-reviewer"
provider = "poe"
model = "openai/gpt-5.4"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "full"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is not None
    assert cfg['profiles']['full']['provider'] == 'poe'
    assert cfg['profiles']['full']['model'] == 'openai/gpt-5.4'


def test_config_real_file():
    """The actual opencode-router.toml in the hooks directory loads successfully."""
    cfg = _hook.load_config(_hook._CONFIG_PATH)
    assert cfg is not None
    assert cfg['defaults']['startup_timeout_seconds'] == 10
    assert 'review_gpt54' in cfg['profiles']
    assert len(cfg['routes']) >= 2


def test_config_empty_routes_valid(tmp_path):
    """Config with profiles but no routes is valid (nothing will match)."""
    toml_content = """\
version = 1

[profiles.review_gpt54]
agent = "code-reviewer"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is not None
    assert cfg['routes'] == []


def test_config_route_without_profile_field(tmp_path):
    """Route without a profile field is valid (profile defaults to empty string)."""
    toml_content = """\
version = 1

[[routes]]
name = "no-profile-route"
match_subagent = "superpowers:code-reviewer"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is not None
    assert cfg['routes'][0]['profile'] == ''


# ---------------------------------------------------------------------------
# Route matching (find_matching_route)
# ---------------------------------------------------------------------------

_ROUTE_CONFIG = {
    'defaults': {},
    'profiles': {
        'review_gpt54': {
            'agent': 'code-reviewer',
            'provider': 'poe',
            'model': 'openai/gpt-5.4',
            'timeout_seconds': 1200,
        },
        'implementor_sonnet': {
            'agent': 'implementor',
            'provider': 'poe',
            'model': 'anthropic/claude-sonnet-4.6',
            'timeout_seconds': 3600,
        },
    },
    'routes': [
        {
            'name': 'superpowers-review',
            'enabled': True,
            'match_subagent': 'superpowers:code-reviewer',
            'match_description_prefix': None,
            'profile': 'review_gpt54',
        },
        {
            'name': 'general-review-prefix',
            'enabled': True,
            'match_subagent': 'general-purpose',
            'match_description_prefix': 'review',
            'profile': 'review_gpt54',
        },
    ],
}


def test_route_match_code_reviewer():
    """Exact subagent_type 'superpowers:code-reviewer' matches the first route."""
    result = _hook.find_matching_route(_ROUTE_CONFIG, 'superpowers:code-reviewer', 'Review impl')
    assert result is not None
    route, profile = result
    assert route['name'] == 'superpowers-review'
    assert profile['agent'] == 'code-reviewer'
    assert profile['model'] == 'openai/gpt-5.4'


def test_route_match_general_purpose_review_prefix():
    """general-purpose + description starting with 'review' matches the second route."""
    result = _hook.find_matching_route(_ROUTE_CONFIG, 'general-purpose', 'Review the code')
    assert result is not None
    route, profile = result
    assert route['name'] == 'general-review-prefix'
    assert profile['agent'] == 'code-reviewer'


def test_route_match_description_prefix_case_insensitive():
    """match_description_prefix is case-insensitive."""
    result = _hook.find_matching_route(_ROUTE_CONFIG, 'general-purpose', 'REVIEW THE CODE')
    assert result is not None
    route, _ = result
    assert route['name'] == 'general-review-prefix'

    result2 = _hook.find_matching_route(_ROUTE_CONFIG, 'general-purpose', 'rEvIeW mixed case')
    assert result2 is not None
    route2, _ = result2
    assert route2['name'] == 'general-review-prefix'


def test_route_no_match_falls_through():
    """No matching route returns None."""
    result = _hook.find_matching_route(_ROUTE_CONFIG, 'Explore', 'Find relevant files')
    assert result is None


def test_route_no_match_general_purpose_wrong_prefix():
    """general-purpose with non-review description does not match."""
    result = _hook.find_matching_route(_ROUTE_CONFIG, 'general-purpose', 'Explore the codebase')
    assert result is None


def test_route_first_match_wins():
    """When two routes could match, the first one declared wins."""
    config = {
        'defaults': {},
        'profiles': {
            'profile_a': {'agent': 'agent-a', 'provider': None, 'model': None, 'timeout_seconds': None},
            'profile_b': {'agent': 'agent-b', 'provider': None, 'model': None, 'timeout_seconds': None},
        },
        'routes': [
            {
                'name': 'first-route',
                'enabled': True,
                'match_subagent': 'superpowers:code-reviewer',
                'match_description_prefix': None,
                'profile': 'profile_a',
            },
            {
                'name': 'second-route',
                'enabled': True,
                'match_subagent': 'superpowers:code-reviewer',
                'match_description_prefix': None,
                'profile': 'profile_b',
            },
        ],
    }
    result = _hook.find_matching_route(config, 'superpowers:code-reviewer', 'Review impl')
    assert result is not None
    route, profile = result
    assert route['name'] == 'first-route'
    assert profile['agent'] == 'agent-a'


def test_route_disabled_route_skipped():
    """Disabled routes are skipped even if they would otherwise match."""
    config = {
        'defaults': {},
        'profiles': {
            'profile_a': {'agent': 'agent-a', 'provider': None, 'model': None, 'timeout_seconds': None},
            'profile_b': {'agent': 'agent-b', 'provider': None, 'model': None, 'timeout_seconds': None},
        },
        'routes': [
            {
                'name': 'disabled-route',
                'enabled': False,
                'match_subagent': 'superpowers:code-reviewer',
                'match_description_prefix': None,
                'profile': 'profile_a',
            },
            {
                'name': 'enabled-route',
                'enabled': True,
                'match_subagent': 'superpowers:code-reviewer',
                'match_description_prefix': None,
                'profile': 'profile_b',
            },
        ],
    }
    result = _hook.find_matching_route(config, 'superpowers:code-reviewer', 'Review impl')
    assert result is not None
    route, profile = result
    assert route['name'] == 'enabled-route'
    assert profile['agent'] == 'agent-b'


def test_route_disabled_all_routes_no_match():
    """If all matching routes are disabled, returns None."""
    config = {
        'defaults': {},
        'profiles': {
            'profile_a': {'agent': 'agent-a', 'provider': None, 'model': None, 'timeout_seconds': None},
        },
        'routes': [
            {
                'name': 'disabled-route',
                'enabled': False,
                'match_subagent': 'superpowers:code-reviewer',
                'match_description_prefix': None,
                'profile': 'profile_a',
            },
        ],
    }
    result = _hook.find_matching_route(config, 'superpowers:code-reviewer', 'Review impl')
    assert result is None


def test_route_missing_profile_returns_empty_dict():
    """Route referencing empty profile string resolves to empty dict."""
    config = {
        'defaults': {},
        'profiles': {},
        'routes': [
            {
                'name': 'no-profile-route',
                'enabled': True,
                'match_subagent': 'superpowers:code-reviewer',
                'match_description_prefix': None,
                'profile': '',
            },
        ],
    }
    result = _hook.find_matching_route(config, 'superpowers:code-reviewer', 'Review impl')
    assert result is not None
    route, profile = result
    assert route['name'] == 'no-profile-route'
    assert profile == {}


def test_route_empty_routes_no_match():
    """Config with no routes returns None."""
    config = {'defaults': {}, 'profiles': {}, 'routes': []}
    result = _hook.find_matching_route(config, 'superpowers:code-reviewer', 'Review impl')
    assert result is None


# ---------------------------------------------------------------------------
# Route matching — integration via subprocess (main hook)
# ---------------------------------------------------------------------------

def test_hook_no_config_passes_through(tmp_path, monkeypatch):
    """Missing config file → pass through silently (exit 0, no output)."""
    # Point config path to a non-existent file
    monkeypatch.setattr(_hook, '_CONFIG_PATH', str(tmp_path / 'nonexistent.toml'))
    # Use subprocess-free approach: call main() directly with patched stdin
    import io
    payload = make_payload('superpowers:code-reviewer')
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))

    with pytest.raises(SystemExit) as exc_info:
        _hook.main()
    assert exc_info.value.code == 0


def test_hook_bypass_before_config_loading(monkeypatch):
    """Bypass flag short-circuits before config is loaded."""
    # Make config loading explode if called
    def boom(path=None):
        raise RuntimeError('config should not be loaded when bypass is active')
    monkeypatch.setattr(_hook, 'load_config', boom)

    import io
    payload = make_payload('superpowers:code-reviewer', '[BYPASS_HOOK] Review implementation')
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))

    with pytest.raises(SystemExit) as exc_info:
        _hook.main()
    assert exc_info.value.code == 0


def test_hook_no_route_match_passes_through(tmp_path, monkeypatch):
    """Subagent type with no matching route → pass through silently."""
    toml_content = """\
version = 1

[profiles.review_gpt54]
agent = "code-reviewer"

[[routes]]
name = "superpowers-review"
match_subagent = "superpowers:code-reviewer"
profile = "review_gpt54"
"""
    path = _write_toml(tmp_path, toml_content)
    monkeypatch.setattr(_hook, '_CONFIG_PATH', path)

    import io
    payload = make_payload('Explore', 'Find relevant files')
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))

    with pytest.raises(SystemExit) as exc_info:
        _hook.main()
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Payload shape — agent + model dispatch
# ---------------------------------------------------------------------------

def test_payload_agent_always_sent(fake_opencode, tmp_path):
    """Agent field is always present in POST body for a matched route."""
    server = fake_opencode(session_id='sess-agent', result_text='Ok.')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    _hook.write_status(cwd, 'agent-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'agent-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-agent',
        task_id='agent-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='minimal',
    )
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    assert msg_reqs[0]['body']['agent'] == 'code-reviewer'


def test_payload_model_object_sent_when_provider_model_present(fake_opencode, tmp_path):
    """Profile with provider+model → model object with providerID/modelID is sent."""
    server = fake_opencode(session_id='sess-full', result_text='Ok.')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _FULL_PROFILE_TOML)
    _hook.write_status(cwd, 'full-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'full-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-full',
        task_id='full-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='review_gpt54',
    )
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    body = msg_reqs[0]['body']
    assert body['agent'] == 'code-reviewer'
    assert body['model'] == {'providerID': 'poe', 'modelID': 'openai/gpt-5.4'}


def test_payload_model_omitted_when_agent_only(fake_opencode, tmp_path):
    """Profile with agent only → no model object in POST body."""
    server = fake_opencode(session_id='sess-agentonly', result_text='Ok.')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    _hook.write_status(cwd, 'agentonly-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'agentonly-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-agentonly',
        task_id='agentonly-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='minimal',
    )
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    body = msg_reqs[0]['body']
    assert body['agent'] == 'code-reviewer'
    assert 'model' not in body
    assert 'modelID' not in body


# ---------------------------------------------------------------------------
# Malformed response handling
# ---------------------------------------------------------------------------

def test_empty_response_body_produces_failed(fake_opencode, tmp_path):
    """200 OK with empty body → FAILED (e.g., invalid agent name)."""
    server = fake_opencode(session_id='sess-empty', raw_response_body=b'')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    _hook.write_status(cwd, 'empty-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'empty-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-empty',
        task_id='empty-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='minimal',
    )
    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'empty-test.status').read_text()
    assert status.strip() == 'FAILED'


def test_invalid_json_body_produces_failed(fake_opencode, tmp_path):
    """200 OK with invalid JSON body → FAILED."""
    server = fake_opencode(session_id='sess-badjson', raw_response_body=b'not valid json {{{')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    _hook.write_status(cwd, 'badjson-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'badjson-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-badjson',
        task_id='badjson-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='minimal',
    )
    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'badjson-test.status').read_text()
    assert status.strip() == 'FAILED'


def test_finish_not_stop_produces_failed(fake_opencode, tmp_path):
    """Response with finish != 'stop' → FAILED."""
    server = fake_opencode(session_id='sess-badfinish', finish='error')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    _hook.write_status(cwd, 'badfinish-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'badfinish-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-badfinish',
        task_id='badfinish-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='minimal',
    )
    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'badfinish-test.status').read_text()
    assert status.strip() == 'FAILED'


def test_missing_info_in_response_produces_failed(fake_opencode, tmp_path):
    """Response JSON with no 'info' key → FAILED."""
    server = fake_opencode(session_id='sess-noinfo', response_omit_keys=['info'])
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    _hook.write_status(cwd, 'noinfo-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'noinfo-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-noinfo',
        task_id='noinfo-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='minimal',
    )
    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'noinfo-test.status').read_text()
    assert status.strip() == 'FAILED'


def test_missing_parts_in_response_produces_failed(fake_opencode, tmp_path):
    """Response JSON with no 'parts' key → FAILED."""
    server = fake_opencode(session_id='sess-noparts', response_omit_keys=['parts'])
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _AGENT_ONLY_TOML)
    _hook.write_status(cwd, 'noparts-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'noparts-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-noparts',
        task_id='noparts-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='minimal',
    )
    status = (tmp_path / 'project' / '.opencode' / 'tasks' / 'noparts-test.status').read_text()
    assert status.strip() == 'FAILED'
