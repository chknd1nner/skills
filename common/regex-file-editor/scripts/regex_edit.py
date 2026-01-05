#!/usr/bin/env python3
"""
Standalone regex editing tool extracted from Serena.
Provides token-efficient file editing with advanced regex capabilities.

Features:
- Custom backreference syntax ($!1, $!2, etc.)
- Ambiguity detection for multiline matches
- Multi-file pattern searching
- Glob pattern filtering with brace expansion
"""

import argparse
import difflib
import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Literal


class LineType(str, Enum):
    """Types of lines in search results."""
    MATCH = "match"
    BEFORE_MATCH = "prefix"
    AFTER_MATCH = "postfix"


@dataclass
class TextLine:
    """Represents a line of text with match metadata."""
    line_number: int
    line_content: str
    match_type: LineType

    def to_dict(self):
        return {
            "line_number": self.line_number,
            "line_content": self.line_content,
            "match_type": self.match_type.value
        }


@dataclass
class MatchedConsecutiveLines:
    """Represents consecutive lines found through pattern matching."""
    lines: list[TextLine]
    source_file_path: str | None = None

    @property
    def matched_lines(self):
        return [line for line in self.lines if line.match_type == LineType.MATCH]

    def to_dict(self):
        return {
            "source_file": self.source_file_path,
            "start_line": self.lines[0].line_number if self.lines else 0,
            "end_line": self.lines[-1].line_number if self.lines else 0,
            "matched_text": "\n".join(line.line_content for line in self.matched_lines),
            "context_before": [line.line_content for line in self.lines if line.match_type == LineType.BEFORE_MATCH],
            "context_after": [line.line_content for line in self.lines if line.match_type == LineType.AFTER_MATCH],
            "all_lines": [line.to_dict() for line in self.lines]
        }


def create_replacement_function(regex_pattern: str, repl_template: str, regex_flags: int) -> Callable[[re.Match], str]:
    """
    Creates a replacement function that validates for ambiguity and handles custom backreferences.

    Custom Backreference Syntax:
        $!1, $!2, $!3, etc. instead of \\1, \\2, \\3
        This avoids conflicts with dollar signs commonly found in code.

    Ambiguity Detection:
        For multiline matches, checks if the pattern matches again within an already-matched text.
        This prevents unintended nested replacements.

    :param regex_pattern: The regex pattern being used for matching
    :param repl_template: The replacement template with $!1, $!2, etc. for backreferences
    :param regex_flags: The flags to use when searching (e.g., re.DOTALL | re.MULTILINE)
    :return: A function suitable for use with re.sub() or re.subn()
    """

    def validate_and_replace(match: re.Match) -> str:
        matched_text = match.group(0)

        # For multi-line match, check if the same pattern matches again within the already-matched text
        # This detects ambiguous patterns like:
        #    <start><other-stuff><start><stuff><end>
        # When matching <start>.*?<end>, this would match the entire span,
        # while only the suffix may have been intended.
        if "\n" in matched_text and re.search(regex_pattern, matched_text[1:], flags=regex_flags):
            raise ValueError(
                "Match is ambiguous: the search pattern matches multiple overlapping occurrences. "
                "Please revise the search pattern to be more specific to avoid ambiguity."
            )

        # Handle custom backreferences: replace $!1, $!2, etc. with actual matched groups
        def expand_backreference(m: re.Match) -> str:
            group_num = int(m.group(1))
            try:
                group_value = match.group(group_num)
                return group_value if group_value is not None else m.group(0)
            except IndexError:
                # Group doesn't exist in the match
                return m.group(0)

        result = re.sub(r"\$!(\d+)", expand_backreference, repl_template)
        return result

    return validate_and_replace


