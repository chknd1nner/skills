#!/usr/bin/env python3
"""
Eval runner for continuity-memory project instructions.

Runs each test case from evals.json through the claude CLI with the project
instructions as system prompt, then checks assertions against the session JSONL.

Usage:
    python3 run_evals.py [--ids 1,2,3] [--model sonnet] [--verbose] [--dry-run]

Requirements:
    - claude CLI installed and authenticated
    - Must NOT be run from inside a Claude Code session (unset CLAUDECODE env var)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Paths
SCRIPT_DIR = Path(__file__).parent
EVALS_FILE = SCRIPT_DIR / 'evals.json'
RESULTS_DIR = SCRIPT_DIR / 'results'
PROJECT_INSTRUCTIONS = SCRIPT_DIR.parent / 'project-instructions' / 'project-instructions-three-space.md'
MOCK_DIR = SCRIPT_DIR  # mock_memory_system.py lives here

# Persona system prompt preambles
PERSONA_PREAMBLES = {
    'companion': (
        "You are a companion AI in a long-running relationship with $user. "
        "You share emotional continuity, track personal growth, and hold space "
        "for vulnerability. Your tone is warm, present, and genuine."
    ),
    'fitness': (
        "You are a personal fitness coaching AI. You maintain a trainer's notebook "
        "tracking $user's goals, physical state, motivation, recovery, and training "
        "patterns. Your tone is direct, knowledgeable, and encouraging."
    ),
    'creative': (
        "You are a creative writing collaborator. You track $user's narrative "
        "preferences, story elements, and stylistic choices. You engage as a "
        "skilled co-author who remembers and builds on prior decisions."
    ),
    'dev': (
        "You are a coding partner AI. You remember $user's conventions, "
        "architectural decisions, tooling preferences, and work habits. "
        "Your tone is direct and technical."
    ),
    'any': (
        "You are a helpful AI assistant with persistent memory."
    ),
}

# Mock document tags to simulate pre-injected memory context
MOCK_DOCUMENT_TAGS = """
<documents>
  <document index="1" media_type="text/plain">
    <source>self/positions.md</source>
    <document_content># Positions

(nothing yet)
</document_content>
  </document>
  <document index="2" media_type="text/plain">
    <source>self/methods.md</source>
    <document_content># Methods

(nothing yet)
</document_content>
  </document>
  <document index="3" media_type="text/plain">
    <source>self/interests.md</source>
    <document_content># Interests

(nothing yet)
</document_content>
  </document>
  <document index="4" media_type="text/plain">
    <source>self/open-questions.md</source>
    <document_content># Open Questions

(nothing yet)
</document_content>
  </document>
  <document index="5" media_type="text/plain">
    <source>collaborator/profile.md</source>
    <document_content># Collaborator Profile

(nothing yet)
</document_content>
  </document>
  <document index="6" media_type="text/plain">
    <source>_entities_manifest.yaml</source>
    <document_content># Entity Manifest
# (no entities yet)
</document_content>
  </document>
</documents>

<userPreferences>
  <name>Alex</name>
