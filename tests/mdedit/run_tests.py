#!/usr/bin/env python3
"""
LLM integration test runner for mdedit v1.

Launches Claude CLI agents to test mdedit commands, one agent per test group.
Each agent writes a structured markdown report. The runner collates results.

Usage:
    python3 run_tests.py [--groups 1,2,3] [--model haiku] [--workers 5] [--dry-run]

Requirements:
    - claude CLI installed and authenticated
    - mdedit release binary built (cargo build --release)
    - Must NOT be run from inside a Claude Code session (unset CLAUDECODE first)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PROMPTS_DIR = SCRIPT_DIR / 'prompts'
SAMPLES_DIR = SCRIPT_DIR / 'samples'
RESULTS_DIR = SCRIPT_DIR / 'results'
MDEDIT_BINARY = SCRIPT_DIR.parent.parent / 'claude-code-only' / 'mdedit' / 'target' / 'release' / 'mdedit'

# Group definitions: (number, slug, description)
GROUPS = [
    (1, 'read-structure', 'Read: Structure (outline, stats, validate)'),
    (2, 'read-content', 'Read: Content (extract, search)'),
    (3, 'frontmatter', 'Frontmatter (show, get, set, delete)'),
    (4, 'replace', 'Replace (all modes, preamble, dry-run, no-op)'),
    (5, 'append-prepend', 'Append + Prepend (including preamble)'),
    (6, 'insert-delete-rename', 'Insert + Delete + Rename'),
    (7, 'addressing-exit-codes', 'Addressing + Exit Codes'),
    (8, 'edge-cases', 'Edge Cases'),
    (9, 'workflows', 'Workflows'),
]


def verify_binary() -> Path:
    """Verify the mdedit binary exists and is executable."""
    if not MDEDIT_BINARY.exists():
        print(f"ERROR: mdedit binary not found at {MDEDIT_BINARY}")
        print(f"       Build it first: cd claude-code-only/mdedit && cargo build --release")
        sys.exit(1)

    # Quick smoke test
    result = subprocess.run(
        [str(MDEDIT_BINARY), '--help'],
        capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        print(f"ERROR: mdedit binary failed smoke test (--help returned {result.returncode})")
        sys.exit(1)

    return MDEDIT_BINARY.resolve()


def setup_workdir(group_num: int, group_slug: str) -> Path:
    """Create a temp working directory with pristine sample files."""
    timestamp = int(time.time())
    workdir = Path(f'/tmp/mdedit-test-group-{group_num}-{timestamp}')
    pristine = workdir / 'pristine'

    # Copy samples to pristine/
    shutil.copytree(SAMPLES_DIR, pristine)

    return workdir


def substitute_placeholders(content: str, binary: Path, workdir: Path,
                            report_path: Path) -> str:
    """Replace {{BINARY}}, {{WORKDIR}}, {{REPORT_PATH}} in prompt content."""
    content = content.replace('{{BINARY}}', str(binary))
    content = content.replace('{{WORKDIR}}', str(workdir))
    content = content.replace('{{REPORT_PATH}}', str(report_path))
    return content


def run_group(group_num: int, group_slug: str, group_desc: str,
              binary: Path, model: str, timeout: int,
              dry_run: bool = False) -> dict:
    """Run a single test group and return the result."""
    # Setup
    workdir = setup_workdir(group_num, group_slug)
    report_path = workdir / f'group-{group_num}-{group_slug}.md'

    # Read prompts
    system_prompt_file = PROMPTS_DIR / 'system.md'
    group_prompt_file = PROMPTS_DIR / f'group-{group_num}-{group_slug}.md'

    if not system_prompt_file.exists():
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': False, 'error': f'System prompt not found: {system_prompt_file}',
            'report_path': None, 'duration_s': 0,
        }

    if not group_prompt_file.exists():
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': False, 'error': f'Group prompt not found: {group_prompt_file}',
            'report_path': None, 'duration_s': 0,
        }

    system_prompt = substitute_placeholders(
        system_prompt_file.read_text(), binary, workdir, report_path
    )
    user_prompt = substitute_placeholders(
        group_prompt_file.read_text(), binary, workdir, report_path
    )

    if dry_run:
        print(f"  [DRY RUN] Group {group_num}: {group_desc}")
        print(f"    workdir: {workdir}")
        print(f"    report:  {report_path}")
        print(f"    system prompt: {len(system_prompt)} chars")
        print(f"    user prompt:   {len(user_prompt)} chars")
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': True, 'error': 'DRY RUN',
            'report_path': None, 'duration_s': 0,
        }

    # Launch claude
    cmd = [
        'claude', '-p',
        '--output-format', 'json',
        '--system-prompt', system_prompt,
        '--model', model,
        '--no-chrome',
        '--dangerously-skip-permissions',
    ]

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(workdir),
        )
        duration = time.time() - start_time

        if result.returncode != 0:
            return {
                'group': group_num, 'slug': group_slug, 'desc': group_desc,
                'passed': False,
                'error': f"claude exited {result.returncode}: {result.stderr[:500]}",
                'report_path': None, 'duration_s': duration,
            }

        # Check if report was written
        if not report_path.exists():
            return {
                'group': group_num, 'slug': group_slug, 'desc': group_desc,
                'passed': False,
                'error': 'Agent completed but no report file was written',
                'report_path': None, 'duration_s': duration,
            }

        # Extract summary line from report
        report_content = report_path.read_text()
        summary_match = re.search(r'\*\*Result:\*\*\s*(\d+)/(\d+)', report_content)

        if summary_match:
            passed_count = int(summary_match.group(1))
            total_count = int(summary_match.group(2))
            all_passed = (passed_count == total_count)
        else:
            passed_count = '?'
            total_count = '?'
            all_passed = False

        # Copy report to results directory
        RESULTS_DIR.mkdir(exist_ok=True)
        final_report = RESULTS_DIR / f'group-{group_num}-{group_slug}.md'
        shutil.copy2(report_path, final_report)

        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': all_passed,
            'tests_passed': passed_count,
            'tests_total': total_count,
            'error': '',
            'report_path': str(final_report),
            'duration_s': duration,
        }

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': False, 'error': f'Timeout ({timeout}s)',
            'report_path': None, 'duration_s': duration,
        }
    except Exception as e:
        duration = time.time() - start_time
        return {
            'group': group_num, 'slug': group_slug, 'desc': group_desc,
            'passed': False, 'error': str(e),
            'report_path': None, 'duration_s': duration,
        }


def print_summary(results: list):
    """Print a summary table of results."""
    passed = sum(1 for r in results if r['passed'])
    total = len(results)

    print(f"\n{'='*70}")
    print(f"  MDEDIT TEST RESULTS: {passed}/{total} groups passed")
    print(f"{'='*70}\n")

    for r in sorted(results, key=lambda x: x['group']):
        status = 'PASS' if r['passed'] else 'FAIL'
        icon = '+' if r['passed'] else 'X'
        time_str = f"({r['duration_s']:.0f}s)" if r['duration_s'] else ""

        tests_str = ''
        if 'tests_passed' in r:
            tests_str = f" [{r['tests_passed']}/{r['tests_total']} tests]"

        print(f"  [{icon}] Group {r['group']}: {r['desc']}{tests_str} {time_str}")

        if r['error'] and r['error'] != 'DRY RUN':
            print(f"       ERROR: {r['error']}")

    print()
    if passed < total:
        failed_groups = [r['group'] for r in results if not r['passed']]
        print(f"  Re-run failed groups: python3 {__file__} --groups {','.join(map(str, failed_groups))}")

    report_paths = [r['report_path'] for r in results if r.get('report_path')]
    if report_paths:
        print(f"\n  Reports saved to: {RESULTS_DIR}/")


def main():
    parser = argparse.ArgumentParser(description='Run mdedit LLM integration tests')
    parser.add_argument('--groups', type=str, default=None,
                        help='Comma-separated group numbers to run (default: all)')
    parser.add_argument('--model', type=str, default='haiku',
                        help='Claude model to use (default: haiku)')
    parser.add_argument('--workers', type=int, default=5,
                        help='Parallel workers (default: 5)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='Timeout per agent in seconds (default: 300)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would run without executing')
    args = parser.parse_args()

    # Check we're not inside Claude Code
    if os.environ.get('CLAUDECODE'):
        print("ERROR: Cannot run tests inside a Claude Code session.")
        print("       Unset the CLAUDECODE environment variable first:")
        print("       unset CLAUDECODE && python3 run_tests.py")
        sys.exit(1)

    # Verify binary
    binary = verify_binary()
    print(f"Binary: {binary}")

    # Filter groups
    groups_to_run = GROUPS
    if args.groups:
        group_ids = [int(x.strip()) for x in args.groups.split(',')]
        groups_to_run = [g for g in GROUPS if g[0] in group_ids]

    total = len(groups_to_run)
    print(f"Groups: {total} | Model: {args.model} | Workers: {args.workers} | Timeout: {args.timeout}s")

    if args.dry_run:
        for num, slug, desc in groups_to_run:
            run_group(num, slug, desc, binary, args.model, args.timeout, dry_run=True)
        return

    # Run groups
    results = [None] * total
    completed = 0

    if args.workers == 1:
        for i, (num, slug, desc) in enumerate(groups_to_run):
            print(f"\n[{i+1}/{total}] Running Group {num}: {desc}...", flush=True)
            result = run_group(num, slug, desc, binary, args.model, args.timeout)
            results[i] = result
            status = '+' if result['passed'] else 'X'
            print(f"  [{status}] Done ({result['duration_s']:.0f}s)")
    else:
        print(f"\nRunning {total} groups in parallel...\n")
        futures = {}
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for i, (num, slug, desc) in enumerate(groups_to_run):
                future = executor.submit(
                    run_group, num, slug, desc, binary, args.model, args.timeout
                )
                futures[future] = i

            for future in as_completed(futures):
                i = futures[future]
                result = future.result()
                results[i] = result
                completed += 1
                status = '+' if result['passed'] else 'X'
                time_str = f"({result['duration_s']:.0f}s)" if result['duration_s'] else ""
                tests_str = ''
                if 'tests_passed' in result:
                    tests_str = f" [{result['tests_passed']}/{result['tests_total']}]"
                print(f"  [{status}] [{completed:2d}/{total}] Group {result['group']}: "
                      f"{result['desc']}{tests_str} {time_str}", flush=True)

    print_summary(results)


if __name__ == '__main__':
    main()
