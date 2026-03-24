"""
Correctness validation module for benchmark runs.

Provides validation functions to compare modified fixtures against expected output,
extract and verify sections, and check structural validity (TOC).
"""

import difflib
import re
from pathlib import Path


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace in text for comparison.

    - Strip trailing whitespace from each line
    - Collapse multiple blank lines to single blank line
    - Strip trailing newlines at EOF
    - End with single newline

    Args:
        text: Input text to normalize

    Returns:
        Normalized text
    """
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in text.split('\n')]

    # Collapse multiple blank lines to single blank line
    normalized_lines = []
    prev_blank = False
    for line in lines:
        is_blank = line == ''
        if is_blank and prev_blank:
            continue
        normalized_lines.append(line)
        prev_blank = is_blank

    # Join and ensure single trailing newline
    result = '\n'.join(normalized_lines)
    # Strip any trailing whitespace/newlines
    result = result.rstrip('\n')
    # Add back single newline
    result = result + '\n' if result else '\n'

    return result


def _extract_section(markdown: str, section_name: str) -> str | None:
    """
    Extract a section from markdown by heading name.

    Finds the heading matching section_name and returns content from that heading
    through to (but not including) the next same-or-higher-level heading.

    Args:
        markdown: Markdown text to search
        section_name: Name of the section heading to extract

    Returns:
        Section content including the heading, or None if not found
    """
    lines = markdown.split('\n')

    # Find the heading line that matches section_name
    heading_pattern = r'^(#{1,6})\s+(.+)$'
    start_idx = None
    start_level = None

    for i, line in enumerate(lines):
        match = re.match(heading_pattern, line)
        if match:
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            if heading_text == section_name:
                start_idx = i
                start_level = level
                break

    if start_idx is None:
        return None

    # Find the next heading at same or higher level (fewer #'s)
    # We want the content UP TO but not including that heading
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        match = re.match(heading_pattern, lines[i])
        if match:
            level = len(match.group(1))
            if level <= start_level:
                end_idx = i
                break

    # Return section content (not including the next heading)
    section_lines = lines[start_idx:end_idx]
    # Remove trailing blank lines before joining
    while section_lines and section_lines[-1].strip() == '':
        section_lines.pop()

    return '\n'.join(section_lines)


def validate_isolated(result_file: Path, expected_file: Path) -> dict:
    """
    Compare a modified fixture against expected output after whitespace normalization.

    Args:
        result_file: Path to the result file (modified fixture)
        expected_file: Path to the expected output file

    Returns:
        dict with keys:
            - 'valid': bool indicating if files match after normalization
            - 'reason': str explaining the validation result
            - 'diff': str with unified diff if invalid, empty if valid
    """
    try:
        result_text = result_file.read_text()
        expected_text = expected_file.read_text()
    except FileNotFoundError as e:
        return {
            'valid': False,
            'reason': f'File not found: {e}',
            'diff': ''
        }

    # Normalize both texts
    normalized_result = normalize_whitespace(result_text)
    normalized_expected = normalize_whitespace(expected_text)

    if normalized_result == normalized_expected:
        return {
            'valid': True,
            'reason': 'Output matches expected after whitespace normalization',
            'diff': ''
        }

    # Generate unified diff
    result_lines = normalized_result.splitlines(keepends=True)
    expected_lines = normalized_expected.splitlines(keepends=True)
    diff = ''.join(difflib.unified_diff(
        expected_lines,
        result_lines,
        fromfile='expected',
        tofile='result',
        lineterm=''
    ))

    return {
        'valid': False,
        'reason': 'Output does not match expected after whitespace normalization',
        'diff': diff
    }


def validate_targeted_read(report_text: str, fixture_file: Path, section_name: str) -> dict:
    """
    Check that the agent's response contains the correct section content.

    Extracts the section from the fixture, normalizes it, and checks if it appears
    in the normalized report text.

    Args:
        report_text: The agent's response text to check
        fixture_file: Path to the fixture file containing expected sections
        section_name: Name of the section heading to validate

    Returns:
        dict with keys:
            - 'valid': bool indicating if section was found and matches
            - 'reason': str explaining the validation result
            - 'diff': str with context (always empty for this validation)
    """
    try:
        fixture_text = fixture_file.read_text()
    except FileNotFoundError:
        return {
            'valid': False,
            'reason': f'Fixture file not found: {fixture_file}',
            'diff': ''
        }

    # Extract the section from fixture
    section_content = _extract_section(fixture_text, section_name)
    if section_content is None:
        return {
            'valid': False,
            'reason': f'Section "{section_name}" not found in fixture',
            'diff': ''
        }

    # Normalize both texts, stripping trailing newlines for substring matching
    normalized_section = normalize_whitespace(section_content).rstrip('\n')
    normalized_report = normalize_whitespace(report_text).rstrip('\n')

    if normalized_section in normalized_report:
        return {
            'valid': True,
            'reason': f'Section "{section_name}" found in report',
            'diff': ''
        }

    return {
        'valid': False,
        'reason': f'Section "{section_name}" not found in report after normalization',
        'diff': ''
    }


def validate_build_toc(result_file: Path) -> dict:
    """
    Check that a TOC (lines starting with `- ` or `  - `) exists near the top.

    Skips frontmatter (YAML between --- delimiters) and looks for list items
    in the first 50 lines after frontmatter.

    Args:
        result_file: Path to the file to validate

    Returns:
        dict with keys:
            - 'valid': bool indicating if TOC was found
            - 'reason': str explaining the validation result
            - 'diff': str with context (always empty for this validation)
    """
    try:
        text = result_file.read_text()
    except FileNotFoundError:
        return {
            'valid': False,
            'reason': f'File not found: {result_file}',
            'diff': ''
        }

    lines = text.split('\n')

    # Skip frontmatter (--- delimited)
    start_idx = 0
    if lines and lines[0].strip() == '---':
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                start_idx = i + 1
                break

    # Look for list items in first 50 lines after frontmatter
    search_lines = lines[start_idx:start_idx + 50]

    for line in search_lines:
        if re.match(r'^\s*-\s+', line):
            return {
                'valid': True,
                'reason': 'TOC (list items) found near top of document',
                'diff': ''
            }

    return {
        'valid': False,
        'reason': 'No TOC (list items) found in first 50 lines after frontmatter',
        'diff': ''
    }


def validate_edit_and_verify(report_text: str, expected_content: str) -> dict:
    """
    Check that the agent's response contains the expected replacement content.

    Normalizes both texts and checks if the expected content appears in the report.

    Args:
        report_text: The agent's response text
        expected_content: The content expected to appear in the report

    Returns:
        dict with keys:
            - 'valid': bool indicating if expected content was found
            - 'reason': str explaining the validation result
            - 'diff': str with context (always empty for this validation)
    """
    # Normalize both texts, stripping trailing newlines for substring matching
    normalized_report = normalize_whitespace(report_text).rstrip('\n')
    normalized_expected = normalize_whitespace(expected_content).rstrip('\n')

    if normalized_expected in normalized_report:
        return {
            'valid': True,
            'reason': 'Expected content found in report',
            'diff': ''
        }

    return {
        'valid': False,
        'reason': 'Expected content not found in report after normalization',
        'diff': ''
    }
