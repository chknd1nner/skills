#!/usr/bin/env python3
"""
intercept-review-agents.py (v2 — OpenCode Async Bridge)

PreToolUse hook: intercepts Agent calls matching TOML-configured routes and
dispatches them to OpenCode Server asynchronously. Results delivered via file
handshake.

Detection flow:
  1. description.startswith('[BYPASS_HOOK]') → pass through immediately
  2. Load opencode-router.toml → if missing/invalid, pass through
  3. Match subagent_type + description against ordered routes → first match wins
  4. No match → pass through

Route matching (opencode-router.toml):
  - match_subagent     — exact string equality (required)
  - match_description_prefix — case-insensitive startswith() (optional)
  - enabled: false     — route is skipped

Environment variables:
  OPENCODE_PORT              OpenCode Server port (default: 4096)
  OPENCODE_TIMEOUT           Background process HTTP timeout in seconds (default: 1800)
  OPENCODE_STARTUP_TIMEOUT   Server startup timeout in seconds (default: 10)
  OPENCODE_SERVER_PASSWORD   Auth password if configured
  OPENCODE_DEBUG=1           Enable debug logging (default: off)
  OPENCODE_LOG_FILE          Log file path (default: /tmp/opencode-hook-debug.log)
  OPENCODE_SKIP_POLLER=1     Test-only: suppress background process spawning
"""
import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

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


def find_matching_route(config: dict, subagent_type: str, description: str) -> tuple[dict, dict] | None:
    """Return (route, profile) for the first matching route, or None.

    Match logic per route:
    - ``match_subagent`` — exact string equality (required on every route)
    - ``match_description_prefix`` — case-insensitive ``startswith()`` (optional;
      omitted means unconstrained)
    - ``enabled: false`` routes are skipped
    """
    for route in config.get('routes', []):
        if not route.get('enabled', True):
            continue
        if route.get('match_subagent') != subagent_type:
            continue
        prefix = route.get('match_description_prefix')
        if prefix is not None and not description.lower().startswith(prefix.lower()):
            continue
        # Resolve the referenced profile (may be empty string → empty dict)
        profile_name = route.get('profile', '')
        profile = config.get('profiles', {}).get(profile_name, {})
        return route, profile
    return None


# ---------------------------------------------------------------------------
# TOML config loading
# ---------------------------------------------------------------------------
_SUPPORTED_VERSIONS = {1}
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'opencode-router.toml')


def _config_error(msg: str) -> None:
    """Log a configuration error.  Always writes to the log file and stderr
    so the operator sees the problem regardless of debug mode."""
    log_file = os.environ.get('OPENCODE_LOG_FILE', '/tmp/opencode-hook-debug.log')
    try:
        with open(log_file, 'a') as f:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            f.write(f'[{ts}] CONFIG ERROR: {msg}\n')
    except OSError:
        pass
    print(f'OpenCode hook config error: {msg}', file=sys.stderr)


def _validate_profiles(profiles: dict) -> list[str]:
    """Validate profile definitions.  Returns a list of error strings (empty = valid)."""
    errors: list[str] = []
    for name, prof in profiles.items():
        if 'agent' not in prof:
            errors.append(f"profile '{name}' missing required field 'agent'")
        has_provider = 'provider' in prof
        has_model = 'model' in prof
        if has_provider and not has_model:
            errors.append(f"profile '{name}' sets 'provider' without 'model'")
        if has_model and not has_provider:
            errors.append(f"profile '{name}' sets 'model' without 'provider'")
    return errors


def _validate_routes(routes: list[dict], profile_names: set[str]) -> list[str]:
    """Validate route definitions.  Returns a list of error strings (empty = valid)."""
    errors: list[str] = []
    for i, route in enumerate(routes):
        label = route.get('name', f'routes[{i}]')
        if 'match_subagent' not in route:
            errors.append(f"route '{label}' missing required field 'match_subagent'")
        if 'profile' not in route:
            errors.append(f"route '{label}' missing required field 'profile'")
        ref = route.get('profile', '')
        if ref and ref not in profile_names:
            errors.append(f"route '{label}' references unknown profile '{ref}'")
    return errors


def _normalize_config(raw: dict) -> dict:
    """Transform parsed TOML into the internal config structure."""
    defaults = dict(raw.get('defaults', {}))

    profiles: dict = {}
    for name, prof in raw.get('profiles', {}).items():
        profiles[name] = {
            'agent': prof['agent'],
            'provider': prof.get('provider'),
            'model': prof.get('model'),
            'timeout_seconds': prof.get('timeout_seconds'),
        }

    routes: list[dict] = []
    for route in raw.get('routes', []):
        routes.append({
            'name': route.get('name', ''),
            'enabled': route.get('enabled', True),
            'match_subagent': route.get('match_subagent', ''),
            'match_description_prefix': route.get('match_description_prefix'),
            'profile': route.get('profile', ''),
        })

    return {
        'defaults': defaults,
        'profiles': profiles,
        'routes': routes,
    }


