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
