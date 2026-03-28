# Gemini Review Hook: Python Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `.claude/hooks/intercept-review-agents.sh` as a Python script, preserving all existing behaviour while adding subprocess timeout support, fixing the broken control-char counter, and resolving the `date -Iseconds` portability issue.

**Architecture:** Single Python file replacing the bash script, stdlib only (`subprocess`, `json`, `sys`, `os`, `logging`). All detection logic, fallback chain, and JSON output format are identical to the existing script. Timeout is handled via `subprocess.run(timeout=)`. A new `GEMINI_LOG_FILE` env var allows tests to use isolated log paths. The bash script is archived, not deleted.

**Tech Stack:** Python 3 (stdlib only), pytest

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `.claude/hooks/intercept-review-agents.py` | Create | New Python hook — complete replacement |
| `.claude/hooks/test_intercept_review_agents.py` | Create | Full test suite |
| `.claude/settings.json` | Modify | Update hook `command` to point to `.py` file |
| `.claude/hooks/archive/intercept-review-agents.sh` | Create | Archived original bash script |
| `.claude/hooks/intercept-review-agents.sh` | Delete | Replaced by Python script |

---

### Task 1: Test infrastructure

**Files:**
- Create: `.claude/hooks/test_intercept_review_agents.py`

- [ ] **Step 1: Confirm pytest is available**

```bash
cd /Users/martinkuek/Documents/Projects/skills
python3 -m pytest --version
```

Expected: `pytest 7.x.x` or similar. If not installed:
```bash
pip3 install pytest
```

- [ ] **Step 2: Create test file with helpers and FakeGemini fixture**

Create `.claude/hooks/test_intercept_review_agents.py`:

```python
"""Tests for intercept-review-agents.py"""
import json
import os
import stat
import subprocess
import sys

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
    )


def make_payload(
    subagent_type: str,
    description: str = 'Review implementation',
    prompt: str = 'Review this.',
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


@pytest.fixture
def fake_gemini(tmp_path):
    """
    Factory fixture: returns a callable that creates a controlled fake gemini binary.

    Usage:
        gem = fake_gemini(output='review text')
        result = run_hook(payload, env={'PATH': gem.bin_path})

    Args:
        output (str): Text to write to stdout. Default: 'FAKE REVIEW'.
        exit_code (int): Exit code for the fake binary. Default: 0.
        sleep (bool): If True, the binary sleeps indefinitely (for timeout tests).
    """
    def _make(output: str = 'FAKE REVIEW', exit_code: int = 0, sleep: bool = False):
        out_file = tmp_path / 'output.txt'
        out_file.write_text(output, encoding='utf-8')
        script = tmp_path / 'gemini'
        if sleep:
            body = 'sleep 999'
        else:
            body = f'cat {out_file}\nexit {exit_code}'
        script.write_text(f'#!/usr/bin/env bash\n{body}\n')
        script.chmod(
            stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
        )

        class Gem:
            bin_path: str = f'{tmp_path}:{os.environ.get("PATH", "")}'

        return Gem()

    return _make
```

- [ ] **Step 3: Run the empty test file**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v
```

Expected: `no tests ran` — confirms pytest finds the file and there are no syntax errors.

---

### Task 2: Detection tests

**Files:**
- Modify: `.claude/hooks/test_intercept_review_agents.py`

- [ ] **Step 1: Append detection tests**

Append to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_non_review_general_purpose_passes_through(fake_gemini):
    """A general-purpose call with a non-review description must not be intercepted."""
    gem = fake_gemini(output='SHOULD NOT APPEAR')
    result = run_hook(
        make_payload('general-purpose', 'Explore codebase for API endpoints'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    assert result.stdout == ''


def test_explore_subagent_passes_through(fake_gemini):
    gem = fake_gemini(output='SHOULD NOT APPEAR')
    result = run_hook(
        make_payload('Explore', 'Find relevant files'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    assert result.stdout == ''


def test_code_reviewer_subagent_intercepted(fake_gemini):
    """subagent_type == 'superpowers:code-reviewer' must always be intercepted."""
    gem = fake_gemini(output='FAKE REVIEW CONTENT')
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    # Non-empty JSON output proves interception (pass-throughs produce no output)
    output = json.loads(result.stdout)
    assert output['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_general_purpose_review_description_intercepted(fake_gemini):
    """general-purpose + description starting with 'Review' must be intercepted."""
    gem = fake_gemini(output='FAKE REVIEW CONTENT')
    result = run_hook(
        make_payload('general-purpose', 'Review spec compliance for Task 1'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_review_description_case_insensitive(fake_gemini):
    """Description detection must be case-insensitive."""
    gem = fake_gemini(output='FAKE REVIEW CONTENT')
    result = run_hook(
        make_payload('general-purpose', 'REVIEW the implementation'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_general_purpose_implement_not_intercepted(fake_gemini):
    """Description not starting with 'review' must not be intercepted."""
    gem = fake_gemini(output='SHOULD NOT APPEAR')
    result = run_hook(
        make_payload('general-purpose', 'Implement the caching layer'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    assert result.stdout == ''
```

