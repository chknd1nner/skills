"""Claude Code Launcher — modular TUI launcher with system prompt assembly."""

import importlib
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from launcher.config import parse_env, load_state, save_state
from launcher.prompt_builder import assemble_prompt

MODULES_DIR = Path(__file__).parent / "modules"
STATE_FILENAME = ".claude-launcher-state.json"

INTERCEPT_FLAGS = {
    "--append-system-prompt",
    "--append-system-prompt-file",
}


def parse_args(argv: list) -> dict:
    user_appends = []
    passthrough = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--append-system-prompt" and i + 1 < len(argv):
            user_appends.append(argv[i + 1])
            i += 2
        elif arg == "--append-system-prompt-file" and i + 1 < len(argv):
            user_appends.append(f"file:{argv[i + 1]}")
            i += 2
        else:
            passthrough.append(arg)
            i += 1

    return {
        "user_appends": user_appends,
        "passthrough": passthrough,
    }