def replace_in_file(
    file_path: str,
    needle: str,
    repl: str,
    mode: Literal["literal", "regex"] = "regex",
    allow_multiple_occurrences: bool = False,
    encoding: str = "utf-8"
) -> dict:
    """
    Replaces content in a file using literal or regex matching.

    :param file_path: Path to the file to edit
    :param needle: The string or regex pattern to search for
    :param repl: The replacement string (supports $!1, $!2, etc. for regex mode)
    :param mode: Either "literal" or "regex"
    :param allow_multiple_occurrences: If True, replace all matches; if False, error on multiple matches
    :param encoding: File encoding (default: utf-8)
    :return: Dict with status, message, and match information
    """
    try:
        # Read file
        with open(file_path, 'r', encoding=encoding) as f:
            original_content = f.read()

        # Prepare regex pattern
        if mode == "literal":
            regex = re.escape(needle)
        elif mode == "regex":
            regex = needle
        else:
            return {
                "status": "error",
                "message": f"Invalid mode: '{mode}', expected 'literal' or 'regex'."
            }

        regex_flags = re.DOTALL | re.MULTILINE

        # Create replacement function with validation and backreference handling
        repl_fn = create_replacement_function(regex, repl, regex_flags=regex_flags)

        # Perform replacement
        updated_content, n = re.subn(regex, repl_fn, original_content, flags=regex_flags)

        # Validate match count
        if n == 0:
            return {
                "status": "error",
                "message": f"No matches of search expression found in file '{file_path}'.",
                "matches_count": 0
            }

        if not allow_multiple_occurrences and n > 1:
            return {
                "status": "error",
                "message": f"Expression matches {n} occurrences in file '{file_path}'. "
                          "Please revise the expression to be more specific or use --allow-multiple.",
                "matches_count": n
            }

        # Generate unified diff before writing
        diff = ''.join(difflib.unified_diff(
            original_content.splitlines(keepends=True),
            updated_content.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}"
        ))

        # Write updated content
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(updated_content)

        return {
            "status": "success",
            "operation": "replace",
            "file": file_path,
            "matches_count": n,
            "message": f"Replaced {n} occurrence(s) in {file_path}",
            "diff": diff
        }

    except ValueError as e:
        return {
            "status": "error",
            "message": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error processing file: {str(e)}"
        }


def search_text(
    pattern: str,
    content: str,
    source_file_path: str | None = None,
    context_lines_before: int = 0,
    context_lines_after: int = 0
) -> list[MatchedConsecutiveLines]:
    """
    Search for a pattern in text content with context lines.

    :param pattern: Regex pattern to search for
    :param content: The text content to search
    :param source_file_path: Optional path to the source file
    :param context_lines_before: Number of context lines to include before matches
    :param context_lines_after: Number of context lines to include after matches
    :return: List of MatchedConsecutiveLines objects
    """
    matches = []
    lines = content.splitlines()
    total_lines = len(lines)

    # Use DOTALL flag to make '.' match newlines for multiline patterns
    compiled_pattern = re.compile(pattern, re.DOTALL)

    # Search across the entire content as a single string
    for match in compiled_pattern.finditer(content):
        start_pos = match.start()
        end_pos = match.end()

        # Find the line numbers for the start and end positions
        start_line_num = content[:start_pos].count("\n")
        end_line_num = content[:end_pos].count("\n")

        # Calculate the range of lines to include in the context
        context_start = max(0, start_line_num - context_lines_before)
        context_end = min(total_lines - 1, end_line_num + context_lines_after)

        # Create TextLine objects for the context
        context_lines = []
        for i in range(context_start, context_end + 1):
            line_num = i
            if context_start <= line_num < start_line_num:
                match_type = LineType.BEFORE_MATCH
            elif end_line_num < line_num <= context_end:
                match_type = LineType.AFTER_MATCH
            else:
                match_type = LineType.MATCH

            context_lines.append(TextLine(
                line_number=line_num,
                line_content=lines[i] if i < len(lines) else "",
                match_type=match_type
            ))

        matches.append(MatchedConsecutiveLines(lines=context_lines, source_file_path=source_file_path))

    return matches


def search_in_file(
    file_path: str,
    pattern: str,
    context_lines: int = 3,
    encoding: str = "utf-8"
) -> dict:
    """
    Search for a pattern in a single file.

    :param file_path: Path to the file to search
    :param pattern: Regex pattern to search for
    :param context_lines: Number of context lines before and after each match
    :param encoding: File encoding (default: utf-8)
    :return: Dict with status and matches
    """
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()

        matches = search_text(
            pattern=pattern,
            content=content,
            source_file_path=file_path,
            context_lines_before=context_lines,
            context_lines_after=context_lines
        )

        return {
            "status": "success",
            "operation": "search",
            "file": file_path,
            "matches_count": len(matches),
            "matches": [match.to_dict() for match in matches]
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error searching file: {str(e)}"
        }


