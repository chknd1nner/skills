#!/usr/bin/env python3
"""
Benchmark runner for mdedit — measures token efficiency vs baseline.

Dispatches Claude CLI agents for two conditions (mdedit vs baseline),
captures token usage, validates correctness, and saves structured results.

Usage:
    python3 run_benchmarks.py [--tasks replace-small,insert-section] \\
                               [--sizes small,medium,large] \\
                               [--conditions mdedit,baseline] \\
                               [--reps 5] [--model haiku] \\
                               [--workers 5] [--timeout 300] [--dry-run]

Requirements:
    - claude CLI installed and authenticated
    - mdedit release binary built (cargo build --release)
    - Must NOT be run from inside a Claude Code session (unset CLAUDECODE first)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
FIXTURES_DIR = SCRIPT_DIR / 'fixtures'
PROMPTS_DIR = SCRIPT_DIR / 'prompts'
EXPECTED_DIR = SCRIPT_DIR / 'expected'
RESULTS_DIR = SCRIPT_DIR / 'results'
MDEDIT_BINARY = (
    SCRIPT_DIR.parent.parent.parent
    / 'claude-code-only' / 'mdedit' / 'target' / 'release' / 'mdedit'
)

# ---------------------------------------------------------------------------
# Task definitions
# (slug, description, is_workflow, excluded_sizes)
# ---------------------------------------------------------------------------

TASKS = [
    ('replace-small',        'Replace small section (~5 lines)',    False, []),
    ('replace-large',        'Replace large section (40+ lines)',   False, ['small']),
    ('insert-section',       'Insert new section',                  False, []),
    ('delete-section',       'Delete a section',                    False, []),
    ('rename-heading',       'Rename a heading',                    False, []),
    ('multi-section-update', 'Multi-section update (3 edits)',      False, []),
    ('targeted-read',        'Targeted read (single section)',      False, []),
    ('build-toc',            'Build + prepend table of contents',   True,  []),
    ('edit-and-verify',      'Edit and verify (self-confirming)',   True,  []),
]

ALL_SIZES = ['small', 'medium', 'large']
ALL_CONDITIONS = ['mdedit', 'baseline']


# ---------------------------------------------------------------------------
# Validation import
# ---------------------------------------------------------------------------

try:
    from validate import (
        validate_isolated,
        validate_targeted_read,
        validate_build_toc,
        validate_edit_and_verify,
    )
    _VALIDATE_AVAILABLE = True
except ImportError:
    _VALIDATE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def verify_binary() -> Path | None:
    """Check mdedit exists and is executable. Returns resolved Path or None."""
    if not MDEDIT_BINARY.exists():
        print(f"WARNING: mdedit binary not found at {MDEDIT_BINARY}")
        print(f"         Build it: cd claude-code-only/mdedit && cargo build --release")
        return None

    result = subprocess.run(
        [str(MDEDIT_BINARY), '--help'],
        capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        print(f"WARNING: mdedit binary failed smoke test (--help returned {result.returncode})")
        return None

    return MDEDIT_BINARY.resolve()


def setup_workdir(task: str, condition: str, size: str, rep: int) -> Path:
    """Create a /tmp working directory with a copy of the fixture."""
    timestamp = int(time.time() * 1000)
    workdir = Path(f'/tmp/mdedit-bench-{task}-{condition}-{size}-rep{rep}-{timestamp}')
    workdir.mkdir(parents=True, exist_ok=True)

    fixture_src = FIXTURES_DIR / f'{size}.md'
    if fixture_src.exists():
        shutil.copy2(fixture_src, workdir / f'{size}.md')

    return workdir


def load_prompt(path: Path, binary: Path | None, workdir: Path,
                fixture_name: str, report_path: Path) -> str:
    """Read a prompt file and substitute placeholders."""
    content = path.read_text()
    content = content.replace('{{WORKDIR}}', str(workdir))
    content = content.replace('{{FIXTURE}}', fixture_name)
    content = content.replace('{{BINARY}}', str(binary) if binary else '')
    content = content.replace('{{REPORT_PATH}}', str(report_path))
    return content


def _parse_token_usage(stdout: str) -> dict:
    """
    Parse token usage from claude CLI JSON output.

    Tries multiple locations in the JSON structure to find usage data,
    falling back gracefully when fields are absent.
    """
    try:
        data = json.loads(stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'num_tool_calls': 0}

    input_tokens = 0
    output_tokens = 0
    num_tool_calls = 0

    # Try known locations first
    usage = None
    try:
        usage = data['result']['usage']
    except (KeyError, TypeError):
        pass

    if usage is None:
        try:
            usage = data['usage']
        except (KeyError, TypeError):
            pass

    if usage and isinstance(usage, dict):
        input_tokens = usage.get('input_tokens', 0) or 0
        output_tokens = usage.get('output_tokens', 0) or 0
    else:
        # Scan the whole structure for input_tokens / output_tokens
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

    # Tool call count: look for a tools array or tool_use items
    try:
        messages = data.get('messages') or []
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get('content') or []
                if isinstance(content, list):
                    num_tool_calls += sum(
                        1 for block in content
                        if isinstance(block, dict) and block.get('type') == 'tool_use'
                    )
    except Exception:
        pass

    total_tokens = input_tokens + output_tokens
    return {
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': total_tokens,
        'num_tool_calls': num_tool_calls,
    }


def _validate_run(task_slug: str, is_workflow: bool, size: str,
                  workdir: Path, fixture_name: str,
                  report_path: Path, claude_output_text: str) -> dict:
    """
    Dispatch to appropriate validate.py function based on task type.

    Returns dict with 'valid', 'reason', 'diff'.
    """
    if not _VALIDATE_AVAILABLE:
        return {'valid': None, 'reason': 'validate.py not importable', 'diff': ''}

    result_file = workdir / fixture_name

    if task_slug == 'targeted-read':
        # Agent writes extracted section to output.md; compare against pre-generated expected
        result_file = workdir / 'output.md'
        expected_file = EXPECTED_DIR / size / 'targeted-read.md'
        return validate_isolated(result_file, expected_file)

    elif task_slug == 'build-toc':
        return validate_build_toc(result_file)

    elif task_slug == 'edit-and-verify':
        if report_path.exists():
            report_text = report_path.read_text()
        else:
            report_text = claude_output_text
        # Expected content: hardcoded from the edit-and-verify prompt
        expected_content = (
            "This project addresses the growing need for efficient document processing\n"
            "in large-scale systems. Previous approaches relied on batch processing,\n"
            "which introduced unacceptable latency for real-time applications."
        )
        return validate_edit_and_verify(report_text, expected_content)

    else:
        # Isolated op — compare result file against expected
        expected_file = EXPECTED_DIR / size / f'{task_slug}.md'
        return validate_isolated(result_file, expected_file)


def run_single(task_slug: str, task_desc: str, is_workflow: bool,
               condition: str, size: str, rep: int,
               binary: Path | None, model: str, timeout: int) -> dict:
    """Execute one benchmark run and return a structured result dict."""
    fixture_name = f'{size}.md'
    workdir = setup_workdir(task_slug, condition, size, rep)
    report_path = workdir / f'report-{task_slug}-{condition}.md'

    # Select system prompt based on condition
    system_prompt_file = PROMPTS_DIR / f'system-{condition}.md'

    # Select task prompt based on whether it's a workflow
    task_subdir = 'workflows' if is_workflow else 'isolated'
    task_prompt_file = PROMPTS_DIR / task_subdir / f'{task_slug}.md'

    # Check prompt files exist
    if not system_prompt_file.exists():
        return _error_result(task_slug, task_desc, is_workflow, condition, size, rep, workdir,
                             f'System prompt not found: {system_prompt_file}')

    if not task_prompt_file.exists():
        return _error_result(task_slug, task_desc, is_workflow, condition, size, rep, workdir,
                             f'Task prompt not found: {task_prompt_file}')

    # Load and substitute prompts
    system_prompt = load_prompt(system_prompt_file, binary, workdir, fixture_name, report_path)
    user_prompt = load_prompt(task_prompt_file, binary, workdir, fixture_name, report_path)

    # Build claude CLI command
    cmd = [
        'claude', '-p',
        '--output-format', 'json',
        '--system-prompt', system_prompt,
        '--model', model,
        '--no-chrome',
        '--dangerously-skip-permissions',
    ]

    # Build environment: unset CLAUDECODE always
    env = os.environ.copy()
    env.pop('CLAUDECODE', None)

    # For baseline condition: remove mdedit binary directory from PATH
    if condition == 'baseline' and binary:
        binary_dir = str(binary.parent)
        path_parts = env.get('PATH', '').split(':')
        path_parts = [p for p in path_parts if p != binary_dir]
        env['PATH'] = ':'.join(path_parts)

    start_time = time.time()

    try:
        proc = subprocess.run(
            cmd,
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(workdir),
        )
        duration = time.time() - start_time

        if proc.returncode != 0:
            return _error_result(
                task_slug, task_desc, is_workflow, condition, size, rep, workdir,
                f'claude exited {proc.returncode}: {proc.stderr[:500]}',
                duration_s=duration,
            )

        stdout = proc.stdout

        # Parse token usage
        token_data = _parse_token_usage(stdout)

        # Extract text output for workflow validation fallback
        claude_output_text = ''
        try:
            parsed = json.loads(stdout.strip())
            claude_output_text = (
                parsed.get('result', '') or
                parsed.get('text', '') or
                parsed.get('content', '') or
                ''
            )
            if isinstance(claude_output_text, list):
                claude_output_text = ' '.join(
                    b.get('text', '') for b in claude_output_text
                    if isinstance(b, dict)
                )
        except Exception:
            claude_output_text = stdout

        # Validate correctness
        val = _validate_run(
            task_slug, is_workflow, size, workdir, fixture_name,
            report_path, claude_output_text
        )
        correct = val.get('valid') is True
        validation_reason = val.get('reason', '')

        return {
            'task': task_slug,
            'task_desc': task_desc,
            'is_workflow': is_workflow,
            'condition': condition,
            'size': size,
            'rep': rep,
            'success': True,
            'correct': correct,
            'validation_reason': validation_reason,
            'error': '',
            'input_tokens': token_data['input_tokens'],
            'output_tokens': token_data['output_tokens'],
            'total_tokens': token_data['total_tokens'],
            'duration_s': duration,
            'num_tool_calls': token_data['num_tool_calls'],
            'workdir': str(workdir),
        }

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return _error_result(
            task_slug, task_desc, is_workflow, condition, size, rep, workdir,
            f'Timeout ({timeout}s)', duration_s=duration,
        )
    except Exception as exc:
        duration = time.time() - start_time
        return _error_result(
            task_slug, task_desc, is_workflow, condition, size, rep, workdir,
            str(exc), duration_s=duration,
        )


def _error_result(task_slug: str, task_desc: str, is_workflow: bool,
                  condition: str, size: str, rep: int,
                  workdir: Path, error: str,
                  duration_s: float = 0.0) -> dict:
    """Build a failed-run result dict."""
    return {
        'task': task_slug,
        'task_desc': task_desc,
        'is_workflow': is_workflow,
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
        'duration_s': duration_s,
        'num_tool_calls': 0,
        'workdir': str(workdir),
    }


# ---------------------------------------------------------------------------
# Matrix + orchestration
# ---------------------------------------------------------------------------

def build_run_matrix(tasks: list, sizes: list, conditions: list, reps: int) -> list:
    """
    Build list of (task_tuple, size, condition, rep) runs.
    Excludes per-task excluded_sizes.
    """
    matrix = []
    for task_tuple in tasks:
        task_slug, task_desc, is_workflow, excluded_sizes = task_tuple
        for size in sizes:
            if size in excluded_sizes:
                continue
            for condition in conditions:
                for rep in range(1, reps + 1):
                    matrix.append((task_tuple, size, condition, rep))
    return matrix


def save_results(results: list, results_dir: Path) -> Path:
    """Write timestamped JSON results file."""
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    out_path = results_dir / f'benchmark-{timestamp}.json'
    out_path.write_text(json.dumps(results, indent=2))
    return out_path


def _median(values: list) -> float:
    """Return the median of a list of numbers."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return float(s[mid])


