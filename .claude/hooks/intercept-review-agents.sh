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