def expand_braces(pattern: str) -> list[str]:
    """
    Expands brace patterns in a glob string.
    Example: "**/*.{js,jsx,ts,tsx}" becomes ["**/*.js", "**/*.jsx", "**/*.ts", "**/*.tsx"]
    """
    patterns = [pattern]
    while any("{" in p for p in patterns):
        new_patterns = []
        for p in patterns:
            match = re.search(r"\{([^{}]+)\}", p)
            if match:
                prefix = p[:match.start()]
                suffix = p[match.end():]
                options = match.group(1).split(",")
                for option in options:
                    new_patterns.append(f"{prefix}{option}{suffix}")
            else:
                new_patterns.append(p)
        patterns = new_patterns
    return patterns


def glob_match(pattern: str, path: str) -> bool:
    """
    Match a file path against a glob pattern.
    Supports *, **, ?, [seq], and brace expansion {a,b,c}.
    """
    pattern = pattern.replace("\\", "/")
    path = path.replace("\\", "/")

    # Handle ** patterns that should match zero or more directories
    if "**" in pattern:
        # Method 1: Standard fnmatch (matches one or more directories)
        regex1 = fnmatch.translate(pattern)
        if re.match(regex1, path):
            return True

        # Method 2: Handle zero-directory case by removing /** entirely
        if "/**/" in pattern:
            zero_dir_pattern = pattern.replace("/**/", "/")
            regex2 = fnmatch.translate(zero_dir_pattern)
            if re.match(regex2, path):
                return True

        # Method 3: Handle leading ** case by removing **/
        if pattern.startswith("**/"):
            zero_dir_pattern = pattern[3:]
            regex3 = fnmatch.translate(zero_dir_pattern)
            if re.match(regex3, path):
                return True

        return False
    else:
        return fnmatch.fnmatch(path, pattern)


def search_in_files(
    pattern: str,
    root_path: str = ".",
    include_glob: str = "",
    exclude_glob: str = "",
    context_lines: int = 0,
    encoding: str = "utf-8"
) -> dict:
    """
    Search for a pattern across multiple files.

    :param pattern: Regex pattern to search for
    :param root_path: Root directory to search in
    :param include_glob: Glob pattern to include files (e.g., "*.py", "src/**/*.ts")
    :param exclude_glob: Glob pattern to exclude files (e.g., "*test*", "**/*_generated.py")
    :param context_lines: Number of context lines before and after each match
    :param encoding: File encoding (default: utf-8)
    :return: Dict with status and matches across all files
    """
    try:
        # Collect all files
        all_files = []
        for root, dirs, files in os.walk(root_path):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, root_path)
                all_files.append(rel_path)

        # Filter files using glob patterns
        include_patterns = expand_braces(include_glob) if include_glob else None
        exclude_patterns = expand_braces(exclude_glob) if exclude_glob else None

        filtered_files = []
        for rel_path in all_files:
            if include_patterns:
                if not any(glob_match(p, rel_path) for p in include_patterns):
                    continue

            if exclude_patterns:
                if any(glob_match(p, rel_path) for p in exclude_patterns):
                    continue

            filtered_files.append(rel_path)

        # Search in each file
        all_matches = []
        files_with_matches = []

        for rel_path in filtered_files:
            abs_path = os.path.join(root_path, rel_path)
            try:
                with open(abs_path, 'r', encoding=encoding) as f:
                    content = f.read()

                matches = search_text(
                    pattern=pattern,
                    content=content,
                    source_file_path=rel_path,
                    context_lines_before=context_lines,
                    context_lines_after=context_lines
                )

                if matches:
                    files_with_matches.append(rel_path)
                    all_matches.extend([match.to_dict() for match in matches])

            except Exception:
                # Skip files that can't be read
                continue

        return {
            "status": "success",
            "operation": "search-files",
            "root_path": root_path,
            "files_searched": len(filtered_files),
            "files_with_matches": len(files_with_matches),
            "total_matches": len(all_matches),
            "matches": all_matches
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error searching files: {str(e)}"
        }


