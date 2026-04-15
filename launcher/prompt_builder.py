"""Prompt builder — assembles module fragments into a temp file for --append-system-prompt-file."""

import json
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


def write_mcp_config(config: dict) -> str:
    """Write MCP config to temp file, return path.

    Args:
        config: dict with mcpServers key

    Returns:
        Path to temp JSON file
    """
    fd, path = tempfile.mkstemp(suffix=".json", prefix="claude-mcp-")
    with os.fdopen(fd, "w") as f:
        json.dump(config, f, indent=2)

    return path


def write_settings_config(config: dict) -> str:
    """Write settings fragment to temp file, return path.

    Args:
        config: settings.json-shaped dict (e.g. with 'hooks' key)

    Returns:
        Path to temp JSON file
    """
    fd, path = tempfile.mkstemp(suffix=".json", prefix="claude-settings-")
    with os.fdopen(fd, "w") as f:
        json.dump(config, f, indent=2)

    return path


def merge_settings(settings_list: list[dict]) -> dict:
    """Deep merge a list of settings dicts.

    Dicts are recursively merged. Lists are concatenated.
    Scalar conflicts: later value wins.

    Args:
        settings_list: list of settings fragments from modules

    Returns:
        Single merged settings dict
    """
    merged: dict = {}
    for settings in settings_list:
        _deep_merge(merged, settings)
    return merged


def _deep_merge(base: dict, overlay: dict) -> None:
    """Mutate base by merging overlay into it."""
    for key, value in overlay.items():
        if key in base:
            if isinstance(base[key], dict) and isinstance(value, dict):
                _deep_merge(base[key], value)
            elif isinstance(base[key], list) and isinstance(value, list):
                base[key].extend(value)
            else:
                base[key] = value
        else:
            base[key] = value