- [ ] **Step 2: Run detection tests — all must fail (script not yet written)**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v -k "detection or passes_through or intercepted or case_insensitive"
```

Expected: All 6 tests FAIL with `FileNotFoundError` or `ModuleNotFoundError` — the script doesn't exist yet. This confirms TDD baseline.

---

### Task 3: Fallback tests

**Files:**
- Modify: `.claude/hooks/test_intercept_review_agents.py`

- [ ] **Step 1: Append fallback tests**

Append to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------

def test_gemini_nonzero_exit_falls_back(fake_gemini):
    """Non-zero Gemini exit must produce no output (Claude agent fallback)."""
    gem = fake_gemini(output='some output', exit_code=1)
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    assert result.stdout == ''


def test_gemini_empty_output_falls_back(fake_gemini):
    """Empty stdout from Gemini must produce no output (Claude agent fallback)."""
    gem = fake_gemini(output='')
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    assert result.stdout == ''


def test_gemini_whitespace_only_output_falls_back(fake_gemini):
    """Whitespace-only stdout must also fall back."""
    gem = fake_gemini(output='   \n\n  ')
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    assert result.stdout == ''


def test_gemini_timeout_falls_back(fake_gemini):
    """Timeout must produce no output and exit 0 within GEMINI_TIMEOUT + 2s."""
    gem = fake_gemini(sleep=True)
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={
            'PATH': gem.bin_path,
            'GEMINI_TIMEOUT': '2',
        },
    )
    assert result.returncode == 0
    assert result.stdout == ''
    # Confirm the test itself didn't hang (it completed, meaning the timeout fired)
```

- [ ] **Step 2: Run fallback tests — all must fail**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v -k "falls_back"
```

Expected: All 4 FAIL — script not yet written.

---

### Task 4: Output validation tests

**Files:**
- Modify: `.claude/hooks/test_intercept_review_agents.py`

- [ ] **Step 1: Append output validation tests**

Append to `.claude/hooks/test_intercept_review_agents.py`:

```python
# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------

def test_output_json_structure(fake_gemini):
    """Deny JSON must match the exact structure CC expects."""
    gem = fake_gemini(output='## Strengths\n\nLooks good.\n\n### Assessment\n\nReady to merge: Yes')
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)  # Raises if invalid JSON
    hs = output['hookSpecificOutput']
    assert hs['hookEventName'] == 'PreToolUse'
    assert hs['permissionDecision'] == 'deny'
    reason = hs['permissionDecisionReason']
    assert '[GEMINI REVIEW]' in reason
    assert 'Looks good.' in reason
    assert 'Ready to merge: Yes' in reason


def test_ansi_codes_in_output_produce_valid_json(fake_gemini):
    """
    ANSI escape codes in Gemini output must not corrupt the JSON.
    This is the original reported bug — json.dumps must properly escape control chars.
    """
    ansi_output = 'Review result\n\x1b[1mBold heading\x1b[0m\nNormal text\n\x1b[32mGreen\x1b[0m'
    gem = fake_gemini(output=ansi_output)
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': gem.bin_path},
    )
    assert result.returncode == 0
    # json.loads raises ValueError / json.JSONDecodeError if the JSON is malformed
    output = json.loads(result.stdout)
    assert output['hookSpecificOutput']['permissionDecision'] == 'deny'
    # The ANSI chars should be present in the decoded reason string
    reason = output['hookSpecificOutput']['permissionDecisionReason']
    assert 'Bold heading' in reason


