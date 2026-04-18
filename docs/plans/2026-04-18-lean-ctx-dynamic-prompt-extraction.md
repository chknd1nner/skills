# lean-ctx: Dynamic Prompt & Hook Extraction

**Date:** 2026-04-18  
**Commit:** `bbaf0e5` (+ follow-up fix)
**Status:** Complete (with two corrections — see Correction sections below)

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

## Correction (2026-04-18, post-ship)

### Faulty premise
The original implementation called `lean-ctx setup` non-interactively, assuming it would write `.claude/rules/lean-ctx.md` and `.claude/settings.json`. It does not.

Verified empirically against lean-ctx 3.2.3 in a fresh sandbox HOME with `stdin=DEVNULL`:

| Command | Writes rules | Writes settings.json + hook scripts |
|---------|:---:|:---:|
| `lean-ctx setup` (non-interactive) | ❌ | ❌ |
| `lean-ctx init --agent claude` | ✅ | ✅ |

In non-interactive mode, `setup` runs only the shell-alias install step; the agent-install step (which produces the files the launcher reads) is silently skipped. `init --agent claude` is the command that actually performs the agent install and is documented as "Configure MCP for specific editor/agent".

### Symptom
Launcher emitted both warnings:
- `Warning: lean-ctx setup did not produce a rules file; no prompt fragment injected`
- `Warning: lean-ctx setup did not produce a settings file; no hooks injected`

Pre-existing stale `rules/lean-ctx.md` in the sandbox (from earlier interactive runs) occasionally masked the rules half of the bug; `settings.json` was never produced so the hooks warning always fired on a fresh sandbox.

### Fix
`_run_lean_ctx_setup()` now invokes `[binary, "init", "--agent", "claude"]` instead of `[binary, "setup"]`. Everything else in the pipeline (sandbox HOME, idempotency flag, file reads, failure handling) is unchanged.

### Verification
- 41/41 lean-ctx module tests pass (test updated to assert the new argv)
- End-to-end with sandbox `.claude/` wiped: `build_prompt()` returns 1467 chars, `build_hooks()` returns `{'hooks': {'PreToolUse': ...}}`

## Second Correction (2026-04-18, post-ship)

### Faulty premise
The first correction switched from `setup` to `init --agent claude` on the assumption that the HOME override alone would contain all writes. It does not.

`lean-ctx init --agent claude` writes **two categories** of files:

| Category | Location | Sandboxed by `HOME=`? |
|----------|----------|:---:|
| Home-level rules/hooks | `$HOME/.claude/rules/lean-ctx.md`, `$HOME/.claude/settings.json`, `$HOME/.claude/hooks/` | ✅ |
| Project-level agent files | `./AGENTS.md`, `./LEAN-CTX.md`, `./.cursorrules`, `./.claude/rules/lean-ctx.md` | ❌ — written to CWD |

### Symptom
Launching from the skills repo left four untracked artifacts scattered in the project root: `AGENTS.md`, `LEAN-CTX.md`, `.cursorrules`, and a fresh `.claude/rules/` directory. The sandbox caught the home-level writes but `subprocess.run` inherited the launcher's CWD, so init wrote project files into the repo instead.

### Fix
`_run_lean_ctx_setup()` now passes `cwd=str(sandbox_home)` to `subprocess.run`, so both categories of writes land inside the sandbox. Test updated to assert the new kwarg.

### Verification
- 41/41 lean-ctx module tests pass
- Leaked files (`AGENTS.md`, `LEAN-CTX.md`, `.cursorrules`, `.claude/rules/`) removed from the repo
- Prompt injection confirmed working end-to-end: the lean-ctx rules block appears in the session system prompt
