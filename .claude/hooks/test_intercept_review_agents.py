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