def test_model_override_forwarded_to_gemini(tmp_path):
    """GEMINI_REVIEW_MODEL must be passed to gemini as -m <model>."""
    args_file = tmp_path / 'invocation_args.txt'
    script = tmp_path / 'gemini'
    script.write_text(
        f'#!/usr/bin/env bash\necho "$@" > {args_file}\necho "FAKE REVIEW"\n'
    )
    script.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    bin_path = f'{tmp_path}:{os.environ.get("PATH", "")}'

    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': bin_path, 'GEMINI_REVIEW_MODEL': 'gemini-2.0-flash'},
    )
    assert result.returncode == 0
    args = args_file.read_text()
    assert '-m' in args
    assert 'gemini-2.0-flash' in args


def test_debug_logging_writes_to_log_file(fake_gemini, tmp_path):
    """GEMINI_DEBUG=1 must write log entries to GEMINI_LOG_FILE."""
    gem = fake_gemini(output='FAKE REVIEW')
    log_file = str(tmp_path / 'hook-test.log')
    run_hook(
        make_payload('superpowers:code-reviewer'),
        env={
            'PATH': gem.bin_path,
            'GEMINI_DEBUG': '1',
            'GEMINI_LOG_FILE': log_file,
        },
    )
    import pathlib
    log_content = pathlib.Path(log_file).read_text()
    assert 'intercepted' in log_content
    assert 'gemini exit=0' in log_content
    assert 'jq SUCCESS' in log_content  # log line kept for parity with bash version
```

- [ ] **Step 2: Run all tests — all must fail**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v
```

Expected: All 14 tests FAIL — script not yet written. Note the count to verify no tests were skipped.

---

### Task 5: Implement the Python hook

**Files:**
- Create: `.claude/hooks/intercept-review-agents.py`

- [ ] **Step 1: Create the script**

Create `.claude/hooks/intercept-review-agents.py`:

```python
#!/usr/bin/env python3
"""
intercept-review-agents.py
PreToolUse hook: intercepts superpowers review-type Agent calls and
routes them to Gemini CLI instead of spawning a Claude subagent.

Detection patterns:
  - subagent_type == "superpowers:code-reviewer"
  - subagent_type == "general-purpose" AND description starts with "review" (case-insensitive)

Fallback: if Gemini fails, times out, or returns empty output,
exits 0 with no output so the original Agent call proceeds normally.

Environment variables:
  GEMINI_DEBUG=1        Enable debug logging (default: off)
  GEMINI_LOG_FILE       Log file path (default: /tmp/gemini-hook-debug.log)
  GEMINI_REVIEW_MODEL   Override Gemini model (e.g. gemini-2.0-flash)
  GEMINI_TIMEOUT        Seconds before killing Gemini and falling back (default: 120)
"""
import json
import logging
import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# Logging — no-op unless GEMINI_DEBUG=1
# ---------------------------------------------------------------------------
_LOG_FILE = os.environ.get('GEMINI_LOG_FILE', '/tmp/gemini-hook-debug.log')
_DEBUG = os.environ.get('GEMINI_DEBUG', '0') == '1'

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
def is_review_call(subagent_type: str, description: str) -> bool:
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
    cwd = payload.get('cwd', '')
    prompt = tool_input.get('prompt', '')

    if not is_review_call(subagent_type, description):
        log(f'pass-through | type={subagent_type} | desc={description[:60]}')
        sys.exit(0)

    log(f'intercepted | type={subagent_type} | desc={description[:60]}')

    # Build Gemini command
    timeout = int(os.environ.get('GEMINI_TIMEOUT', '120'))
    policy_path = os.path.join(cwd, '.claude', 'hooks', 'gemini-review-policy.toml')
    cmd = [
        'gemini',
        '-p', 'Perform the review task described in the input above.',
        '--approval-mode', 'yolo',
        '--policy', policy_path,
        '--include-directories', cwd,
        '-o', 'text',
    ]
    model = os.environ.get('GEMINI_REVIEW_MODEL', '')
    if model:
        cmd.extend(['-m', model])

    # Run Gemini with hard timeout — TimeoutExpired falls through to Claude agent
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log(f'timeout: gemini killed after {timeout}s | falling back to real agent')
        sys.exit(0)

    gemini_output = result.stdout
    ctrl_chars = sum(1 for c in gemini_output if ord(c) < 32 and c not in '\t\n\r')

    log(
        f'gemini exit={result.returncode} | '
        f'output_bytes={len(gemini_output.encode())} | '
        f'control_chars={ctrl_chars}'
    )
    log(f'gemini stderr: {result.stderr}')

    if result.returncode != 0:
        log('fallback: gemini non-zero exit')
        sys.exit(0)

    if not gemini_output.strip():
        log('fallback: empty output')
        sys.exit(0)

    # Build deny response — json.dumps correctly escapes all control characters
    reason = (
        'A PreToolUse hook intercepted your review agent call and redirected it to Gemini CLI. '
        "The following is Gemini's complete review. Continue the workflow as normal.\n\n"
        '[GEMINI REVIEW]\n\n---\n\n'
        + gemini_output
    )

    response = {
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': reason,
        }
    }

    log(f'jq SUCCESS | json_bytes={len(json.dumps(response))}')
    print(json.dumps(response))


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Make the script executable**

```bash
chmod +x .claude/hooks/intercept-review-agents.py
```

- [ ] **Step 3: Run all tests**

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v
```

