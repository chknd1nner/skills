# Gemini Review Hook for Superpowers — Design Spec

> **Last updated:** 2026-03-28 — Python rewrite, policy file fix, timeout support, quota findings.
> This is a living document. If source code were lost, this spec should be sufficient to recreate it.

## Overview

A project-scoped (or globally scoped depending on user preference) Claude Code hook that intercepts review-type Agent calls made by the Superpowers plugin and routes them to Gemini CLI instead of spawning a Claude subagent. This distributes review workload across both Claude Pro and Gemini Pro subscriptions, and provides genuine cross-model review as a secondary benefit.

The mechanism is entirely hook-based. No superpowers skill files are modified, so it survives upstream version updates.

---

## Problem

The superpowers workflow dispatches several Claude subagents as reviewers throughout the development lifecycle: spec compliance reviewers, plan reviewers, code quality reviewers, and the explicit `superpowers:code-reviewer`. These all consume Claude Pro capacity. They are also good candidates for cross-model review — a second model catching issues the first missed.

---

## Approach

A `PreToolUse` hook fires on every `Agent` tool call. The hook detects whether the call is a review-type dispatch. If so, it runs the review via Gemini CLI instead, returns Gemini's output as the denial reason (prefixed with an instruction to Claude to treat it as the real result), and blocks the original Agent call. If Gemini fails, times out, or returns empty output, the hook falls through and the real Agent call proceeds.

---

## Components

Four files:

**`.claude/settings.json`** (project) or **`~/.claude/settings.json`** (global) — registers the hook at the user's preferred scope.

**`.claude/hooks/intercept-review-agents.py`** — the hook script (Python): detection, Gemini invocation, result delivery, fallback. Replaces the original bash implementation.

**`.claude/hooks/gemini-review-policy.toml`** — project-scoped Gemini CLI policy that enforces reviewer separation of duties (see Gemini Invocation below).

**`.claude/hooks/archive/intercept-review-agents.sh`** — archived original bash implementation, retained for reference.

---

## Detection

Two patterns cover all superpowers review calls:

| Pattern | Source |
|---|---|
| `subagent_type == "superpowers:code-reviewer"` | `requesting-code-review` skill, code quality reviewer in `subagent-driven-development` |
| `subagent_type == "general-purpose"` AND `description.lower().startswith("review")` | Spec document reviewer (`brainstorming`), plan document reviewer (`writing-plans`), spec compliance reviewer (`subagent-driven-development`) |

All other Agent calls pass through untouched.

The `description` field (not `prompt`) is used for the general-purpose pattern — it is always present, short, and human-written. The `startswith("review")` match (case-insensitive) is tight enough to avoid false positives against Explore agents, implementer agents, and other general-purpose dispatches.

---

## Hook Script: intercept-review-agents.py

Python 3, stdlib only (`subprocess`, `json`, `sys`, `os`, `logging`). No pip dependencies.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_DEBUG` | `0` | Set to `1` to enable debug logging |
| `GEMINI_LOG_FILE` | `/tmp/gemini-hook-debug.log` | Log file path (useful for isolated test logging) |
| `GEMINI_REVIEW_MODEL` | *(none)* | Override Gemini model (e.g. `gemini-2.0-flash`). Default uses Gemini Auto. |
| `GEMINI_TIMEOUT` | `120` | Seconds before killing Gemini and falling back to Claude agent. Must be a positive integer; invalid values default to 120. |

### Input

JSON on stdin — the standard Claude Code PreToolUse hook payload:

```json
{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "superpowers:code-reviewer",
    "description": "Review implementation of Task 3",
    "prompt": "..."
  },
  "cwd": "/abs/path/to/project"
}
```

### Output on pass-through

Exit 0, no stdout. Claude Code proceeds with the original Agent call.

### Output on interception (success)

Exit 0, valid JSON to stdout:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "<prefix>\n\n[GEMINI REVIEW]\n\n---\n\n<gemini_stdout>"
  }
}
```

