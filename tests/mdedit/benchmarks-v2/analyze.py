#!/usr/bin/env python3
"""
Benchmark analysis — produces summary.md and narrative.md from results.

Can be run standalone:
    python3 analyze.py results/run-YYYYMMDD-HHMMSS/

Or imported by run.py for automatic post-run analysis.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median


def _compute_stats(tokens: list[int]) -> dict:
    """Compute min/median/max for a list of token counts."""
    if not tokens:
        return {'min': None, 'median': None, 'max': None, 'n': 0}
    return {
        'min': min(tokens),
        'median': median(tokens),
        'max': max(tokens),
        'n': len(tokens),
    }


def _format_stats(stats: dict) -> str:
    """Format stats as 'min/med/max' or '—'."""
    if stats['n'] == 0:
        return '—'
    return f"{stats['min']}/{int(stats['median'])}/{stats['max']}"


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------

def generate_summary(results: list[dict]) -> str:
    """
    Generate summary.md content from results.

    Produces: headline savings %, per-scenario comparison table,
    variance stats, and failure report.
    """
    valid = [r for r in results if r.get('success') and r.get('correct')]

    # Group by (task, size, condition)
    grouped = defaultdict(list)
    for r in valid:
        key = (r['task'], r['size'], r['condition'])
        grouped[key].append(r['total_tokens'])

    # Build comparison rows
    task_size_pairs = defaultdict(dict)
    for (task, size, condition), tokens in grouped.items():
        task_size_pairs[(task, size)][condition] = _compute_stats(tokens)

    rows = []
    for (task, size), conditions in sorted(task_size_pairs.items()):
        mdedit = conditions.get('mdedit')
        baseline = conditions.get('baseline')
        savings = None
        if (mdedit and baseline and mdedit['median'] and baseline['median']):
            savings = ((baseline['median'] - mdedit['median']) / baseline['median']) * 100
        rows.append({
            'task': task, 'size': size,
            'mdedit': mdedit, 'baseline': baseline,
            'savings': savings,
        })

    size_order = {'small': 0, 'medium': 1, 'large': 2}
    rows.sort(key=lambda r: (r['task'], size_order.get(r['size'], 99)))

    # Headline
    savings_list = [r['savings'] for r in rows if r['savings'] is not None]
    overall = median(savings_list) if savings_list else None

    lines = []
    date_str = datetime.now().strftime('%Y-%m-%d')
    lines.append(f'# mdedit Benchmark Results — {date_str}\n')

    if overall is not None:
        lines.append(f'**Median token savings: {overall:+.1f}%**\n')
        if overall > 0:
            lines.append(f'mdedit reduces token consumption by {overall:.1f}% on average.\n')
        elif overall < 0:
            lines.append(f'mdedit increases token consumption by {abs(overall):.1f}% on average.\n')

    # Per-scenario table
    lines.append('## Per-Scenario Comparison\n')
    lines.append('| Scenario | Size | mdedit (min/med/max) | Baseline (min/med/max) | Savings |')
    lines.append('|---|---|---|---|---|')

    for row in rows:
        m = _format_stats(row['mdedit'] or {'n': 0})
        b = _format_stats(row['baseline'] or {'n': 0})
        s = f"{row['savings']:+.1f}%" if row['savings'] is not None else '—'
        lines.append(f"| {row['task']} | {row['size']} | {m} | {b} | {s} |")

    lines.append('')

    # Variance
    lines.append('## Consistency\n')
    lines.append('| Condition | IQR/Median | Interpretation |')
    lines.append('|---|---|---|')

    for condition in ['mdedit', 'baseline']:
        tokens = [r['total_tokens'] for r in valid if r['condition'] == condition]
        if len(tokens) < 4:
            lines.append(f'| {condition} | — | Insufficient data |')
            continue
        s = sorted(tokens)
        q1 = s[len(s) // 4]
        q3 = s[(3 * len(s)) // 4]
        med = median(tokens)
        ratio = (q3 - q1) / med if med else 0
        interp = (
            'Very consistent' if ratio < 0.2 else
            'Consistent' if ratio < 0.4 else
            'Moderate variance' if ratio < 0.6 else
            'High variance'
        )
        lines.append(f'| {condition} | {ratio:.3f} | {interp} |')

    lines.append('')

    # Failures
    failures = [r for r in results if not r.get('success') or not r.get('correct')]
    if failures:
        lines.append('## Failed Runs\n')
        lines.append('| Task | Size | Condition | Rep | Status | Reason |')
        lines.append('|---|---|---|---|---|---|')
        for f in sorted(failures, key=lambda x: (x['task'], x['size'], x['condition'])):
            status = 'error' if not f.get('success') else 'incorrect'
            reason = f.get('error') or f.get('validation_reason') or ''
            if len(reason) > 60:
                reason = reason[:57] + '...'
            lines.append(
                f"| {f['task']} | {f['size']} | {f['condition']} "
                f"| {f['rep']} | {status} | {reason} |"
            )
        lines.append('')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Narrative generation
# ---------------------------------------------------------------------------

def _extract_tool_calls(transcript_json: str) -> list[dict]:
    """
    Extract tool call sequence from a transcript JSON.

    Returns list of dicts: {'tool': name, 'summary': brief description}
    """
    try:
        data = json.loads(transcript_json)
    except (json.JSONDecodeError, ValueError):
        return []

    calls = []
    messages = data.get('messages') or []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get('content') or []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            tool_name = block.get('name', 'unknown')
            tool_input = block.get('input', {})

            # Build a brief summary based on tool type
            if tool_name == 'Bash' or tool_name == 'bash':
                cmd = tool_input.get('command', '')
                summary = cmd[:100] if cmd else 'bash command'
            elif tool_name == 'Read' or tool_name == 'read':
                path = tool_input.get('file_path', '')
                summary = f'read {Path(path).name}' if path else 'read file'
            elif tool_name == 'Edit' or tool_name == 'edit':
                path = tool_input.get('file_path', '')
                summary = f'edit {Path(path).name}' if path else 'edit file'
            elif tool_name == 'Write' or tool_name == 'write':
                path = tool_input.get('file_path', '')
                summary = f'write {Path(path).name}' if path else 'write file'
            else:
                summary = tool_name

            calls.append({'tool': tool_name, 'summary': summary})

    return calls


def generate_narrative(results: list[dict], transcripts_dir: Path) -> str:
    """
    Generate narrative.md from showcase transcripts.

    Produces side-by-side comparison of tool call sequences
    for each showcase scenario/size combination.
    """
    # Find showcase scenarios (those with transcripts)
    transcript_files = list(transcripts_dir.glob('*.json'))
    if not transcript_files:
        return '# Narrative\n\nNo showcase transcripts found.\n'

    # Group transcripts by (task, size)
    grouped = defaultdict(lambda: defaultdict(list))
    for tf in transcript_files:
        # filename: replace-large-mdedit-large-rep1.json
        parts = tf.stem.rsplit('-', 3)  # name-condition-size-repN
        if len(parts) < 4:
            continue
        # Handle scenario names with hyphens by parsing from the right
        rep_str = parts[-1]  # e.g. "rep1"
        size = parts[-2]
        condition = parts[-3]
        name = '-'.join(parts[:-3])
        grouped[(name, size)][condition].append(tf)

    lines = ['# Narrative Comparison\n']

    # Get token stats from results for context
    result_lookup = defaultdict(list)
    for r in results:
        if r.get('success') and r.get('correct'):
            result_lookup[(r['task'], r['size'], r['condition'])].append(r)

    for (name, size) in sorted(grouped.keys()):
        lines.append(f'## {name} / {size}\n')

        for condition in ['baseline', 'mdedit']:
            transcripts = grouped[(name, size)].get(condition, [])
            runs = result_lookup.get((name, size, condition), [])

            tokens_list = [r['total_tokens'] for r in runs]
            med_tokens = int(median(tokens_list)) if tokens_list else 0
            tool_counts = [r['num_tool_calls'] for r in runs]
            med_tools = int(median(tool_counts)) if tool_counts else 0

            lines.append(f'### {condition} (median: {med_tokens:,} tokens, {med_tools} tool calls)\n')

            # Show tool calls from first available transcript
            if transcripts:
                transcript_text = transcripts[0].read_text()
                calls = _extract_tool_calls(transcript_text)
                if calls:
                    for i, call in enumerate(calls, 1):
                        lines.append(f'{i}. **{call["tool"]}** — {call["summary"]}')
                    lines.append('')
                else:
                    lines.append('(no tool calls extracted)\n')
            else:
                lines.append('(no transcript available)\n')

        # Savings line
        mdedit_runs = result_lookup.get((name, size, 'mdedit'), [])
        baseline_runs = result_lookup.get((name, size, 'baseline'), [])
        if mdedit_runs and baseline_runs:
            m_med = median([r['total_tokens'] for r in mdedit_runs])
            b_med = median([r['total_tokens'] for r in baseline_runs])
            if b_med > 0:
                pct = ((b_med - m_med) / b_med) * 100
                lines.append(f'**Savings: {pct:.1f}% fewer tokens**\n')

        lines.append('---\n')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Standalone CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print('Usage: python3 analyze.py results/run-YYYYMMDD-HHMMSS/')
        sys.exit(1)

    run_dir = Path(sys.argv[1])
    results_path = run_dir / 'results.json'

    if not results_path.exists():
        print(f'ERROR: {results_path} not found')
        sys.exit(1)

    results = json.loads(results_path.read_text())

    # Generate summary
    summary_path = run_dir / 'summary.md'
    summary_path.write_text(generate_summary(results))
    print(f'Summary:   {summary_path}')

    # Generate narrative if transcripts exist
    transcripts_dir = run_dir / 'transcripts'
    if transcripts_dir.exists() and list(transcripts_dir.glob('*.json')):
        narrative_path = run_dir / 'narrative.md'
        narrative_path.write_text(generate_narrative(results, transcripts_dir))
        print(f'Narrative: {narrative_path}')
    else:
        print('No transcripts found, skipping narrative')


if __name__ == '__main__':
    main()