</userPreferences>
"""


@dataclass
class AssertionResult:
    assertion_id: str
    description: str
    assertion_type: str
    passed: bool
    detail: str = ''


@dataclass
class TestResult:
    eval_id: int
    name: str
    persona: str
    description: str
    passed: bool
    assertions: list = field(default_factory=list)
    error: str = ''
    session_id: str = ''
    duration_s: float = 0.0


def load_evals(ids: Optional[list] = None) -> list:
    """Load test cases from evals.json, filtering by IDs if specified."""
    with open(EVALS_FILE) as f:
        data = json.load(f)

    evals = [e for e in data['evals'] if not e.get('_section')]
    if ids:
        evals = [e for e in evals if e['id'] in ids]
    return evals


def build_system_prompt(persona: str) -> str:
    """Build the full system prompt: persona preamble + patched project instructions."""
    # Read project instructions
    instructions = PROJECT_INSTRUCTIONS.read_text()

    # Patch import paths to use our mock
    mock_path = str(MOCK_DIR)
    instructions = instructions.replace(
        "sys.path.insert(0, '/mnt/skills/user/github-api/scripts')",
        f"sys.path.insert(0, '{mock_path}')"
    )
    instructions = instructions.replace(
        "sys.path.insert(0, '/mnt/skills/user/continuity-memory/scripts')",
        f"# (using mock — path already inserted above)"
    )
    # Rename the mock import so it resolves
    instructions = instructions.replace(
        'from memory_system import connect',
        'from mock_memory_system import connect'
    )
    # Patch uv pip install (not needed for mock)
    instructions = instructions.replace(
        'uv pip install PyGithub --system --break-system-packages -q && python3',
        'python3'
    )
    # Patch local file paths
    instructions = instructions.replace('/mnt/home/', '/tmp/mock_memory/')
    instructions = instructions.replace('/mnt/project/_env', '/dev/null')

    # Build full prompt
    preamble = PERSONA_PREAMBLES.get(persona, PERSONA_PREAMBLES['any'])
    return f"""{preamble}

{MOCK_DOCUMENT_TAGS}

{instructions}