The prefix is: `"A PreToolUse hook intercepted your review agent call and redirected it to Gemini CLI. The following is Gemini's complete review. Continue the workflow as normal."`

`json.dumps` is used to build the JSON. This correctly escapes all control characters (including any ANSI codes) without requiring external tooling. The original bash implementation used `jq -n --arg` which is also correct, but `json.dumps` in Python is more explicit and portable.

### Fallback chain

The hook exits 0 with no stdout (allowing the real Agent to run) in any of these conditions:

1. Not a review call (pass-through at detection)
2. `gemini` binary not found on `PATH` (`FileNotFoundError`)
3. Gemini exits non-zero
4. Gemini output is empty or whitespace-only
5. `subprocess.TimeoutExpired` — Gemini exceeded `GEMINI_TIMEOUT` seconds

Reviews always happen — the fallback guarantees it.

---

## Gemini Invocation

```python
cmd = [
    'gemini',
    '-p', 'Perform the review task described in the input above.',
    '--approval-mode', 'yolo',
    '--policy', os.path.join(cwd, '.claude', 'hooks', 'gemini-review-policy.toml'),
    '--include-directories', cwd,
    '-o', 'text',
]
if model:  # GEMINI_REVIEW_MODEL
    cmd.extend(['-m', model])

result = subprocess.run(
    cmd,
    input=prompt,          # agent's prompt piped to stdin
    capture_output=True,   # stdout captured, stderr captured (not discarded)
    text=True,
    timeout=timeout,       # GEMINI_TIMEOUT, default 120
)
```

**`cwd` from hook input JSON** — more reliable than `os.getcwd()`, which may differ for the hook subprocess.

**Stdin carries the prompt; `-p` provides the trailing instruction** — together they form the complete request. This pattern is explicitly documented in the Gemini CLI headless reference.

**`--approval-mode yolo --policy "$CWD/.claude/hooks/gemini-review-policy.toml"`** — yolo mode allows Gemini full read and explore access (files, `git diff`, grep, shell commands) without prompting. The project-scoped policy file enforces reviewer separation of duties by explicitly denying `write_file`, `replace`, and destructive git commands. **The `--policy` flag loads a specific file per-invocation, independent of the global `~/.gemini/policies/` directory.** This is the correct mechanism for per-agent policies in headless mode.

**`--include-directories "$CWD"`** — scopes Gemini's filesystem access to the project workspace.

**`-o text`** — clean text output, no JSON wrapping. Confirmed: Gemini's stdout with this flag contains no ANSI escape codes. ANSI/status output goes to stderr (Gemini's internal progress indicators, "Loaded cached credentials.", tool invocation messages). Stderr is captured but not injected into the review output.

**`capture_output=True` (not `2>/dev/null`)** — stderr is captured rather than discarded. When `GEMINI_DEBUG=1` is set, stderr is logged to `GEMINI_LOG_FILE`. This enables diagnosis of policy file errors and rate limit messages without polluting the review response delivered to Claude.

**No `-m` flag by default** — Gemini CLI's Auto mode selects the model based on prompt complexity. Review tasks are complex; Auto routes to the pro tier. `GEMINI_REVIEW_MODEL` overrides this for testing or quota management.

---

## Policy File: gemini-review-policy.toml

```toml
# Block file write operations
[[rule]]
toolName = ["write_file", "replace"]
decision = "deny"
priority = 100
denyMessage = "Write operations are blocked during code review."

# Block destructive git commands
[[rule]]
toolName = "run_shell_command"
commandPrefix = ["git commit", "git push", "git checkout", "git reset", "git rebase", "git rm", "git clean", "git merge", "git tag"]
decision = "deny"
priority = 100
denyMessage = "Destructive git operations are blocked during code review."
```

**Key constraint:** `commandPrefix` rules **must** include `toolName = "run_shell_command"`. Without this, Gemini reports a policy file error on every invocation and the deny rules are silently not applied (Gemini continues in yolo mode without restrictions). Both `toolName` and `commandPrefix` support arrays.

---

## Result Delivery