def load_config(path: str | None = None) -> dict | None:
    """Load and validate the TOML config file.

    Returns the normalized config dict, or None if:
    - the file is missing (silent pass-through)
    - the file is invalid TOML
    - validation fails

    None means "fall through to Claude" — the hook should not crash.
    """
    config_path = path if path is not None else _CONFIG_PATH
    try:
        with open(config_path, 'rb') as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        return None
    except (tomllib.TOMLDecodeError, OSError) as exc:
        _config_error(f'failed to parse {config_path}: {exc}')
        return None

    # Version gate
    version = raw.get('version')
    if version not in _SUPPORTED_VERSIONS:
        _config_error(f"unsupported config version {version!r} (supported: {_SUPPORTED_VERSIONS})")
        return None

    # Type guards — malformed TOML can produce unexpected types
    raw_profiles = raw.get('profiles', {})
    if not isinstance(raw_profiles, dict):
        _config_error(f"'profiles' must be a table, got {type(raw_profiles).__name__}")
        return None
    raw_routes = raw.get('routes', [])
    if not isinstance(raw_routes, list):
        _config_error(f"'routes' must be an array, got {type(raw_routes).__name__}")
        return None

    # Validate profiles
    profile_errors = _validate_profiles(raw_profiles)
    if profile_errors:
        for err in profile_errors:
            _config_error(err)
        return None

    # Validate routes
    route_errors = _validate_routes(raw_routes, set(raw_profiles.keys()))
    if route_errors:
        for err in route_errors:
            _config_error(err)
        return None

    return _normalize_config(raw)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def tasks_dir(cwd: str) -> str:
    """Path to .opencode/tasks/ under the project root."""
    return os.path.join(cwd, '.opencode', 'tasks')


def write_status(cwd: str, task_id: str, status: str) -> None:
    """Write status string to {task_id}.status file (atomic via rename)."""
    d = tasks_dir(cwd)
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, f'{task_id}.status')
    tmp = final + '.tmp'
    with open(tmp, 'w') as f:
        f.write(status)
    os.replace(tmp, final)


def read_status(cwd: str, task_id: str) -> str:
    """Read status file, return empty string if missing."""
    try:
        with open(os.path.join(tasks_dir(cwd), f'{task_id}.status')) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ''


def write_result(cwd: str, task_id: str, content: str) -> None:
    """Write review content to {task_id}.result.md file (atomic via rename)."""
    d = tasks_dir(cwd)
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, f'{task_id}.result.md')
    tmp = final + '.tmp'
    with open(tmp, 'w') as f:
        f.write(content)
    os.replace(tmp, final)


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


