"""
Validation module for mdedit benchmark suite.

Two validation modes:
- validate_file_diff: compare modified fixture against expected output
- validate_report_contains: check that expected strings appear in agent output
"""

import difflib
import re
from pathlib import Path


def _normalize(text: str) -> str:
    """Normalize whitespace for comparison.

    - Strip trailing whitespace from each line
    - Collapse multiple blank lines to single blank line
    - Strip trailing newlines at EOF
    - End with single newline
    """
    lines = text.splitlines()
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in lines]
    # Rejoin and collapse multiple blank lines to single blank line
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    # Strip trailing newlines and end with single newline
    normalized = normalized.rstrip("\n") + "\n"
    return normalized


def validate_file_diff(result_path: Path, expected_path: Path) -> dict:
    """Compare a modified fixture against expected output after whitespace normalization.

    Returns:
        {'valid': bool, 'reason': str, 'diff': str}
    """
    try:
        result_text = Path(result_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        return {"valid": False, "reason": f"File not found: {e}", "diff": ""}

    try:
        expected_text = Path(expected_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        return {"valid": False, "reason": f"File not found: {e}", "diff": ""}

    result_norm = _normalize(result_text)
    expected_norm = _normalize(expected_text)

    if result_norm == expected_norm:
        return {"valid": True, "reason": "Output matches expected", "diff": ""}

    diff_lines = difflib.unified_diff(
        expected_norm.splitlines(keepends=True),
        result_norm.splitlines(keepends=True),
        fromfile=str(expected_path),
        tofile=str(result_path),
    )
    diff = "".join(diff_lines)
    return {"valid": False, "reason": "Output does not match expected", "diff": diff}


def validate_report_contains(agent_output: str, report_path: Path, expected_strings: list) -> dict:
    """Check that ALL expected strings appear in the agent's output.

    Checks report_path file first (if it exists and has content), falls back to agent_output.

    Both expected strings and search text are whitespace-normalized before comparison.

    Returns:
        {'valid': bool, 'reason': str}
    """
    search_text = ""

    # Try report_path first
    try:
        content = Path(report_path).read_text(encoding="utf-8").strip()
        if content:
            search_text = content
    except (FileNotFoundError, OSError):
        pass

    # Fall back to agent_output if report file had no usable content
    if not search_text:
        search_text = agent_output

    search_norm = _normalize(search_text)

    missing = []
    for expected in expected_strings:
        expected_norm = _normalize(expected).strip()
        if expected_norm not in search_norm:
            missing.append(expected[:80])

    if not missing:
        return {"valid": True, "reason": "All expected strings found"}

    return {"valid": False, "reason": f"Missing: {', '.join(missing)}"}
