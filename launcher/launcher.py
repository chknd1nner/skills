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


def discover_modules(env: dict) -> list:
    available = []

    if not MODULES_DIR.exists():
        return available

    for entry in sorted(MODULES_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue

        module_file = entry / "module.py"
        if not module_file.exists():
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                f"launcher.modules.{entry.name}.module",
                str(module_file),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "check_dependencies"):
                continue

            result = mod.check_dependencies(env)
            if result.get("available"):
                available.append({
                    "name": result["name"],
                    "module": mod,
                })
        except Exception:
            continue

    return available
