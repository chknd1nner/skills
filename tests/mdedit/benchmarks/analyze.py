#!/usr/bin/env python3
"""
Benchmark results analysis script.

Reads JSON result files from benchmark runs and produces summary tables:
- Per-task comparison (mdedit vs baseline, min/median/max tokens, savings %)
- Tool usage frequency by condition
- Variance comparison (spread measure per condition)
- Failure report

Usage:
    python3 analyze.py results/benchmark-TIMESTAMP.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median


def load_results(path: str) -> list:
    """
    Load benchmark results from JSON file.

    Args:
        path: Path to the results JSON file

    Returns:
        List of result dictionaries
    """
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            # If the JSON is a dict with a 'results' key, extract that
            if isinstance(data, dict) and 'results' in data:
                return data['results']
            # Otherwise assume it's already a list
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"ERROR: Failed to load results file: {e}", file=sys.stderr)
        sys.exit(1)


def filter_valid(results: list) -> list:
    """
    Filter to only valid, successful runs.

    Args:
        results: List of result dictionaries

    Returns:
        List of results where success=True and correct=True
    """
    return [r for r in results if r.get('success') and r.get('correct')]


def compute_stats(tokens: list) -> dict:
    """
    Compute statistics for a list of token counts.

    Args:
        tokens: List of token counts (integers)

    Returns:
        Dictionary with 'min', 'median', 'max', and 'n' (count)
    """
    if not tokens:
        return {'min': None, 'median': None, 'max': None, 'n': 0}

    sorted_tokens = sorted(tokens)
    return {
        'min': min(tokens),
        'median': median(tokens),
        'max': max(tokens),
        'n': len(tokens)
    }


def per_task_comparison(results: list) -> list:
    """
    Group results by task, size, and condition; compute stats and savings.

    Args:
        results: List of valid result dictionaries

    Returns:
        List of comparison rows, each with:
        - task, size
        - mdedit_stats (min, median, max)
        - baseline_stats (min, median, max)
        - delta (baseline_median - mdedit_median)
        - savings_percent (delta / baseline_median * 100)
    """
    # Group by (task, size, condition)
    grouped = defaultdict(list)
    for r in results:
        key = (r.get('task'), r.get('size'), r.get('condition'))
        grouped[key].append(r.get('total_tokens', 0))

    # Build comparison rows
    rows = []
    task_size_pairs = defaultdict(lambda: {})

    for (task, size, condition), tokens in grouped.items():
        if task is None or size is None or condition is None:
            continue

        key = (task, size)
        stats = compute_stats(tokens)
        task_size_pairs[key][condition] = stats

    # Compute deltas and savings
    for (task, size), conditions in sorted(task_size_pairs.items()):
        mdedit_stats = conditions.get('mdedit')
        baseline_stats = conditions.get('baseline')

        if mdedit_stats and baseline_stats and mdedit_stats['median'] and baseline_stats['median']:
            delta = baseline_stats['median'] - mdedit_stats['median']
            savings_percent = (delta / baseline_stats['median']) * 100
        else:
            delta = None
            savings_percent = None

        rows.append({
            'task': task,
            'size': size,
            'mdedit': mdedit_stats,
            'baseline': baseline_stats,
            'delta': delta,
            'savings_percent': savings_percent,
        })

    # Sort by task, then by size (small, medium, large)
    size_order = {'small': 0, 'medium': 1, 'large': 2}
    rows.sort(key=lambda r: (r['task'], size_order.get(r['size'], 999)))

    return rows


def tool_usage_summary(results: list) -> dict:
    """
    Count tool usage frequency per condition.

    Args:
        results: List of valid result dictionaries

    Returns:
        Dictionary: {condition: {tool_name: count, ...}, ...}
    """
    usage = defaultdict(lambda: defaultdict(int))

    for r in results:
        condition = r.get('condition')
        tool_calls = r.get('tool_calls', [])

        if condition:
            for call in tool_calls:
                tool_name = call.get('tool') if isinstance(call, dict) else call
                if tool_name:
                    usage[condition][tool_name] += 1

    return {cond: dict(tools) for cond, tools in usage.items()}


def variance_comparison(results: list) -> dict:
    """
    Compute spread (IQR-based) as consistency measure per condition.

    Args:
        results: List of valid result dictionaries

    Returns:
        Dictionary: {condition: {'iqr_ratio': float, 'description': str}, ...}
        where iqr_ratio = (Q3 - Q1) / median as a measure of spread
    """
    # Group by condition
    grouped = defaultdict(list)
    for r in results:
        condition = r.get('condition')
        tokens = r.get('total_tokens', 0)
        if condition:
            grouped[condition].append(tokens)

    variance_results = {}
    for condition, tokens in grouped.items():
        if len(tokens) < 3:
            variance_results[condition] = {'iqr_ratio': None, 'description': 'Insufficient data'}
            continue

        sorted_tokens = sorted(tokens)
        n = len(sorted_tokens)

        # Compute Q1 (25th percentile) and Q3 (75th percentile)
        q1_idx = n // 4
        q3_idx = (3 * n) // 4

        q1 = sorted_tokens[q1_idx]
        q3 = sorted_tokens[q3_idx]
        med = median(tokens)

        if med and med != 0:
            iqr_ratio = (q3 - q1) / med
        else:
            iqr_ratio = None

        variance_results[condition] = {
            'iqr_ratio': iqr_ratio,
            'q1': q1,
            'q3': q3,
            'median': med,
        }

    return variance_results


def failure_report(results: list) -> list:
    """
    List all failed or invalid runs.

    Args:
        results: Full list of result dictionaries (before filtering)

    Returns:
        List of failed runs with task, condition, error details
    """
    failures = []
    for r in results:
        if not r.get('success') or not r.get('correct'):
            failures.append({
                'task': r.get('task'),
                'task_desc': r.get('task_desc'),
                'size': r.get('size'),
                'condition': r.get('condition'),
                'rep': r.get('rep'),
                'success': r.get('success'),
                'correct': r.get('correct'),
                'validation_reason': r.get('validation_reason'),
                'error': r.get('error'),
            })

    return sorted(failures, key=lambda f: (f.get('task', ''), f.get('size', ''), f.get('condition', '')))


def print_markdown(rows: list, tool_usage: dict, variance: dict, failures: list):
    """
    Render results as markdown tables.

    Args:
        rows: Per-task comparison rows
        tool_usage: Tool usage frequency dictionary
        variance: Variance comparison dictionary
        failures: List of failed runs
    """
    # Compute overall median savings percentage
    savings_percentages = [r['savings_percent'] for r in rows if r['savings_percent'] is not None]
    if savings_percentages:
        overall_savings = median(savings_percentages)
    else:
        overall_savings = None

    # Headline
    print("# mdedit Benchmark Analysis\n")

    if overall_savings is not None:
        print(f"## Overall Results\n")
        print(f"**Median token savings: {overall_savings:+.1f}%**\n")
        if overall_savings > 0:
            print(f"✓ mdedit reduces token consumption by {overall_savings:.1f}% on average")
        elif overall_savings < 0:
            print(f"✗ mdedit increases token consumption by {abs(overall_savings):.1f}% on average")
        else:
            print(f"≈ No net token difference")
        print()

    # Per-task comparison table
    print("## Per-Task Comparison\n")
    print("|Task|Size|mdedit (tokens)|Baseline (tokens)|Savings|")
    print("|---|---|---|---|---|")

    for row in rows:
        task = row['task']
        size = row['size']
        mdedit = row['mdedit']
        baseline = row['baseline']
        savings = row['savings_percent']

        # Format mdedit cell (min/med/max)
        if mdedit and mdedit['n'] > 0:
            mdedit_str = f"{mdedit['min']}/{int(mdedit['median'])}/{mdedit['max']}"
        else:
            mdedit_str = "—"

        # Format baseline cell (min/med/max)
        if baseline and baseline['n'] > 0:
            baseline_str = f"{baseline['min']}/{int(baseline['median'])}/{baseline['max']}"
        else:
            baseline_str = "—"

        # Format savings
        if savings is not None:
            if savings > 0:
                savings_str = f"+{savings:.1f}%"
            else:
                savings_str = f"{savings:.1f}%"
        else:
            savings_str = "—"

        print(f"|{task}|{size}|{mdedit_str}|{baseline_str}|{savings_str}|")

    print()

    # Tool usage table
    print("## Tool Usage Frequency\n")
    if tool_usage:
        print("|Condition|Tool|Count|")
        print("|---|---|---|")

        for condition in sorted(tool_usage.keys()):
            tools = tool_usage[condition]
            for tool_name in sorted(tools.keys()):
                count = tools[tool_name]
                print(f"|{condition}|{tool_name}|{count}|")
    else:
        print("No tool usage data available.\n")

    print()

    # Variance comparison table
    print("## Consistency (Variance)\n")
    if variance:
        print("|Condition|IQR/Median Ratio|Interpretation|")
        print("|---|---|---|")

        for condition in sorted(variance.keys()):
            v = variance[condition]
            if v['iqr_ratio'] is not None:
                ratio = v['iqr_ratio']
                if ratio < 0.2:
                    interp = "Very consistent"
                elif ratio < 0.4:
                    interp = "Consistent"
                elif ratio < 0.6:
                    interp = "Moderate variance"
                else:
                    interp = "High variance"
                print(f"|{condition}|{ratio:.3f}|{interp}|")
            else:
                print(f"|{condition}|—|{v.get('description', 'N/A')}|")
    else:
        print("No variance data available.\n")

    print()

    # Failure report
    if failures:
        print("## Failed Runs\n")
        print("|Task|Size|Condition|Rep|Success|Correct|Reason|Error|")
        print("|---|---|---|---|---|---|---|---|")

        for f in failures:
            task = f.get('task', '—')
            size = f.get('size', '—')
            condition = f.get('condition', '—')
            rep = f.get('rep', '—')
            success = '✓' if f.get('success') else '✗'
            correct = '✓' if f.get('correct') else '✗'
            reason = f.get('validation_reason', '')
            error = f.get('error', '')

            # Truncate long error messages
            if len(error) > 50:
                error = error[:47] + "..."

            print(f"|{task}|{size}|{condition}|{rep}|{success}|{correct}|{reason}|{error}|")

        print()
    else:
        print("## Results\n")
        print("✓ All runs passed validation.\n")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze mdedit benchmark results',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python3 analyze.py results/benchmark-1234567890.json"
    )
    parser.add_argument('results_file', help='Path to benchmark results JSON file')

    args = parser.parse_args()

    # Load results
    all_results = load_results(args.results_file)

    # Filter to valid runs
    valid_results = filter_valid(all_results)

    if not valid_results:
        print("WARNING: No valid results found in the results file", file=sys.stderr)

    # Compute analyses
    comparison_rows = per_task_comparison(valid_results)
    tool_usage = tool_usage_summary(valid_results)
    variance = variance_comparison(valid_results)
    failures = failure_report(all_results)

    # Print markdown
    print_markdown(comparison_rows, tool_usage, variance, failures)


if __name__ == '__main__':
    main()