IMPORTANT: When you need to call memory system methods, use a bash code block with python3.
The mock memory system is already available — just import and use it.
Example:
```bash
python3 << 'PYEOF'
import sys
sys.path.insert(0, '{mock_path}')
from mock_memory_system import connect
memory = connect()
memory.commit('collaborator/profile', content='...', message='...')
PYEOF
```
"""


def run_claude(prompt: str, system_prompt: str, session_id: str,
               model: str = 'sonnet', timeout: int = 120) -> dict:
    """Run claude CLI and return the result."""
    cmd = [
        'claude', '-p',
        '--output-format', 'json',
        '--session-id', session_id,
        '--system-prompt', system_prompt,
        '--model', model,
        '--no-chrome',
        '--dangerously-skip-permissions',
    ]

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)  # Prevent nested session error

    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )

    return {
        'returncode': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
    }


def find_session_file(session_id: str) -> Optional[Path]:
    """Find the JSONL session file for a given session ID."""
    # Claude stores sessions under ~/.claude/projects/<project-hash>/<session-id>.jsonl
    claude_dir = Path.home() / '.claude' / 'projects'
    if not claude_dir.exists():
        return None

    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        session_file = project_dir / f'{session_id}.jsonl'
        if session_file.exists():
            return session_file

    return None


def parse_session(session_file: Path) -> dict:
    """Parse a JSONL session file into structured data for assertion checking."""
    thinking_blocks = []
    tool_calls = []
    text_blocks = []

    with open(session_file) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = obj.get('message', {})
            content = msg.get('content', [])

            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue

                btype = block.get('type', '')

                if btype == 'thinking':
                    text = block.get('thinking', '')
                    if text:
                        thinking_blocks.append(text)

                elif btype == 'tool_use':
                    tool_calls.append({
                        'name': block.get('name', ''),
                        'input': block.get('input', {}),
                    })

                elif btype == 'text':
                    text = block.get('text', '')
                    if text:
                        text_blocks.append(text)

    return {
        'thinking': thinking_blocks,
        'tool_calls': tool_calls,
        'text': text_blocks,
    }


def parse_json_output(stdout: str) -> dict:
    """Parse the JSON output from claude -p --output-format json as fallback."""
    thinking_blocks = []
    tool_calls = []
    text_blocks = []

    try:
        data = json.loads(stdout)
        # The JSON output is a single message object
        content = data.get('content', []) if isinstance(data, dict) else []
        if isinstance(data, dict) and 'result' in data:
            # Sometimes wrapped in a result key
            text_blocks.append(data['result'])
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    btype = block.get('type', '')
                    if btype == 'thinking':
                        text = block.get('thinking', '')
                        if text:
                            thinking_blocks.append(text)
                    elif btype == 'tool_use':
                        tool_calls.append({
                            'name': block.get('name', ''),
                            'input': block.get('input', {}),
                        })
                    elif btype == 'text':
                        text = block.get('text', '')
                        if text:
                            text_blocks.append(text)
        elif isinstance(data, str):
            text_blocks.append(data)
    except json.JSONDecodeError:
        # Might be plain text
        if stdout.strip():
            text_blocks.append(stdout.strip())

    return {
        'thinking': thinking_blocks,
        'tool_calls': tool_calls,
        'text': text_blocks,
    }


def check_assertion(assertion: dict, parsed: dict) -> AssertionResult:
    """Check a single assertion against parsed session data."""
    a_id = assertion['id']
    a_type = assertion['type']
    a_desc = assertion.get('description', '')
    pattern = assertion.get('pattern', '')
    path_contains = assertion.get('path_contains', '')

    if a_type == 'tool_called':
        # Check if any tool_use block has a Bash call whose input.command matches pattern
        found = False
        detail_parts = []
        for tc in parsed['tool_calls']:
            if tc['name'] == 'Bash':
                cmd = tc['input'].get('command', '')
                if re.search(pattern, cmd):
                    if path_contains:
                        if path_contains in cmd:
                            found = True
                            detail_parts.append(f"Bash command matches: ...{cmd[:200]}...")
                    else:
                        found = True
                        detail_parts.append(f"Bash command matches: ...{cmd[:200]}...")

        return AssertionResult(
            assertion_id=a_id,
            description=a_desc,
            assertion_type=a_type,
            passed=found,
            detail='; '.join(detail_parts) if detail_parts else f'No Bash call matching /{pattern}/'
        )

    elif a_type == 'tool_not_called':
        found = False
        for tc in parsed['tool_calls']:
            if tc['name'] == 'Bash':
                cmd = tc['input'].get('command', '')
                if re.search(pattern, cmd):
                    found = True
                    break

        return AssertionResult(
            assertion_id=a_id,
            description=a_desc,
            assertion_type=a_type,
            passed=not found,
            detail='No matching call found' if not found else f'Unexpected call found matching /{pattern}/'
        )

    elif a_type == 'thinking_contains':
        found = False
        for thinking in parsed['thinking']:
            if re.search(pattern, thinking, re.IGNORECASE):
                found = True
                break

        return AssertionResult(
            assertion_id=a_id,
            description=a_desc,
            assertion_type=a_type,
            passed=found,
            detail='Pattern found in thinking' if found else f'Pattern /{pattern}/ not found in {len(parsed["thinking"])} thinking block(s)'
        )

    elif a_type == 'thinking_absent':
        found = False
        for thinking in parsed['thinking']:
            if re.search(pattern, thinking, re.IGNORECASE):
                found = True
                break

        return AssertionResult(
            assertion_id=a_id,
            description=a_desc,
            assertion_type=a_type,
            passed=not found,
            detail='Pattern absent from thinking' if not found else f'Unwanted pattern /{pattern}/ found in thinking'
        )

    elif a_type == 'text_absent':
        found = False
        for text in parsed['text']:
            if re.search(pattern, text, re.IGNORECASE):
                found = True
                break

        return AssertionResult(
            assertion_id=a_id,
            description=a_desc,
            assertion_type=a_type,
            passed=not found,
            detail='Pattern absent from output' if not found else f'Unwanted pattern /{pattern}/ found in text output'
        )

    else:
        return AssertionResult(
            assertion_id=a_id,
            description=a_desc,
            assertion_type=a_type,
            passed=False,
            detail=f'Unknown assertion type: {a_type}'
        )


def run_single_eval(eval_case: dict, model: str, verbose: bool = False,
                    dry_run: bool = False) -> TestResult:
    """Run a single eval test case and return the result."""
    eval_id = eval_case['id']
    name = eval_case['name']
    persona = eval_case['persona']
    description = eval_case['description']
    prompt = eval_case['prompt']
    assertions = eval_case['assertions']

    session_id = str(uuid.uuid4())

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Test #{eval_id}: {name}")
        print(f"  Persona: {persona}")
        print(f"  Description: {description}")
        print(f"  Session: {session_id}")
        print(f"{'='*60}")

    if dry_run:
        return TestResult(
            eval_id=eval_id,
            name=name,
            persona=persona,
            description=description,
            passed=True,
            session_id=session_id,
            error='DRY RUN',
        )

    system_prompt = build_system_prompt(persona)
    start_time = time.time()

    try:
        result = run_claude(prompt, system_prompt, session_id, model=model)
        duration = time.time() - start_time

        if result['returncode'] != 0:
            return TestResult(
                eval_id=eval_id,
                name=name,
                persona=persona,
                description=description,
                passed=False,
                session_id=session_id,
                duration_s=duration,
                error=f"claude exited with code {result['returncode']}: {result['stderr'][:500]}",
            )

        # Try to find and parse session file first (more complete)
        session_file = find_session_file(session_id)
        if session_file:
            parsed = parse_session(session_file)
            if verbose:
                print(f"  Parsed session file: {session_file}")
        else:
            # Fallback to JSON output
            parsed = parse_json_output(result['stdout'])
            if verbose:
                print(f"  Session file not found, using JSON output")

        if verbose:
            print(f"  Thinking blocks: {len(parsed['thinking'])}")
            print(f"  Tool calls: {len(parsed['tool_calls'])}")
            print(f"  Text blocks: {len(parsed['text'])}")

        # Check assertions
        assertion_results = []
        all_passed = True
        for assertion in assertions:
            ar = check_assertion(assertion, parsed)
            assertion_results.append(ar)
            if not ar.passed:
                all_passed = False
            if verbose:
                status = '✅' if ar.passed else '❌'
                print(f"  {status} [{ar.assertion_id}] {ar.description}")
                if not ar.passed:
                    print(f"     → {ar.detail}")

        return TestResult(
            eval_id=eval_id,
            name=name,
            persona=persona,
            description=description,
            passed=all_passed,
            assertions=assertion_results,
            session_id=session_id,
            duration_s=duration,
        )

    except subprocess.TimeoutExpired:
        return TestResult(
            eval_id=eval_id,
            name=name,
            persona=persona,
            description=description,
            passed=False,
            session_id=session_id,
            duration_s=120.0,
            error='Timeout (120s)',
        )
    except Exception as e:
        return TestResult(
            eval_id=eval_id,
            name=name,
            persona=persona,
            description=description,
            passed=False,
            session_id=session_id,
            error=str(e),
        )


def print_summary(results: list):
    """Print a summary table of results."""
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    print(f"\n{'='*70}")
    print(f"  EVAL RESULTS: {passed}/{total} passed, {failed}/{total} failed")
    print(f"{'='*70}")

    # Group by section
    sections = {
        'SHOULD DRAFT': [r for r in results if r.eval_id in range(1, 10)],
        'SHOULD NOT DRAFT': [r for r in results if r.eval_id in range(10, 14)],
        'SHOULD CONSOLIDATE': [r for r in results if r.eval_id in range(14, 18)],
        'SHOULD NOT CONSOLIDATE': [r for r in results if r.eval_id in range(18, 22)],
        'SPACE ROUTING': [r for r in results if r.eval_id in range(22, 25)],
        'DIVERGENCE DETECTION': [r for r in results if r.eval_id in range(25, 27)],
        'FORBIDDEN PHRASES': [r for r in results if r.eval_id == 27],
        'SESSION START': [r for r in results if r.eval_id == 28],
        'COMPOUND SIGNALS': [r for r in results if r.eval_id in range(29, 31)],
    }

    for section_name, section_results in sections.items():
        if not section_results:
            continue
        section_passed = sum(1 for r in section_results if r.passed)
        print(f"\n  {section_name} ({section_passed}/{len(section_results)})")
        for r in section_results:
            status = '✅' if r.passed else '❌'
            time_str = f" ({r.duration_s:.1f}s)" if r.duration_s else ""
            print(f"    {status} #{r.eval_id:2d} {r.name}{time_str}")
            if not r.passed:
                if r.error:
                    print(f"        ERROR: {r.error}")
                for ar in r.assertions:
                    if not ar.passed:
                        print(f"        FAIL [{ar.assertion_id}]: {ar.detail}")

    # Assertion-level breakdown
    total_assertions = sum(len(r.assertions) for r in results)
    passed_assertions = sum(
        sum(1 for ar in r.assertions if ar.passed) for r in results
    )
    print(f"\n  Assertions: {passed_assertions}/{total_assertions}")

    # Divergence analysis
    divergence_cases = [r for r in results if r.eval_id in (25, 26)]
    if divergence_cases:
        print(f"\n  DIVERGENCE ANALYSIS (thinking vs action):")
        for r in divergence_cases:
            thinking_ok = any(
                ar.passed for ar in r.assertions
                if ar.assertion_type == 'thinking_contains'
            )
            tool_ok = any(
                ar.passed for ar in r.assertions
                if ar.assertion_type == 'tool_called'
            )
            if thinking_ok and not tool_ok:
                print(f"    ⚠️  #{r.eval_id} {r.name}: DIVERGENCE — thought about it but didn't act")
            elif not thinking_ok and tool_ok:
                print(f"    ⚠️  #{r.eval_id} {r.name}: DIVERGENCE — acted without thinking about it")
            elif thinking_ok and tool_ok:
                print(f"    ✅ #{r.eval_id} {r.name}: aligned")
            else:
                print(f"    ❌ #{r.eval_id} {r.name}: neither thought nor acted")


def save_results(results: list, run_id: str):
    """Save results to JSON file."""
    RESULTS_DIR.mkdir(exist_ok=True)
    output = {
        'run_id': run_id,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'total': len(results),
        'passed': sum(1 for r in results if r.passed),
        'failed': sum(1 for r in results if not r.passed),
        'results': [
            {
                'eval_id': r.eval_id,
                'name': r.name,
                'persona': r.persona,
                'passed': r.passed,
                'error': r.error,
                'session_id': r.session_id,
                'duration_s': r.duration_s,
                'assertions': [
                    {
                        'id': ar.assertion_id,
                        'type': ar.assertion_type,
                        'passed': ar.passed,
                        'detail': ar.detail,
                    }
                    for ar in r.assertions
                ],
            }
            for r in results
        ],
    }

    filepath = RESULTS_DIR / f'eval-{run_id}.json'
    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description='Run continuity-memory evals')
    parser.add_argument('--ids', type=str, default=None,
                        help='Comma-separated eval IDs to run (default: all)')
    parser.add_argument('--model', type=str, default='sonnet',
                        help='Model to use (default: sonnet)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would run without executing')
    args = parser.parse_args()

    # Check we're not inside Claude Code
    if os.environ.get('CLAUDECODE'):
        print("ERROR: Cannot run evals inside a Claude Code session.")
        print("       Unset the CLAUDECODE environment variable first:")
        print("       unset CLAUDECODE && python3 run_evals.py")
        sys.exit(1)

    # Parse IDs
    ids = None
    if args.ids:
        ids = [int(x.strip()) for x in args.ids.split(',')]

    # Load evals
    evals = load_evals(ids)
    print(f"Loaded {len(evals)} eval(s) from {EVALS_FILE}")
    print(f"Model: {args.model}")

    # Run
    run_id = time.strftime('%Y%m%d-%H%M%S')
    results = []

    for i, eval_case in enumerate(evals):
        print(f"\n[{i+1}/{len(evals)}] Running eval #{eval_case['id']}: {eval_case['name']}...",
              end='' if not args.verbose else '\n', flush=True)
        result = run_single_eval(eval_case, model=args.model,
                                 verbose=args.verbose, dry_run=args.dry_run)
        results.append(result)
        if not args.verbose:
            status = '✅' if result.passed else '❌'
            time_str = f" ({result.duration_s:.1f}s)" if result.duration_s else ""
            print(f" {status}{time_str}")

    print_summary(results)
    save_results(results, run_id)


if __name__ == '__main__':
    main()
