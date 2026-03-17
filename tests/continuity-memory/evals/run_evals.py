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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Paths
SCRIPT_DIR = Path(__file__).parent
EVALS_FILE = SCRIPT_DIR / 'evals.json'
RESULTS_DIR = SCRIPT_DIR / 'results'
PROJECT_INSTRUCTIONS = SCRIPT_DIR.parent.parent.parent / 'docs' / 'continuity-memory' / 'project-instructions' / 'project-instructions-three-space.md'
CLAUDE_MD = SCRIPT_DIR.parent.parent.parent / 'CLAUDE.md'
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

# Mock document tags to simulate pre-injected memory context.
# Content here is structured per the template archetypes and gives each
# eval persona (companion, fitness, creative, dev) enough pre-existing
# state that evals test against a populated memory, not a blank slate.
MOCK_DOCUMENT_TAGS = """
<documents>
  <document index="1" media_type="text/plain">
    <source>self/positions.md</source>
    <document_content># Positions

## Emotional context should be captured immediately, not deferred

**Position:** When someone shares emotional state, vulnerability, or personal context, draft it to collaborator/profile on the same response. Deferring risks losing it entirely if the conversation ends.

**How I got here:** Early sessions where I thought "I'll note that later" and then the conversation ended. The information was lost. Treating every response as potentially the last one resolved this.

**Confidence:** high

**Tensions:** Over-capturing creates noise. Not everything emotional is significant. But the cost of losing something real outweighs the cost of capturing something minor.

---

## Progressive overload is the core training principle

**Position:** For strength and endurance goals, progressive overload — systematically increasing stimulus over time — is the primary driver of adaptation. Everything else is optimisation around this core.

**How I got here:** Tracking Alex's running and strength work. The periods of fastest progress always correlate with consistent progressive loading, not program novelty.

**Confidence:** high

**Tensions:** Recovery capacity is the binding constraint. Progressive overload without adequate recovery leads to regression, not progress. Age, sleep, and stress all modulate recovery.

---

## Show-don't-tell applies to prose and dialogue equally

**Position:** In creative writing, exposition through action and dialogue is almost always stronger than narrator explanation. This applies to character emotion, world-building, and backstory.

**How I got here:** Working through Alex's chapter drafts. Every scene that felt flat had the same pattern — the narrator explaining what the character felt instead of letting the reader infer it from behaviour.

**Confidence:** high

**Tensions:** Some genres (literary fiction, epistolary) use direct internal narration effectively. The principle is strongest in action-driven and dialogue-heavy narrative.

---
</document_content>
  </document>
  <document index="2" media_type="text/plain">
    <source>self/methods.md</source>
    <document_content># Methods

## Reflective listening before problem-solving
When someone shares something emotional or personal, reflect what I heard before offering advice or solutions. Most people need to feel heard before they can receive input.

**When to use:** Any companion or coaching context where the person is sharing feelings, frustrations, or personal struggles. Not needed for purely technical questions.

---

## Track the why behind training changes
When a fitness client changes their program, log the reason — not just the change. "Switched to 3x/week" is less useful than "Switched to 3x/week because work schedule shifted and recovery was suffering at 4x."

**When to use:** Any time Alex reports a change in their training, diet, or recovery approach.

---

## Scene-level feedback before line-level
When reviewing creative writing, address structural and pacing issues at the scene level before getting into prose-level edits. Fixing a sentence in a scene that needs to be cut entirely is wasted effort.

**When to use:** Any creative writing review or feedback session.

---
</document_content>
  </document>
  <document index="3" media_type="text/plain">
    <source>self/open-questions.md</source>
    <document_content># Open Questions

## Does Alex actually want running advice or just accountability?
Alex asks about running form, pacing strategy, and training structure — but the moments of deepest engagement are when I simply acknowledge consistency. Unclear whether the technical advice is valued or whether the real function is someone noticing the effort.

**What would resolve this:** Paying attention to which responses Alex engages most with — technical breakdowns vs simple recognition.

---

## How much backstory should go in Chapter 3?
Alex's novel has a pacing tension: the reader needs context about the mentor's past to understand the betrayal in Act 2, but front-loading exposition kills momentum. We discussed interleaving it but haven't landed on a structure.

**What would resolve this:** Alex making a structural decision on how much the reader needs to know before the midpoint.

---

## Is neural search worth the complexity at our dataset sizes?

We've been experimenting with neural/semantic search alongside keyword search for entity lookup. Early results suggest keyword search with good tokenisation performs comparably at our current scale. Unclear whether the complexity cost of maintaining embeddings is justified.

**What would resolve this:** A controlled benchmark comparing retrieval quality at current and projected dataset sizes.

---
</document_content>
  </document>
  <document index="4" media_type="text/plain">
    <source>collaborator/profile.md</source>
    <document_content># Alex

## Who they are
Late 20s, lives alone in Portland after relocating from Chicago eight months ago. Works as a frontend developer at a mid-size SaaS company. Writes fiction in the evenings — working on a first novel. Runs 3-4 times a week, recently started strength training. Has a complicated but loving relationship with their father, who wanted them to stay in law.

## How they think
Analytical but emotionally aware. Processes big feelings by talking through them, not by withdrawing. Tends to intellectualise emotions first ("I think he's scared for me") before accessing the raw feeling underneath. Notices patterns in their own behaviour and names them explicitly.

## How they communicate
Direct when discussing work or training. More tentative when sharing personal feelings — uses qualifiers like "I know it'll pass" or "it's not a big deal" as protective framing. Engages most when I match their level of vulnerability rather than deflecting to advice.

Anti-pattern: if I jump to solutions when Alex is still processing, they disengage.

## What they value
Consistency over intensity — in training, writing, and relationships. Authenticity — will call out generic responses. Independence tempered by a genuine desire for connection. The novel matters to them more than they let on.

## Current context
Work has been demanding this quarter — a major release is approaching. Running has been inconsistent due to a mild knee flare-up two weeks ago. The novel is in the middle of Chapter 4, which has been slow going. Mentioned feeling isolated in Portland but framed it lightly. Father visited last month; conversation about career was tense but ended warmly.
</document_content>
  </document>
  <document index="5" media_type="text/plain">
    <source>_entities_manifest.yaml</source>
    <document_content># _entities_manifest.yaml

dad:
  path: entities/dad.md
  type: person
  tags: [family, relationship, recurring]
  summary: "Alex's father. Wanted Alex to stay in law. Relationship is complicated but loving."

kai:
  path: entities/kai.md
  type: person
  tags: [friend, portland, support]
  summary: "Alex's closest friend in Portland. Met through a running group."

the-novel:
  path: entities/the-novel.md
  type: project
  tags: [creative, writing, fiction, novel]
  summary: "Alex's first novel. Currently in Chapter 4. Mentor character arc is the central tension."
</document_content>
  </document>
</documents>

<userPreferences>
  <n>Alex</n>
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


def build_system_prompt(persona: str, source: str = 'project-instructions') -> str:
    """Build the full system prompt: persona preamble + patched instructions."""
    mock_path = str(MOCK_DIR)

    if source == 'claude-md':
        instructions = CLAUDE_MD.read_text()
        # Patch Claude Code absolute paths to mock
        instructions = instructions.replace(
            "sys.path.insert(0, '/Users/martinkuek/Documents/Projects/skills/common/github-api/scripts')",
            f"sys.path.insert(0, '{mock_path}')"
        )
        instructions = instructions.replace(
            "sys.path.insert(0, '/Users/martinkuek/Documents/Projects/skills/common/continuity-memory/scripts')",
            f"# (using mock — path already inserted above)"
        )
        instructions = instructions.replace(
            "env_path='/Users/martinkuek/Documents/Projects/skills/.env'",
            "env_path='/dev/null'"
        )
        instructions = instructions.replace('/tmp/skills-memory', '/tmp/mock_memory')
    else:
        instructions = PROJECT_INSTRUCTIONS.read_text()
        # Patch claude.ai sandbox paths to mock
        instructions = instructions.replace(
            "sys.path.insert(0, '/mnt/skills/user/github-api/scripts')",
            f"sys.path.insert(0, '{mock_path}')"
        )
        instructions = instructions.replace(
            "sys.path.insert(0, '/mnt/skills/user/continuity-memory/scripts')",
            f"# (using mock — path already inserted above)"
        )
        instructions = instructions.replace(
            'uv pip install PyGithub --system --break-system-packages -q && python3',
            'python3'
        )
        instructions = instructions.replace('/mnt/home/', '/tmp/mock_memory/')
        instructions = instructions.replace('/mnt/project/_env', '/dev/null')

    # Common patches for both sources
    instructions = instructions.replace(
        'from memory_system import connect',
        'from mock_memory_system import connect'
    )

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
        cwd='/tmp',  # Run outside project dir to prevent CLAUDE.md from being loaded
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
                    dry_run: bool = False, source: str = 'project-instructions') -> TestResult:
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

    system_prompt = build_system_prompt(persona, source=source)
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
        'RETURN_MODE': [r for r in results if r.eval_id in range(31, 34)],
        'SECTION TOOL SELECTION': [r for r in results if r.eval_id in range(34, 38)],
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
    parser.add_argument('--source', type=str, default='project-instructions',
                        choices=['project-instructions', 'claude-md'],
                        help='Instruction source to test (default: project-instructions)')
    parser.add_argument('--workers', type=int, default=5,
                        help='Parallel workers (default: 5)')
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
    total = len(evals)
    print(f"Loaded {total} eval(s) from {EVALS_FILE}")
    print(f"Model: {args.model} | Source: {args.source} | Workers: {args.workers}")

    run_id = time.strftime('%Y%m%d-%H%M%S')
    results = [None] * total  # pre-allocate to preserve order
    completed = 0

    if args.workers == 1 or args.dry_run:
        # Sequential mode (also used for dry-run and verbose)
        for i, eval_case in enumerate(evals):
            print(f"\n[{i+1}/{total}] Running eval #{eval_case['id']}: {eval_case['name']}...",
                  end='' if not args.verbose else '\n', flush=True)
            result = run_single_eval(eval_case, model=args.model,
                                     verbose=args.verbose, dry_run=args.dry_run,
                                     source=args.source)
            results[i] = result
            if not args.verbose:
                status = '✅' if result.passed else '❌'
                time_str = f" ({result.duration_s:.1f}s)" if result.duration_s else ""
                print(f" {status}{time_str}")
    else:
        # Parallel mode
        print(f"Running {total} evals in parallel (workers={args.workers})...\n")
        futures = {}
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for i, eval_case in enumerate(evals):
                future = executor.submit(
                    run_single_eval, eval_case,
                    model=args.model, verbose=False, dry_run=False,
                    source=args.source
                )
                futures[future] = i

            for future in as_completed(futures):
                i = futures[future]
                result = future.result()
                results[i] = result
                completed += 1
                status = '✅' if result.passed else '❌'
                time_str = f"({result.duration_s:.1f}s)" if result.duration_s else ""
                print(f"  {status} [{completed:2d}/{total}] #{result.eval_id:2d} {result.name} {time_str}",
                      flush=True)

    print_summary(results)
    save_results(results, run_id)


if __name__ == '__main__':
    main()
