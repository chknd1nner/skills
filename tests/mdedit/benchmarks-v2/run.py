#!/usr/bin/env python3
"""
Benchmark runner for mdedit v2 — measures token efficiency vs baseline.

Auto-discovers scenarios from scenarios/*/scenario.yaml, dispatches
headless claude CLI agents with --bare mode, validates correctness,
and saves structured results.

Usage:
    python3 run.py [--scenarios replace-small,delete-section]
                   [--sizes small,medium,large]
                   [--conditions mdedit,baseline]
                   [--reps 3] [--model haiku]
                   [--workers 15] [--timeout 300] [--dry-run]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from validate import validate_file_diff, validate_report_contains

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
FIXTURES_DIR = SCRIPT_DIR / 'fixtures'
SYSTEM_PROMPTS_DIR = SCRIPT_DIR / 'system-prompts'
SCENARIOS_DIR = SCRIPT_DIR / 'scenarios'
RESULTS_DIR = SCRIPT_DIR / 'results'
# Candidate paths for mdedit binary, checked in order
MDEDIT_CANDIDATES = [
    SCRIPT_DIR.parent.parent.parent / 'claude-code-only' / 'mdedit' / 'target' / 'release' / 'mdedit',
    Path.home() / '.cargo' / 'bin' / 'mdedit',
]

ALL_SIZES = ['small', 'medium', 'large']
ALL_CONDITIONS = ['mdedit', 'baseline']


# ---------------------------------------------------------------------------
# Scenario discovery
# ---------------------------------------------------------------------------

def discover_scenarios(filter_names: list[str] | None = None) -> list[dict]:
    """
    Scan scenarios/*/scenario.yaml and return list of scenario dicts.

    Each dict has: name, description, sizes, validation, showcase, dir.
    """
    scenarios = []
    for yaml_path in sorted(SCENARIOS_DIR.glob('*/scenario.yaml')):
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
        config['dir'] = yaml_path.parent
        scenarios.append(config)

    if filter_names:
        scenarios = [s for s in scenarios if s['name'] in filter_names]

    return scenarios


def load_prompt_frontmatter(prompt_path: Path) -> dict:
    """
    Extract YAML frontmatter from a prompt file.

    Returns empty dict if no frontmatter present.
    """
    text = prompt_path.read_text()
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def load_prompt_body(prompt_path: Path) -> str:
    """
    Read prompt file, stripping YAML frontmatter if present.
    """
    text = prompt_path.read_text()
    match = re.match(r'^---\s*\n.*?\n---\s*\n', text, re.DOTALL)
    if match:
        return text[match.end():]
    return text


# ---------------------------------------------------------------------------
# Binary verification
# ---------------------------------------------------------------------------