def validate_pattern(pattern: str) -> dict:
    """
    Validate that a regex pattern is valid.

    :param pattern: Regex pattern to validate
    :return: Dict with status and validation result
    """
    try:
        re.compile(pattern, re.DOTALL | re.MULTILINE)
        return {
            "status": "success",
            "message": "Pattern is valid",
            "pattern": pattern
        }
    except re.error as e:
        return {
            "status": "error",
            "message": f"Invalid regex pattern: {str(e)}",
            "pattern": pattern
        }


def main():
    """CLI interface for the regex editing tool."""
    parser = argparse.ArgumentParser(
        description="Token-efficient regex file editing tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Replace pattern in file
  %(prog)s replace main.py "console\\.error" "console.log" --mode=regex

  # Search for pattern in file
  %(prog)s search main.py "TODO.*" --context=3

  # Search across multiple files
  %(prog)s search-files "API_KEY" --include="**/*.py" --exclude="**/test_*"

  # Validate regex pattern
  %(prog)s validate "catch \\(error\\) \\{.*?\\}"
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Replace command
    replace_parser = subparsers.add_parser('replace', help='Replace pattern in file')
    replace_parser.add_argument('file', help='File to edit')
    replace_parser.add_argument('pattern', help='Pattern to search for')
    replace_parser.add_argument('replacement', help='Replacement text (use $!1, $!2 for backreferences)')
    replace_parser.add_argument('--mode', choices=['literal', 'regex'], default='regex',
                                help='Matching mode (default: regex)')
    replace_parser.add_argument('--allow-multiple', action='store_true',
                                help='Allow replacing multiple occurrences')
    replace_parser.add_argument('--encoding', default='utf-8', help='File encoding (default: utf-8)')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search for pattern in file')
    search_parser.add_argument('file', help='File to search')
    search_parser.add_argument('pattern', help='Regex pattern to search for')
    search_parser.add_argument('--context', type=int, default=3,
                               help='Number of context lines before/after match (default: 3)')
    search_parser.add_argument('--encoding', default='utf-8', help='File encoding (default: utf-8)')

    # Search-files command
    search_files_parser = subparsers.add_parser('search-files', help='Search for pattern across files')
    search_files_parser.add_argument('pattern', help='Regex pattern to search for')
    search_files_parser.add_argument('--root', default='.', help='Root directory to search (default: .)')
    search_files_parser.add_argument('--include', default='', help='Glob pattern to include files')
    search_files_parser.add_argument('--exclude', default='', help='Glob pattern to exclude files')
    search_files_parser.add_argument('--context', type=int, default=0,
                                     help='Number of context lines before/after match (default: 0)')
    search_files_parser.add_argument('--encoding', default='utf-8', help='File encoding (default: utf-8)')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate regex pattern')
    validate_parser.add_argument('pattern', help='Regex pattern to validate')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    result = None
    if args.command == 'replace':
        result = replace_in_file(
            file_path=args.file,
            needle=args.pattern,
            repl=args.replacement,
            mode=args.mode,
            allow_multiple_occurrences=args.allow_multiple,
            encoding=args.encoding
        )
    elif args.command == 'search':
        result = search_in_file(
            file_path=args.file,
            pattern=args.pattern,
            context_lines=args.context,
            encoding=args.encoding
        )
    elif args.command == 'search-files':
        result = search_in_files(
            pattern=args.pattern,
            root_path=args.root,
            include_glob=args.include,
            exclude_glob=args.exclude,
            context_lines=args.context,
            encoding=args.encoding
        )
    elif args.command == 'validate':
        result = validate_pattern(args.pattern)

    # Output JSON result
    print(json.dumps(result, indent=2))

    # Exit with appropriate code
    sys.exit(0 if result.get('status') == 'success' else 1)


if __name__ == '__main__':
    main()
