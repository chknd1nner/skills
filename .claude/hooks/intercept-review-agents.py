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


if __name__ == '__main__':
    main()