def start_server(port: int, startup_timeout: int, password: str | None = None, path_override: str | None = None, cwd: str | None = None) -> tuple[bool, str]:
    """
    Start opencode serve and wait until healthy or failure.
    Returns (success, error_message).

    Server stderr is redirected to OPENCODE_LOG_FILE (not PIPE) to prevent
    deadlock — the server is long-lived and PIPE buffers would fill and block it.
    On early exit, the tail of the log file is read for the error message.

    cwd: working directory for the server process — sessions inherit this.
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
            cwd=cwd or None,
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


def ensure_server(port: int, startup_timeout: int, password: str | None = None, path_override: str | None = None, cwd: str | None = None) -> tuple[bool, str]:
    """Health check first, start if needed."""
    if health_check(port, password):
        return True, ''
    return start_server(port, startup_timeout, password, path_override, cwd=cwd)


# ---------------------------------------------------------------------------
# Port resolution
# ---------------------------------------------------------------------------
def is_port_free(port: int) -> bool:
    """Check if a port is free by attempting a TCP connect."""
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return False  # something is listening
    except (ConnectionRefusedError, OSError):
        return True  # nothing listening — port is free


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
    profile: dict,
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

    # Send blocking POST — body uses agent + optional model object from profile
    url = f'http://127.0.0.1:{port}/session/{session_id}/message'
    body: dict = {
        'agent': profile.get('agent', ''),
        'parts': [{'type': 'text', 'text': prompt}],
    }
    if profile.get('provider') and profile.get('model'):
        body['model'] = {
            'providerID': profile['provider'],
            'modelID': profile['model'],
        }
    data = json.dumps(body).encode()
    req = Request(url, data=data, headers={'Content-Type': 'application/json'})
    if password:
        req.add_header('Authorization', f'Bearer {password}')

    try:
        with urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read()
    except (URLError, OSError) as e:
        log(f'bg: POST failed | task={task_id} | err={e}')
        stop_event.set()
        sse.join(timeout=2)
        write_status(cwd, task_id, 'FAILED')
        return

    # Signal SSE thread to exit, then wait for it to drain buffered events
    stop_event.set()
    sse.join(timeout=5)

    # Parse and validate response
    if not raw_body:
        log(f'bg: empty response body | task={task_id}')
        write_status(cwd, task_id, 'FAILED')
        return

    try:
        response = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError) as e:
        log(f'bg: invalid JSON response | task={task_id} | err={e}')
        write_status(cwd, task_id, 'FAILED')
        return

    if 'info' not in response:
        log(f'bg: missing info in response | task={task_id}')
        write_status(cwd, task_id, 'FAILED')
        return

    if 'parts' not in response:
        log(f'bg: missing parts in response | task={task_id}')
        write_status(cwd, task_id, 'FAILED')
        return

    # Verify terminal state
    finish = response['info'].get('finish', '')
    if finish != 'stop':
        log(f'bg: unexpected finish={finish!r} | task={task_id}')
        write_status(cwd, task_id, 'FAILED')
        return

    # Extract text parts and write result
    text_parts = [
        p['text']
        for p in response['parts']
        if p.get('type') == 'text' and p.get('text')
    ]
    result_text = '\n\n'.join(text_parts)
    write_result(cwd, task_id, result_text)
    write_status(cwd, task_id, 'COMPLETE')
    log(f'bg: complete | task={task_id} | bytes={len(result_text)}')


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

    # Load config — if missing or invalid, pass through silently
    config = load_config()
    if config is None:
        log(f'no config (missing or invalid), passing through | type={subagent_type}')
        sys.exit(0)

    # Find first matching route
    match = find_matching_route(config, subagent_type, description)
    if match is None:
        log(f'no route matched, passing through | type={subagent_type} | desc={description[:60]}')
        sys.exit(0)

    matched_route, matched_profile = match
    log(f'intercepted | route={matched_route.get("name", "?")} | type={subagent_type} | desc={description[:60]}')

    # Startup timeout: env override → TOML defaults → hard-coded
    toml_startup = config.get('defaults', {}).get('startup_timeout_seconds', 10)
    startup_timeout = _int_env('OPENCODE_STARTUP_TIMEOUT', toml_startup)
    password = os.environ.get('OPENCODE_SERVER_PASSWORD', '') or None

    # Determine config path and profile name for the poller subprocess
    config_path = _CONFIG_PATH
    profile_name = matched_route.get('profile', '')

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

    # Generate task ID and create session
    task_id = uuid.uuid4().hex[:12]

    session_id = create_session(port, password)
    if not session_id:
        log('failed to create session | falling back to Claude agent')
        sys.exit(0)

    # Prepend working directory context so the model knows where the repo is,
    # even if the server was started from a different directory.
    if cwd:
        prompt = f'**Working directory:** `{cwd}`\n\n' + prompt

    # Write prompt to file (background process reads it)
    write_status(cwd, task_id, 'PENDING')  # also creates tasks dir
    prompt_file = os.path.join(tasks_dir(cwd), f'{task_id}.prompt')
    with open(prompt_file, 'w') as f:
        f.write(prompt)

    # Spawn background process (skip in tests via OPENCODE_SKIP_POLLER=1)
    if os.environ.get('OPENCODE_SKIP_POLLER', '0') != '1':
        log_file = os.environ.get('OPENCODE_LOG_FILE', '/tmp/opencode-hook-debug.log')
        poller_stderr = open(log_file, 'a') if _DEBUG else subprocess.DEVNULL
        subprocess.Popen(
            [sys.executable, __file__, '--poll', session_id, task_id, str(port), cwd,
             config_path, profile_name],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=poller_stderr,
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


def main_poll(session_id: str, task_id: str, port: int, cwd: str,
              config_path: str, profile_name: str) -> None:
    """Entry point for --poll mode (background process subprocess)."""
    password = os.environ.get('OPENCODE_SERVER_PASSWORD', '') or None

    # Reload config in the child process and look up the profile
    config = load_config(config_path)
    profile = {}
    if config is not None:
        profile = config.get('profiles', {}).get(profile_name, {})

    # Request timeout: env override → profile → hard-coded
    toml_timeout = profile.get('timeout_seconds', 1800) or 1800
    timeout = _int_env('OPENCODE_TIMEOUT', toml_timeout)

    run_background_process(port, session_id, task_id, cwd, timeout, profile, password)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--poll':
        if len(sys.argv) != 8:
            print(
                f'Usage: {sys.argv[0]} --poll <session_id> <task_id> <port> <cwd> <config_path> <profile_name>',
                file=sys.stderr,
            )
            sys.exit(1)
        main_poll(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5],
                  sys.argv[6], sys.argv[7])
    else:
        main()
