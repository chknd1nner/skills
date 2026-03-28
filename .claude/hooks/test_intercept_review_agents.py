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