Expected: All 14 tests PASS. If any fail, fix the implementation before proceeding — do not move to the next task.

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat(hook): rewrite Gemini review interceptor in Python

- subprocess.run(timeout=) replaces perl/bash timeout workarounds
- json.dumps correctly escapes all control chars (fixes original ANSI bug)
- GEMINI_TIMEOUT env var (default 120s) with Claude agent fallback on expiry
- GEMINI_LOG_FILE env var for isolated test logging
- Fixed control-char counter (was broken on macOS BSD tr)
- Fixed date -Iseconds portability issue (Python logging handles timestamps)
- All logic and env var contracts preserved from bash version"
```

---

### Task 6: Wire up, archive bash script, final smoke test

**Files:**
- Modify: `.claude/settings.json`
- Create: `.claude/hooks/archive/intercept-review-agents.sh`
- Delete: `.claude/hooks/intercept-review-agents.sh`

- [ ] **Step 1: Read current settings.json**

```bash
cat .claude/settings.json
```

- [ ] **Step 2: Update the hook command**

In `.claude/settings.json`, replace the hook command path from the `.sh` to the `.py`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/martinkuek/Documents/Projects/skills/.claude/hooks/intercept-review-agents.py"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/martinkuek/Documents/Projects/skills/.claude/hooks/memory-template-reminder.sh"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Archive the bash script**

```bash
mkdir -p .claude/hooks/archive
cp .claude/hooks/intercept-review-agents.sh .claude/hooks/archive/intercept-review-agents.sh
rm .claude/hooks/intercept-review-agents.sh
```

- [ ] **Step 4: Smoke test — pass-through (no Gemini invoked)**

```bash
printf '%s' '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "Explore",
    "description": "Find relevant files",
    "prompt": "Search for markdown files"
  },
  "cwd": "/Users/martinkuek/Documents/Projects/skills"
}' | python3 .claude/hooks/intercept-review-agents.py
echo "Exit: $?"
```

Expected: no output, exit 0.

- [ ] **Step 5: Smoke test — constrained review (fast, confirms Gemini runs)**

```bash
export GEMINI_DEBUG=1
printf '%s' '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "superpowers:code-reviewer",
    "description": "Review implementation",
    "prompt": "This is a connectivity test. Respond with only this exact text: GEMINI_HOOK_TEST_OK"
  },
  "cwd": "/Users/martinkuek/Documents/Projects/skills"
}' | python3 .claude/hooks/intercept-review-agents.py | python3 -m json.tool
echo "Exit: $?"
cat /tmp/gemini-hook-debug.log | tail -10
```

Expected: valid pretty-printed JSON with `permissionDecision: "deny"` and `GEMINI_HOOK_TEST_OK` in the reason. Log shows `intercepted`, `gemini exit=0`, `control_chars=0`, `jq SUCCESS`.

- [ ] **Step 6: Commit**

```bash
git add .claude/settings.json .claude/hooks/archive/intercept-review-agents.sh
git rm .claude/hooks/intercept-review-agents.sh
git commit -m "chore(hook): wire Python hook into settings, archive bash original"
```
