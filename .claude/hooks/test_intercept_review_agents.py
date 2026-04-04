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
