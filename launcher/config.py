"""Config discovery and state management for the launcher."""

import json
import os
from typing import Optional


def parse_env(path: Optional[str]) -> dict:
    """Parse a .env file into a dict of key-value pairs.

    Skips blank lines and lines starting with #.
    Returns empty dict if file doesn't exist or path is None.
    """
    if not path or not os.path.exists(path):
        return {}

    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                env[key.strip()] = val.strip()
    return env
