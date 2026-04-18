# lean-ctx: Dynamic Prompt & Hook Extraction

**Date:** 2026-04-18  
**Commit:** `bbaf0e5`  
**Status:** Complete  

## Problem

The lean-ctx launcher module used a hardcoded `tool-preference.md` prompt file and a static hook definition. When lean-ctx upgrades (e.g., from 8 → 10 compression modes, or adding `redirect` hooks alongside `rewrite`), the launcher drifts out of sync and must be manually updated.

## Solution

Replace hardcoded artifacts with dynamic extraction from lean-ctx's own `setup` command, run in a sandboxed HOME directory.

### How It Works

1. **Sandbox HOME** (`~/.cache/claude-launcher/lean-ctx-home/`) — already existed for MCP isolation
2. **`lean-ctx setup`** runs non-interactively (`stdin=DEVNULL`) in the sandbox, which writes:
   - `$SANDBOX/.claude/rules/lean-ctx.md` — the rules/prompt fragment
   - `$SANDBOX/.claude/settings.json` — hooks configuration (both `rewrite` and `redirect`)
3. **`build_prompt()`** reads the rules file and returns its content
4. **`build_hooks()`** reads settings.json and extracts the `"hooks"` key
5. **Failure mode:** warn to stderr, return empty string/dict — no hardcoded fallback

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Failure strategy | Warn + empty (no fallback) | Avoids silent drift; user sees warning |
| Setup idempotency | Module-level `_setup_done` flag | Runs once per launcher session |
| Non-interactive detection | lean-ctx auto-detects non-TTY stdin | No special flags needed |
| Sandbox safety | Skip setup if sandbox falls back to real HOME | Never run setup against user's actual home |

## Files Changed

| File | Change |
|------|--------|
| `launcher/modules/lean_ctx_mcp/module.py` | Added `_run_lean_ctx_setup()`, `_ensure_lean_ctx_setup()`; rewrote `build_prompt()` and `build_hooks()` to read from sandbox |
| `launcher/modules/lean_ctx_mcp/prompts/tool-preference.md` | **Deleted** — no longer needed |
| `launcher/tests/test_lean_ctx_module.py` | Rewritten: 41 tests covering setup runner, dynamic prompt/hook extraction, failure modes, warnings |

## Test Results

- **41/41 lean-ctx module tests passed**
- **137/141 full suite passed** (4 pre-existing failures in unrelated `test_memory_module.py` — GitHub credential issue)

## Technical Notes

- lean-ctx `setup` in non-interactive mode: detected via `crate::shell::is_non_interactive()` in `setup.rs`, triggers `run_setup_with_options` with `non_interactive: true, yes: true`
- Rules injection: `inject_all_rules(&home)` writes `RULES_DEDICATED` (v9) to `$HOME/.claude/rules/lean-ctx.md`
- Hooks injection: `install_claude_hook_config(&home)` writes both `rewrite` AND `redirect` PreToolUse hooks to `$HOME/.claude/settings.json`
- Previous code only had the `Bash` rewrite hook; dynamic extraction now picks up the `Read|Grep|ListFiles` redirect hook automatically
