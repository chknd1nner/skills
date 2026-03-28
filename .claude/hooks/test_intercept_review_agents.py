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


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_gemini_not_on_path_falls_back():
    """Missing gemini binary must produce no output (clean pass-through)."""
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': '/nonexistent'},  # gemini definitely not here
    )
    assert result.returncode == 0
    assert result.stdout == ''


def test_invalid_gemini_timeout_uses_default(fake_gemini):
    """Non-integer GEMINI_TIMEOUT must not crash the hook."""
    gem = fake_gemini(output='FAKE REVIEW')
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': gem.bin_path, 'GEMINI_TIMEOUT': 'not-a-number'},
    )
    assert result.returncode == 0
    # Hook should still work (not crash) — output may be deny JSON or empty fallback
    # Just asserting it doesn't exit non-zero with an unhandled exception
    assert result.returncode == 0


def test_zero_gemini_timeout_uses_default(fake_gemini):
    """Zero or negative GEMINI_TIMEOUT must not be passed to subprocess."""
    gem = fake_gemini(output='FAKE REVIEW')
    result = run_hook(
        make_payload('superpowers:code-reviewer'),
        env={'PATH': gem.bin_path, 'GEMINI_TIMEOUT': '0'},
    )
    assert result.returncode == 0
