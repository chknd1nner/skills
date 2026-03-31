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

# Flags that the launcher intercepts and merges into the temp file
INTERCEPT_FLAGS = {
    "--append-system-prompt",
    "--append-system-prompt-file",
}


def parse_args(argv: list) -> dict:
    """Separate intercepted flags from passthrough flags.

    Intercepts --append-system-prompt and --append-system-prompt-file,
    collects their values as user_appends. Everything else passes through.

    Args:
        argv: command-line arguments (not including the launcher script itself)

    Returns:
        dict with 'user_appends' (list[str]) and 'passthrough' (list[str])
    """
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
    """Scan modules/ directory and return modules whose dependencies are met.

    Each module directory must contain a module.py with check_dependencies().

    Args:
        env: parsed .env contents

    Returns:
        list of dicts with 'name', 'module' (imported module object)
    """
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


def build_tui_choices(modules: list, env: dict, saved_state: dict) -> list:
    """Build the full TUI choice list from all available modules.

    Args:
        modules: list from discover_modules()
        env: parsed .env contents
        saved_state: full state dict from state file

    Returns:
        list of dicts, each module's TUI items with module_name attached
    """
    all_items = []
    for mod_info in modules:
        mod = mod_info["module"]
        mod_name = mod_info["name"]
        mod_state = saved_state.get(mod_name.lower().replace(" ", "_"), {})

        if hasattr(mod, "build_tui_section"):
            items = mod.build_tui_section(env, mod_state)
            for item in items:
                item["module_name"] = mod_name
            all_items.extend(items)

    return all_items


def run_tui(all_items: list) -> dict:
    """Present the TUI and return user selections.

    Uses InquirerPy checkbox with separators for grouped flat list.

    Args:
        all_items: list of menu item dicts from build_tui_choices()

    Returns:
        dict mapping item keys to bool (selected or not)
    """
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator

    choices = []
    for item in all_items:
        if item.get("type") == "separator":
            choices.append(Separator(f"── {item['label']} ──"))
        else:
            choices.append(
                Choice(
                    value=item["key"],
                    name=item["label"],
                    enabled=item.get("default", True),
                )
            )

    if not choices:
        return {}

    selected = inquirer.checkbox(
        message="Configure launch options (↑↓ navigate, ␣ toggle, ⏎ launch):",
        choices=choices,
        instruction="",
    ).execute()

    all_keys = [item["key"] for item in all_items if item.get("type") != "separator"]
    return {key: (key in selected) for key in all_keys}


def selections_to_module_state(selections: dict, all_items: list) -> dict:
    """Convert flat TUI selections back to per-module state dicts.

    Args:
        selections: flat dict of key -> bool from run_tui()
        all_items: the items list (with module_name attached)

    Returns:
        dict keyed by module state name, e.g. {"memory_system": {"enabled": True, ...}}
    """
    module_states = {}
    for item in all_items:
        if item.get("type") == "separator":
            continue
        mod_key = item["module_name"].lower().replace(" ", "_")
        if mod_key not in module_states:
            module_states[mod_key] = {}

        key = item["key"]
        selected = selections.get(key, item.get("default", True))

        if key == "enabled":
            module_states[mod_key]["enabled"] = selected
        elif key.startswith("file:"):
            if "selected_files" not in module_states[mod_key]:
                module_states[mod_key]["selected_files"] = {}
            file_path = key[5:]
            module_states[mod_key]["selected_files"][file_path] = selected
        else:
            module_states[mod_key][key] = selected

    return module_states


def main():
    """Main entry point for the launcher."""
    # Step 1: Config discovery
    env_path = os.path.join(os.getcwd(), ".env")
    env = parse_env(env_path)

    # Launcher-level dependency: claude must be on PATH
    if not shutil.which("claude"):
        print("Error: 'claude' not found on PATH. Install Claude Code first.")
        sys.exit(1)

    # Step 2: Module discovery
    modules = discover_modules(env)

    # Step 3: TUI
    state_path = os.path.join(os.getcwd(), STATE_FILENAME)
    saved_state = load_state(state_path)

    all_items = build_tui_choices(modules, env, saved_state)
    selections = run_tui(all_items)

    if selections is None:
        sys.exit(0)

    # Step 4: Save selections
    module_states = selections_to_module_state(selections, all_items)
    # Merge with existing state to preserve stale module entries
    merged_state = {**saved_state, **module_states}
    save_state(state_path, merged_state)

    # Step 5: Build prompt fragments from enabled modules
    fragments = []
    for mod_info in modules:
        mod = mod_info["module"]
        mod_key = mod_info["name"].lower().replace(" ", "_")
        mod_state = module_states.get(mod_key, {})

        if not mod_state.get("enabled", False):
            continue

        if hasattr(mod, "build_prompt"):
            try:
                fragment = mod.build_prompt(env, mod_state)
                if fragment:
                    fragments.append(fragment)
            except Exception as e:
                print(f"Warning: {mod_info['name']} failed to build prompt: {e}")

    # Step 6: Parse user flags
    args = parse_args(sys.argv[1:])

    # Step 7: Assemble system prompt
    prompt_path = assemble_prompt(fragments, args["user_appends"])

    # Step 8: Launch claude
    claude_args = ["claude"]
    if prompt_path:
        claude_args.extend(["--append-system-prompt-file", prompt_path])
    claude_args.extend(args["passthrough"])

    print(f"Launching claude with {len(fragments)} module(s)...")
    os.execvp("claude", claude_args)


if __name__ == "__main__":
    main()
