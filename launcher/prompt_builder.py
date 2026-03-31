"""Prompt builder — assembles module fragments into a temp file for --append-system-prompt-file."""

import os
import tempfile
from typing import Optional


def assemble_prompt(
    fragments: list[str],
    user_appends: list[str],
) -> Optional[str]:
    """Concatenate module prompt fragments and user appends into a temp file.

    Args:
        fragments: list of prompt strings from modules (in order)
        user_appends: list of user-provided append content. Items prefixed
                      with 'file:' are read from disk; others are inline text.

    Returns:
        Path to temp file, or None if there's nothing to write.
    """
    parts = []

    # Module fragments
    for frag in fragments:
        if frag and frag.strip():
            parts.append(frag.strip())

    # User appends
    resolved_appends = []
    for append in user_appends:
        if append.startswith("file:"):
            filepath = append[5:]
            if os.path.exists(filepath):
                resolved_appends.append(open(filepath).read().strip())
        else:
            resolved_appends.append(append.strip())

    if resolved_appends:
        parts.append("---\n")
        parts.extend(resolved_appends)

    if not parts:
        return None

    # Write to temp file
    fd, path = tempfile.mkstemp(suffix=".md", prefix="claude-launcher-")
    with os.fdopen(fd, "w") as f:
        f.write("\n\n".join(parts))
        f.write("\n")

    return path
