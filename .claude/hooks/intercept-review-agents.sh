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

SUBAGENT_TYPE=$(printf "%s\n" "$INPUT" | jq -r '.tool_input.subagent_type // ""')
DESCRIPTION=$(printf "%s\n" "$INPUT" | jq -r '.tool_input.description // ""')
CWD=$(printf "%s\n" "$INPUT" | jq -r '.cwd // ""')
PROMPT=$(printf "%s\n" "$INPUT" | jq -r '.tool_input.prompt // ""')

is_review_call() {
  if [[ "$SUBAGENT_TYPE" == "superpowers:code-reviewer" ]]; then
    return 0
  fi
  if [[ "$SUBAGENT_TYPE" == "general-purpose" ]] && printf "%s\n" "$DESCRIPTION" | grep -qi "^Review"; then
    return 0
  fi
  return 1
}

if ! is_review_call; then
  exit 0
fi

# Build optional model arguments array
MODEL_ARGS=()
if [[ -n "${GEMINI_REVIEW_MODEL:-}" ]]; then
  MODEL_ARGS=(-m "$GEMINI_REVIEW_MODEL")
fi

# Run Gemini in yolo mode with a project-scoped policy that blocks writes and
# destructive git commands. Yolo allows full read/explore access; the policy
# enforces reviewer-only separation of duties.
GEMINI_OUTPUT=$(
  printf "%s\n" "$PROMPT" \
  | gemini \
      -p "Perform the review task described in the input above." \
      --approval-mode yolo \
      --policy "$CWD/.claude/hooks/gemini-review-policy.toml" \
      --include-directories "$CWD" \
      -o text \
      "${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"}" \
      2>/dev/null
) || exit 0

# Fallback: if Gemini returned nothing, let the real Agent run
if [[ -z "$GEMINI_OUTPUT" ]]; then
  exit 0
fi

REASON="A PreToolUse hook intercepted your review agent call and redirected it to Gemini CLI. The following is Gemini's complete review. Continue the workflow as normal.

[GEMINI REVIEW]

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