def print_quick_summary(results: list):
    """Print pass/fail counts and per-condition median token usage."""
    total = len(results)
    passed = sum(1 for r in results if r['success'])
    correct = sum(1 for r in results if r['correct'])

    print(f"\n{'='*70}")
    print(f"  BENCHMARK SUMMARY: {passed}/{total} runs succeeded, {correct}/{total} correct")
    print(f"{'='*70}\n")

    for condition in ALL_CONDITIONS:
        cond_results = [r for r in results if r['condition'] == condition]
        if not cond_results:
            continue
        tokens = [r['total_tokens'] for r in cond_results if r['success'] and r['total_tokens'] > 0]
        med = _median(tokens)
        correct_count = sum(1 for r in cond_results if r['correct'])
        print(f"  {condition:10s}  runs={len(cond_results):3d}  "
              f"correct={correct_count:3d}  median_tokens={med:.0f}")

    # Per-task breakdown
    print()
    task_slugs = list(dict.fromkeys(r['task'] for r in results))
    for slug in task_slugs:
        task_results = [r for r in results if r['task'] == slug]
        for condition in ALL_CONDITIONS:
            cr = [r for r in task_results if r['condition'] == condition]
            if not cr:
                continue
            tokens = [r['total_tokens'] for r in cr if r['success'] and r['total_tokens'] > 0]
            med = _median(tokens)
            ok = sum(1 for r in cr if r['correct'])
            print(f"  {slug:22s}  {condition:10s}  correct={ok}/{len(cr)}  "
                  f"median_tokens={med:.0f}")

    print()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Run mdedit benchmarks: mdedit vs baseline token efficiency'
    )
    parser.add_argument(
        '--tasks', type=str, default=None,
        help='Comma-separated task slugs to run (default: all)',
    )
    parser.add_argument(
        '--sizes', type=str, default=None,
        help='Comma-separated sizes: small,medium,large (default: all)',
    )
    parser.add_argument(
        '--conditions', type=str, default=None,
        help='Comma-separated conditions: mdedit,baseline (default: both)',
    )
    parser.add_argument(
        '--reps', type=int, default=3,
        help='Repetitions per task/size/condition (default: 3)',
    )
    parser.add_argument(
        '--model', type=str, default='haiku',
        help='Claude model to use (default: haiku)',
    )
    parser.add_argument(
        '--workers', type=int, default=5,
        help='Parallel workers (default: 5)',
    )
    parser.add_argument(
        '--timeout', type=int, default=300,
        help='Timeout per agent in seconds (default: 300)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show what would run without executing',
    )
    args = parser.parse_args()

    # Check we are not inside a Claude Code session
    if os.environ.get('CLAUDECODE'):
        print("ERROR: Cannot run benchmarks inside a Claude Code session.")
        print("       Unset the CLAUDECODE environment variable first:")
        print("       unset CLAUDECODE && python3 run_benchmarks.py")
        sys.exit(1)

    # Resolve binary (not fatal — baseline condition doesn't need it)
    binary = verify_binary()

    # Filter tasks
    tasks_to_run = TASKS
    if args.tasks:
        requested = [t.strip() for t in args.tasks.split(',')]
        tasks_to_run = [t for t in TASKS if t[0] in requested]
        if not tasks_to_run:
            print(f"ERROR: No matching tasks for: {args.tasks}")
            sys.exit(1)

    # Filter sizes
    sizes = ALL_SIZES
    if args.sizes:
        sizes = [s.strip() for s in args.sizes.split(',')]

    # Filter conditions
    conditions = ALL_CONDITIONS
    if args.conditions:
        conditions = [c.strip() for c in args.conditions.split(',')]

    # Build matrix
    matrix = build_run_matrix(tasks_to_run, sizes, conditions, args.reps)
    total = len(matrix)

    print(f"Tasks: {len(tasks_to_run)} | Sizes: {sizes} | Conditions: {conditions} | "
          f"Reps: {args.reps} | Total runs: {total}")
    print(f"Model: {args.model} | Workers: {args.workers} | Timeout: {args.timeout}s")
    if binary:
        print(f"Binary: {binary}")
    else:
        print("Binary: NOT FOUND (mdedit condition will fail)")

    if args.dry_run:
        print(f"\n[DRY RUN] Would execute {total} runs:\n")
        for i, (task_tuple, size, condition, rep) in enumerate(matrix, 1):
            slug, desc, is_workflow, _ = task_tuple
            wf_tag = '[workflow]' if is_workflow else '[isolated]'
            print(f"  {i:3d}. {slug:22s}  {size:8s}  {condition:10s}  rep={rep}  {wf_tag}")
        print(f"\nTotal: {total} runs")
        return

    # Execute
    results = [None] * total
    completed = 0

    def _run_one(idx_and_item):
        idx, (task_tuple, size, condition, rep) = idx_and_item
        slug, desc, is_workflow, _ = task_tuple
        return idx, run_single(slug, desc, is_workflow, condition, size, rep,
                               binary, args.model, args.timeout)

    if args.workers == 1:
        for i, item in enumerate(matrix):
            task_tuple, size, condition, rep = item
            slug, desc, is_workflow, _ = task_tuple
            print(f"\n[{i+1}/{total}] {slug} / {size} / {condition} / rep={rep} ...", flush=True)
            _, result = _run_one((i, item))
            results[i] = result
            status = '+' if result['correct'] else ('!' if result['success'] else 'X')
            print(f"  [{status}] done ({result['duration_s']:.0f}s)  "
                  f"tokens={result['total_tokens']}", flush=True)
    else:
        print(f"\nRunning {total} runs in parallel (workers={args.workers})...\n")
        futures = {}
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for i, item in enumerate(matrix):
                future = executor.submit(_run_one, (i, item))
                futures[future] = i

            for future in as_completed(futures):
                _, result = future.result()
                idx = futures[future]
                results[idx] = result
                completed += 1
                status = '+' if result['correct'] else ('!' if result['success'] else 'X')
                print(
                    f"  [{status}] [{completed:3d}/{total}] "
                    f"{result['task']:22s}  {result['size']:8s}  {result['condition']:10s}  "
                    f"rep={result['rep']}  tokens={result['total_tokens']}  "
                    f"({result['duration_s']:.0f}s)",
                    flush=True,
                )

    # Save results
    out_path = save_results(results, RESULTS_DIR)
    print(f"\nResults saved to: {out_path}")

    print_quick_summary(results)


if __name__ == '__main__':
    main()
