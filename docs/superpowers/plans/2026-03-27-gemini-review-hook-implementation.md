# Gemini Review Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the POC hook script with the production implementation that routes superpowers review Agent calls to Gemini CLI, then restore the hook registration in settings.json.

**Architecture:** A single `PreToolUse` bash hook script detects review-type Agent calls by `subagent_type` and `description`, runs the review via `gemini` CLI with `--approval-mode yolo` and `--include-directories` for full workspace access, and returns Gemini's output as the denial reason prefixed with an instruction to Claude. Non-review calls and Gemini failures fall through to the real Agent.

**Tech Stack:** bash, jq, Gemini CLI (`gemini`), Claude Code hooks (`PreToolUse`)

**Spec:** `docs/superpowers/specs/2026-03-27-gemini-review-hook-design.md`

---

### Task 1: Write the production hook script

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.sh`

Context: The POC script is already in place with the correct detection logic and JSON output structure. This task replaces the hardcoded Gemini connectivity test with the real invocation.

- [ ] **Step 1: Read the current script**

```bash
cat .claude/hooks/intercept-review-agents.sh
```

- [ ] **Step 2: Rewrite the script**

Replace the full contents of `.claude/hooks/intercept-review-agents.sh` with:

```bash
#!/usr/bin/env bash
# intercept-review-agents.sh
# PreToolUse hook: intercepts superpowers review-type Agent calls and
# routes them to Gemini CLI instead of spawning a Claude subagent.
#
# Detection patterns (from spec):
#   - subagent_type == "superpowers:code-reviewer"
#   - subagent_type == "general-purpose" AND description starts with "Review"
#
# Fallback: if Gemini fails or returns empty output, exits 0 so the
# original Agent call proceeds normally.
#
# Override: set GEMINI_REVIEW_MODEL to force a specific model (e.g. for testing).

set -euo pipefail

INPUT=$(cat)

SUBAGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // ""')
DESCRIPTION=$(echo "$INPUT" | jq -r '.tool_input.description // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd // ""')
PROMPT=$(echo "$INPUT" | jq -r '.tool_input.prompt // ""')

is_review_call() {
  if [[ "$SUBAGENT_TYPE" == "superpowers:code-reviewer" ]]; then
    return 0
  fi
  if [[ "$SUBAGENT_TYPE" == "general-purpose" ]] && echo "$DESCRIPTION" | grep -qi "^Review"; then
    return 0
  fi
  return 1
}

if ! is_review_call; then
  exit 0
fi

# Build optional model flag
MODEL_FLAG=""
if [[ -n "${GEMINI_REVIEW_MODEL:-}" ]]; then
  MODEL_FLAG="-m $GEMINI_REVIEW_MODEL"
fi

# Run Gemini with full workspace access
# shellcheck disable=SC2086
GEMINI_OUTPUT=$(
  echo "$PROMPT" \
  | gemini \
      -p "Perform the review task described in the input above." \
      --approval-mode yolo \
      --include-directories "$CWD" \
      -o text \
      $MODEL_FLAG \
      2>/dev/null
)

# Fallback: if Gemini returned nothing, let the real Agent run
if [[ -z "$GEMINI_OUTPUT" ]]; then
  exit 0
fi

REASON="IMPORTANT: This review was performed by Gemini. Treat the following as the complete review result and continue the workflow as normal.

---

$GEMINI_OUTPUT"