def verify_binary() -> Path | None:
    """
    Find mdedit binary. Tries candidate paths, then falls back to
    `which mdedit`. Returns resolved absolute Path or None.
    """
    # Try candidate paths in order
    for candidate in MDEDIT_CANDIDATES:
        if candidate.exists():
            result = subprocess.run(
                [str(candidate), '--help'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                print(f'Found mdedit: {candidate.resolve()}')
                return candidate.resolve()

    # Fallback: check if mdedit is anywhere on PATH
    which = shutil.which('mdedit')
    if which:
        path = Path(which).resolve()
        print(f'Found mdedit on PATH: {path}')
        return path

    print('WARNING: mdedit binary not found')
    print('  Checked:', [str(c) for c in MDEDIT_CANDIDATES])
    print('  Also ran: which mdedit (not found)')
    return None


# ---------------------------------------------------------------------------
# Per-run execution
# ---------------------------------------------------------------------------

def setup_workdir(scenario_name: str, condition: str, size: str, rep: int) -> Path:
    """Create /tmp workdir with a copy of the fixture."""
    ts = int(time.time() * 1000)
    workdir = Path(f'/tmp/mdedit-v2-{scenario_name}-{condition}-{size}-r{rep}-{ts}')
    workdir.mkdir(parents=True, exist_ok=True)
    fixture_src = FIXTURES_DIR / f'{size}.md'
    if fixture_src.exists():
        shutil.copy2(fixture_src, workdir / f'{size}.md')
    return workdir


def substitute_placeholders(
    text: str, binary: Path | None, workdir: Path,
    fixture_name: str, report_path: Path,
) -> str:
    """Replace {{WORKDIR}}, {{FIXTURE}}, {{BINARY}}, {{REPORT_PATH}}."""
    text = text.replace('{{WORKDIR}}', str(workdir))
    text = text.replace('{{FIXTURE}}', fixture_name)
    text = text.replace('{{BINARY}}', str(binary) if binary else '')
    text = text.replace('{{REPORT_PATH}}', str(report_path))
    return text


def parse_token_usage(stdout: str) -> dict:
    """
    Parse token usage from claude CLI JSON output.

    Scans the JSON structure for input_tokens/output_tokens and counts
    tool_use blocks.
    """
    try:
        data = json.loads(stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return {
            'input_tokens': 0, 'output_tokens': 0,
            'total_tokens': 0, 'num_tool_calls': 0,
        }

    input_tokens = 0
    output_tokens = 0
    num_tool_calls = 0

    # Try known locations
    for path in [lambda d: d['result']['usage'], lambda d: d['usage']]:
        try:
            usage = path(data)
            if isinstance(usage, dict):
                input_tokens = usage.get('input_tokens', 0) or 0
                output_tokens = usage.get('output_tokens', 0) or 0
                break
        except (KeyError, TypeError):
            continue

    # Fallback: scan the whole structure
    if input_tokens == 0 and output_tokens == 0:
        def _scan(obj):
            nonlocal input_tokens, output_tokens
            if isinstance(obj, dict):
                if 'input_tokens' in obj and input_tokens == 0:
                    input_tokens = obj['input_tokens'] or 0
                if 'output_tokens' in obj and output_tokens == 0:
                    output_tokens = obj['output_tokens'] or 0
                for v in obj.values():
                    _scan(v)
            elif isinstance(obj, list):
                for item in obj:
                    _scan(item)
        _scan(data)

    # Count tool_use blocks
    try:
        messages = data.get('messages') or []
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get('content') or []
                if isinstance(content, list):
                    num_tool_calls += sum(
                        1 for b in content
                        if isinstance(b, dict) and b.get('type') == 'tool_use'
                    )
    except Exception:
        pass

    return {
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
        'num_tool_calls': num_tool_calls,
    }


def extract_agent_text(stdout: str) -> str:
    """Extract the agent's final text response from JSON output."""
    try:
        data = json.loads(stdout.strip())
        text = (
            data.get('result', '') or
            data.get('text', '') or
            data.get('content', '') or
            ''
        )
        if isinstance(text, list):
            text = ' '.join(
                b.get('text', '') for b in text if isinstance(b, dict)
            )
        return text
    except Exception:
        return stdout


def run_single(
    scenario: dict, condition: str, size: str, rep: int,
    binary: Path | None, model: str, timeout: int,
    run_dir: Path,
) -> dict:
    """Execute one benchmark run and return a structured result dict."""
    name = scenario['name']
    fixture_name = f'{size}.md'
    workdir = setup_workdir(name, condition, size, rep)
    report_path = workdir / f'report-{name}-{condition}.md'

    # Load system prompt
    system_prompt_path = SYSTEM_PROMPTS_DIR / f'{condition}.md'
    system_prompt = substitute_placeholders(
        system_prompt_path.read_text(), binary, workdir, fixture_name, report_path,
    )

    # Load task prompt (body only, no frontmatter)
    prompt_path = scenario['dir'] / 'prompt.md'
    user_prompt = substitute_placeholders(
        load_prompt_body(prompt_path), binary, workdir, fixture_name, report_path,
    )

    # Build command
    cmd = [
        'claude', '-p',
        '--output-format', 'json',
        '--bare',
        '--system-prompt', system_prompt,
        '--model', model,
        '--dangerously-skip-permissions',
    ]

    # Build environment
    env = os.environ.copy()
    if binary:
        binary_dir = str(binary.parent)
        if condition == 'mdedit':
            # Ensure mdedit is on PATH even in restricted terminal environments
            if binary_dir not in env.get('PATH', '').split(':'):
                env['PATH'] = binary_dir + ':' + env.get('PATH', '')
        elif condition == 'baseline':
            # Remove mdedit from PATH so baseline can't accidentally use it
            path_parts = [p for p in env.get('PATH', '').split(':') if p != binary_dir]
            env['PATH'] = ':'.join(path_parts)

    start = time.time()

    try:
        proc = subprocess.run(
            cmd, input=user_prompt,
            capture_output=True, text=True,
            timeout=timeout, env=env, cwd=str(workdir),
        )
        duration = time.time() - start

        if proc.returncode != 0:
            return _error_result(
                name, condition, size, rep, workdir,
                f'claude exited {proc.returncode}: {proc.stderr[:500]}',
                duration,
            )

        stdout = proc.stdout
        tokens = parse_token_usage(stdout)
        agent_text = extract_agent_text(stdout)

        # Save transcript for showcase scenarios
        if scenario.get('showcase'):
            transcripts_dir = run_dir / 'transcripts'
            transcripts_dir.mkdir(parents=True, exist_ok=True)
            transcript_file = transcripts_dir / f'{name}-{condition}-{size}-rep{rep}.json'
            transcript_file.write_text(stdout)

        # Validate
        validation = scenario.get('validation', 'file-diff')
        if validation == 'file-diff':
            result_file = workdir / fixture_name
            expected_file = scenario['dir'] / 'expected' / f'{size}.md'
            val = validate_file_diff(result_file, expected_file)
        elif validation == 'report-contains':
            frontmatter = load_prompt_frontmatter(scenario['dir'] / 'prompt.md')
            expected_strings = frontmatter.get('validation_strings', [])
            val = validate_report_contains(agent_text, report_path, expected_strings)
        else:
            val = {'valid': None, 'reason': f'Unknown validation: {validation}'}

        return {
            'task': name,
            'condition': condition,
            'size': size,
            'rep': rep,
            'success': True,
            'correct': val.get('valid') is True,
            'validation_reason': val.get('reason', ''),
            'error': '',
            'input_tokens': tokens['input_tokens'],
            'output_tokens': tokens['output_tokens'],
            'total_tokens': tokens['total_tokens'],
            'num_tool_calls': tokens['num_tool_calls'],
            'duration_s': duration,
            'workdir': str(workdir),
        }

    except subprocess.TimeoutExpired:
        return _error_result(
            name, condition, size, rep, workdir,
            f'Timeout ({timeout}s)', time.time() - start,
        )
    except Exception as exc:
        return _error_result(
            name, condition, size, rep, workdir,
            str(exc), time.time() - start,
        )


def _error_result(
    task: str, condition: str, size: str, rep: int,
    workdir: Path, error: str, duration: float = 0.0,
) -> dict:
    """Build a failed-run result dict."""
    return {
        'task': task,
        'condition': condition,
        'size': size,
        'rep': rep,
        'success': False,
        'correct': False,
        'validation_reason': '',
        'error': error,
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'num_tool_calls': 0,
        'duration_s': duration,
        'workdir': str(workdir),
    }


# ---------------------------------------------------------------------------
# Matrix + orchestration
# ---------------------------------------------------------------------------

def build_matrix(
    scenarios: list[dict], sizes: list[str],
    conditions: list[str], reps: int,
) -> list[tuple]:
    """Build list of (scenario, size, condition, rep) runs."""
    matrix = []
    for scenario in scenarios:
        for size in sizes:
            if size not in scenario.get('sizes', ALL_SIZES):
                continue
            for condition in conditions:
                for rep in range(1, reps + 1):
                    matrix.append((scenario, size, condition, rep))
    return matrix


def main():
    parser = argparse.ArgumentParser(
        description='Run mdedit v2 benchmarks: mdedit vs baseline token efficiency',
    )
    parser.add_argument('--scenarios', type=str, default=None,
                        help='Comma-separated scenario names (default: all)')
    parser.add_argument('--sizes', type=str, default=None,
                        help='Comma-separated sizes (default: small,medium,large)')
    parser.add_argument('--conditions', type=str, default=None,
                        help='Comma-separated conditions (default: mdedit,baseline)')
    parser.add_argument('--reps', type=int, default=3,
                        help='Repetitions per cell (default: 3)')
    parser.add_argument('--model', type=str, default='haiku',
                        help='Claude model (default: haiku)')
    parser.add_argument('--workers', type=int, default=15,
                        help='Parallel workers (default: 15)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='Timeout per agent in seconds (default: 300)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would run without executing')
    args = parser.parse_args()

    # Discover scenarios
    filter_names = [s.strip() for s in args.scenarios.split(',')] if args.scenarios else None
    scenarios = discover_scenarios(filter_names)
    if not scenarios:
        print('ERROR: No scenarios found')
        sys.exit(1)

    sizes = [s.strip() for s in args.sizes.split(',')] if args.sizes else ALL_SIZES
    conditions = [c.strip() for c in args.conditions.split(',')] if args.conditions else ALL_CONDITIONS

    # Verify binary
    binary = verify_binary()

    # Build matrix
    matrix = build_matrix(scenarios, sizes, conditions, args.reps)
    total = len(matrix)

    print(f'Scenarios: {[s["name"] for s in scenarios]}')
    print(f'Sizes: {sizes} | Conditions: {conditions} | Reps: {args.reps}')
    print(f'Total runs: {total} | Workers: {args.workers} | Model: {args.model}')
    print(f'Binary: {binary or "NOT FOUND"}')

    if args.dry_run:
        print(f'\n[DRY RUN] Would execute {total} runs:\n')
        for i, (scenario, size, condition, rep) in enumerate(matrix, 1):
            sc = '★' if scenario.get('showcase') else ' '
            print(f'  {i:3d}. {scenario["name"]:20s}  {size:8s}  {condition:10s}  rep={rep}  {sc}')
        return

    # Create results directory
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    run_dir = RESULTS_DIR / f'run-{timestamp}'
    run_dir.mkdir(parents=True, exist_ok=True)

    # Execute
    results = [None] * total
    completed = 0

    def _run_one(idx_and_item):
        idx, (scenario, size, condition, rep) = idx_and_item
        return idx, run_single(
            scenario, condition, size, rep,
            binary, args.model, args.timeout, run_dir,
        )

    print(f'\nRunning {total} runs (workers={args.workers})...\n')

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for i, item in enumerate(matrix):
            future = executor.submit(_run_one, (i, item))
            futures[future] = i

        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result
            completed += 1
            status = '+' if result['correct'] else ('!' if result['success'] else 'X')
            print(
                f'  [{status}] [{completed:3d}/{total}] '
                f'{result["task"]:20s}  {result["size"]:8s}  {result["condition"]:10s}  '
                f'rep={result["rep"]}  tokens={result["total_tokens"]}  '
                f'({result["duration_s"]:.0f}s)',
                flush=True,
            )

    # Save results
    results_path = run_dir / 'results.json'
    results_path.write_text(json.dumps(results, indent=2))
    print(f'\nResults saved to: {results_path}')

    # Run analyzer
    try:
        from analyze import generate_summary, generate_narrative
        summary_path = run_dir / 'summary.md'
        summary_path.write_text(generate_summary(results))
        print(f'Summary:   {summary_path}')

        narrative_path = run_dir / 'narrative.md'
        transcripts_dir = run_dir / 'transcripts'
        if transcripts_dir.exists():
            narrative_path.write_text(generate_narrative(results, transcripts_dir))
            print(f'Narrative: {narrative_path}')
    except ImportError:
        print('WARNING: analyze.py not found, skipping summary generation')


if __name__ == '__main__':
    main()
