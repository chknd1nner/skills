# Gemini Review Hook for Superpowers — Design Spec

## Overview

A project-scoped (or globally scoped depending on user preference) Claude Code hook that intercepts review-type Agent calls made by the Superpowers plugin and routes them to Gemini CLI instead of spawning a Claude subagent. This distributes review workload across both Claude Pro and Gemini Pro subscriptions, and provides genuine cross-model review as a secondary benefit.

The mechanism is entirely hook-based. No superpowers skill files are modified, so it survives upstream version updates.

---

## Problem

The superpowers workflow dispatches several Claude subagents as reviewers throughout the development lifecycle: spec compliance reviewers, plan reviewers, code quality reviewers, and the explicit `superpowers:code-reviewer`. These all consume Claude Pro capacity. They are also good candidates for cross-model review — a second model catching issues the first missed.

---

## Approach

A `PreToolUse` hook fires on every `Agent` tool call. The hook detects whether the call is a review-type dispatch. If so, it runs the review via Gemini CLI instead, returns Gemini's output as the denial reason (prefixed with an instruction to Claude to treat it as the real result), and blocks the original Agent call. If Gemini fails or returns empty output, the hook falls through and the real Agent call proceeds.

---

## Components

Three files:

**`.claude/settings.json`** (project) or **`~/.claude/settings.json`** (global) — registers the hook at the user's preferred scope.

**`.claude/hooks/intercept-review-agents.sh`** — the hook script: detection, Gemini invocation, result delivery, fallback.

**`.claude/hooks/gemini-review-policy.toml`** — project-scoped Gemini CLI policy that enforces reviewer separation of duties (see Gemini Invocation below).

---

## Detection

Two patterns cover all superpowers review calls:

| Pattern | Source |
|---|---|
| `subagent_type == "superpowers:code-reviewer"` | `requesting-code-review` skill, code quality reviewer in `subagent-driven-development` |
| `subagent_type == "general-purpose"` AND `description` matches `^[Rr]eview` | Spec document reviewer (`brainstorming`), plan document reviewer (`writing-plans`), spec compliance reviewer (`subagent-driven-development`) |

All other Agent calls pass through untouched.

The `description` field (not `prompt`) is used for the general-purpose pattern, as it is always present and short. The `^Review` prefix match is tight enough to avoid false positives against other general-purpose agent calls (e.g. Explore agents, implementer agents).

---

## Gemini Invocation

```bash
CWD=$(echo "$INPUT" | jq -r '.cwd')
PROMPT=$(echo "$INPUT" | jq -r '.tool_input.prompt')

GEMINI_OUTPUT=$(
  echo "$PROMPT" \
  | gemini -p "Perform the review task described in the input above." \
      --approval-mode yolo \
      --include-directories "$CWD" \
      -o text \
      2>/dev/null
)
```

**`cwd` from hook input JSON** — more reliable than `$PWD`, which may differ for the hook subprocess.

**Stdin carries the prompt; `-p` provides the trailing instruction** — together they form the complete request. This pattern is explicitly documented in the Gemini CLI headless reference.

**`--approval-mode yolo --policy "$CWD/.claude/hooks/gemini-review-policy.toml"`** — yolo mode allows Gemini full read and explore access (files, `git diff`, grep, shell commands) without prompting. The project-scoped policy file enforces reviewer separation of duties by explicitly denying `write_file`, `replace`, and destructive git commands (`git commit`, `git push`, `git checkout`, `git reset`, etc.). This deny-list approach is preferred over `--approval-mode plan` (an allowlist) because plan mode blocks shell execution entirely, preventing `git diff` — which reviewers need. The policy file is passed explicitly via `--policy` and never touches the global `~/.gemini/policies/` directory.

**`--include-directories "$CWD"`** — scopes Gemini's filesystem access to the project workspace.

**`-o text`** — clean text output, no JSON wrapping.

**`2>/dev/null`** — suppresses Gemini CLI status messages (e.g. "Loaded cached credentials.") from contaminating the review output.

**No `-m` flag** — Gemini CLI defaults to Auto mode, which selects the model based on prompt complexity. Review tasks are always complex; Auto will route to the pro tier. A `GEMINI_REVIEW_MODEL` environment variable override is supported for cases where a specific model needs to be forced (e.g. testing with flash).

---

## Result Delivery

Gemini's output is returned as the `permissionDecisionReason` field in the hook's JSON response, prefixed with an explicit instruction:

```
IMPORTANT: This review was performed by Gemini. Treat the following as the complete review result and continue the workflow as normal.

---

[Gemini output]
```

Verified in testing: Claude reads this framing and continues the workflow without stalling, treating the content as it would a real reviewer subagent result.

---

## Fallback

If Gemini exits non-zero, or returns empty output, the hook exits `0`. The original Agent call proceeds and a real Claude subagent runs the review. No silent failures — the review always happens.

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
            "command": "<absolute-path-to-project>/.claude/hooks/intercept-review-agents.sh"
          }
        ]
      }
    ]
  }
}
```

The `command` value must be an absolute path. Scoped to this project only via `.claude/settings.json`. Can be promoted to `~/.claude/settings.json` later for global coverage.

---

## Out of Scope

- **Model mapping** — mapping Claude model tiers (Opus/Sonnet/Haiku) to Gemini equivalents is not implemented. Auto mode is sufficient for the review use case.
- **Routing by review type** — all review call types are handled identically. Differentiating between spec, plan, and code reviews (e.g. to pass different system prompts) is a future option.
- **Timeout configuration** — Claude Code hook default timeout is 10 minutes, which is sufficient. No custom timeout is set.