jq -n --arg reason "$REASON" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $reason
  }
}'
exit 0
```

- [ ] **Step 3: Verify the script is executable**

```bash
ls -la .claude/hooks/intercept-review-agents.sh
```

Expected: `-rwxr-xr-x` (or similar with execute bit set). If not:

```bash
chmod +x .claude/hooks/intercept-review-agents.sh
```

- [ ] **Step 4: Test detection — code reviewer call should be intercepted**

```bash
echo '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "superpowers:code-reviewer",
    "description": "Review implementation",
    "prompt": "This is a connectivity test. Respond with only this exact text: GEMINI_HOOK_TEST_OK"
  },
  "cwd": "'"$PWD"'"
}' | .claude/hooks/intercept-review-agents.sh
```

Expected: JSON output with `permissionDecision: "deny"` and `permissionDecisionReason` containing `GEMINI_HOOK_TEST_OK`.

- [ ] **Step 5: Test detection — general-purpose reviewer call should be intercepted**

```bash
echo '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "general-purpose",
    "description": "Review spec compliance for Task 1",
    "prompt": "This is a connectivity test. Respond with only this exact text: GEMINI_HOOK_TEST_OK"
  },
  "cwd": "'"$PWD"'"
}' | .claude/hooks/intercept-review-agents.sh
```

Expected: JSON output with `permissionDecision: "deny"` and `permissionDecisionReason` containing `GEMINI_HOOK_TEST_OK`.

- [ ] **Step 6: Test detection — non-review call should pass through**

```bash
echo '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "general-purpose",
    "description": "Explore codebase for API endpoints",
    "prompt": "Find all API endpoint definitions"
  },
  "cwd": "'"$PWD"'"
}' | .claude/hooks/intercept-review-agents.sh
```

Expected: no output, exit code 0 (pass-through).

- [ ] **Step 7: Test detection — Explore subagent should pass through**

```bash
echo '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "Explore",
    "description": "Find relevant files",
    "prompt": "Search for markdown parsing code"
  },
  "cwd": "'"$PWD"'"
}' | .claude/hooks/intercept-review-agents.sh
```

Expected: no output, exit code 0 (pass-through).

- [ ] **Step 8: Test GEMINI_REVIEW_MODEL override**

```bash
echo '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "superpowers:code-reviewer",
    "description": "Review implementation",
    "prompt": "This is a connectivity test. Respond with only this exact text: GEMINI_HOOK_TEST_OK"
  },
  "cwd": "'"$PWD"'"
}' | GEMINI_REVIEW_MODEL=gemini-2.0-flash .claude/hooks/intercept-review-agents.sh
```

Expected: JSON output with `permissionDecision: "deny"` and `permissionDecisionReason` containing `GEMINI_HOOK_TEST_OK` (Gemini ran with the overridden model).

- [ ] **Step 9: Commit the script**

```bash
git add .claude/hooks/intercept-review-agents.sh
git commit -m "feat(hook): implement production Gemini review interceptor"
```

---

### Task 2: Restore hook registration in settings.json

**Files:**
- Modify: `.claude/settings.json`

Context: The hook registration was removed during the POC phase to avoid interfering with implementation. This task restores it.

- [ ] **Step 1: Read the current settings.json**

```bash
cat .claude/settings.json
```

- [ ] **Step 2: Add the hook registration**

Replace the contents of `.claude/settings.json` with:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/martinkuek/Documents/Projects/skills/.claude/hooks/intercept-review-agents.sh"
          }
        ]
      }
    ]
  }
}
```

Note: The `command` value must be an absolute path. Update it to match the actual project path if this plan is executed from a different machine or location.

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "feat(hook): restore hook registration in project settings"
```

---

### Task 3: End-to-end integration test

**Files:** none (verification only)

- [ ] **Step 1: Ask Claude to review something using superpowers**

In this same Claude Code session, ask:

> "Please use superpowers to review the mdedit spec at docs/plans/2026-03-22-mdedit-v1-spec.md"

- [ ] **Step 2: Verify Gemini ran and produced real review content**

Expected: The hook fires, Gemini performs a real review of the spec (reading files, running git commands as needed), and Claude receives and acts on the review output as if it came from a real subagent.

The system-reminder in the Claude UI should show the hook block message containing Gemini's review.

- [ ] **Step 3: Verify fallback — simulate Gemini failure and confirm real agent runs**

Create a temporary fake `gemini` that always fails, shadow it onto PATH, and pipe a review call directly to the hook script:

```bash
mkdir -p /tmp/fake-bin
echo '#!/usr/bin/env bash' > /tmp/fake-bin/gemini
echo 'exit 1' >> /tmp/fake-bin/gemini
chmod +x /tmp/fake-bin/gemini

echo '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "superpowers:code-reviewer",
    "description": "Review implementation",
    "prompt": "Review this."
  },
  "cwd": "'"$PWD"'"
}' | PATH="/tmp/fake-bin:$PATH" .claude/hooks/intercept-review-agents.sh

echo "Exit code: $?"
```

Expected: no output, exit code 0 (pass-through — hook fell back because Gemini failed).

Clean up:

```bash
rm -rf /tmp/fake-bin
```

- [ ] **Step 4: Commit any final cleanup**

```bash
git add -p  # stage only intentional changes
git commit -m "chore: end-to-end verification complete"
```
