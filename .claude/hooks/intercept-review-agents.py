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