Gemini's stdout is embedded in the `permissionDecisionReason` field. Claude reads this field as the reason an Agent call was blocked. The prefix instructs Claude to treat the content as a complete review result and continue the workflow normally.

Verified in testing: Claude reads this framing correctly and continues the workflow without stalling.

---

## Settings Configuration

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "<absolute-path-to-project>/.claude/hooks/intercept-review-agents.py"
          }
        ]
      }
    ]
  }
}
```

The `command` value must be an absolute path. Scoped to this project only via `.claude/settings.json`. Can be promoted to `~/.claude/settings.json` for global coverage.

**Note on disabling during development:** When developing or debugging the hook itself, temporarily remove the Agent PreToolUse matcher from `settings.json`. This prevents the hook from intercepting the code quality reviews that are part of the development workflow.

---

## Debugging

Enable with `GEMINI_DEBUG=1` (can be set in `settings.local.json` under the `"env"` key for session-wide activation):

```json
{
  "env": {
    "GEMINI_DEBUG": "1"
  }
}
```

Log entries written to `GEMINI_LOG_FILE` (default `/tmp/gemini-hook-debug.log`):

```
[2026-03-28T22:05:37] intercepted | type=superpowers:code-reviewer | desc=Review implementation
[2026-03-28T22:05:58] gemini exit=0 | output_bytes=19 | control_chars=0
[2026-03-28T22:05:58] gemini stderr: YOLO mode is enabled...
[2026-03-28T22:05:58] jq SUCCESS | json_bytes=347
```

`GEMINI_LOG_FILE` can be set to an isolated path per test run, avoiding conflicts between parallel invocations.

---

## Test Suite

**`.claude/hooks/test_intercept_review_agents.py`** — 17 tests, pytest.

| Group | Tests | What's covered |
|---|---|---|
| Detection | 6 | Pass-through cases, both interception patterns, case-insensitivity |
| Fallback chain | 4 | Non-zero exit, empty output, whitespace output, timeout |
| Output validation | 4 | JSON structure, ANSI codes in output, model override flag, debug logging |
| Error handling | 3 | Missing gemini binary, invalid GEMINI_TIMEOUT, zero GEMINI_TIMEOUT |

Uses a `fake_gemini` pytest fixture (factory pattern) that creates a controlled bash binary shadowing the real `gemini` on `PATH`. Tests are fast (no real Gemini calls) and deterministic.

Run: `python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v`

---

## Gemini CLI Quota — Known Constraints

**Important for production use.** The Gemini CLI (when authenticated via OAuth/PKCE "Login with Google") uses the **Gemini Code Assist API**, which is a completely separate quota pool from the web chat at gemini.google.com. Exhausting CLI quota does not affect web chat and vice versa.

For a **Gemini Pro subscriber** authenticated via OAuth:
- 1,500 API calls/day total, **shared with Code Assist IDE agent mode** (VS Code, JetBrains)
- The Pro model (gemini-2.5-pro) has a separate undocumented sub-limit within the daily total — lower and variable
- Agentic yolo sessions (reading files, running git diff) consume 50–100 API calls per review — not one
- In practice, Pro model capacity can exhaust in 2–3 hours of agentic use

**The "exhausted your capacity" error may be transient.** A confirmed bug in Gemini CLI (Issue #18050) misclassifies transient 429 "server busy" responses as daily quota exhaustion. If this fires, Gemini retries internally with exponential backoff (11s, 21s, 35s, ...) — this is what caused observed 10+ minute hook hangs. The `GEMINI_TIMEOUT` fallback is the correct mitigation.

**Recommended:** Set `GEMINI_TIMEOUT` to a value that cuts off the retry loop before it blocks the development workflow (120s default should be sufficient for most cases).

---

## Out of Scope

- **Model mapping** — mapping Claude model tiers (Opus/Sonnet/Haiku) to Gemini equivalents is not implemented. Auto mode is sufficient for the review use case; the reviewer should always use the best available model.
- **Routing by review type** — all review call types are handled identically. Differentiating between spec, plan, and code reviews (e.g. to pass different system prompts) is a future option.
