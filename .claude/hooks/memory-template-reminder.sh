#!/usr/bin/env bash
# memory-template-reminder.sh
# PreToolUse hook: fires on Bash tool calls that may corrupt memory file structure.
#
# Trigger 1 — content= on content paths:
#   Fires when memory.commit is called with content= on self/, collaborator/, or entities/.
#   These files have template structure that must be preserved. Use the mdedit workflow instead:
#   fetch → mdedit → commit(from_file=).
#
# Trigger 2 — entity commit without template fetch:
#   Fires when memory.commit targets entities/ but the command does not include get_template.
#   Entity templates may differ from the base entity.yaml — always fetch before editing.
#   To suppress this reminder, include memory.get_template(...) in the same bash block.

set -euo pipefail

INPUT=$(cat)
COMMAND=$(printf '%s\n' "$INPUT" | jq -r '.tool_input.command // ""')

# ── Trigger 1: content= on a content path ──────────────────────────────────────
is_content_overwrite() {
  printf '%s\n' "$COMMAND" | grep -q 'memory\.commit' || return 1
  printf '%s\n' "$COMMAND" | grep -q 'content\s*=' || return 1
  printf '%s\n' "$COMMAND" | grep -qE "memory\.commit\(['\"]?(self|collaborator|entities)/" || return 1
  return 0
}

if is_content_overwrite; then
  REASON="memory-template-reminder: You are using content= on an existing memory file.

The correct workflow for existing content files is:
  1. memory.fetch(path, return_mode='file', branch='working')
  2. mdedit replace|append|insert /tmp/[repo-name]/[path].md \"[heading]\" --content \"...\"
  3. memory.commit(path, from_file='/tmp/[repo-name]/[path].md', message='...')

Check the template for this file in context (loaded at session start) to confirm the correct structure before editing. Reissue using the mdedit workflow."

  jq -n --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
fi

# ── Trigger 2: entity commit without get_template ──────────────────────────────
is_entity_commit_without_template() {
  printf '%s\n' "$COMMAND" | grep -q 'memory\.commit' || return 1
  printf '%s\n' "$COMMAND" | grep -qE "memory\.commit\(['\"]?entities/" || return 1
  printf '%s\n' "$COMMAND" | grep -q 'get_template' && return 1  # template present — allow
  return 0
}

if is_entity_commit_without_template; then
  REASON="memory-template-reminder: Before committing an entity file, fetch its template.

Entity files may use custom templates that differ from the base entity.yaml.

Add memory.get_template('[entity-name].yaml') to this bash block and reissue.
If a custom template exists at _templates/entities/[name].yaml it will be returned;
otherwise the config default (entity.yaml) is used.

Example commit block:
  memory.get_template('kai.yaml')   # fetch template into context
  memory.commit('entities/kai', from_file='/tmp/[repo]/entities/kai.md', message='...')"

  jq -n --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
fi

# All other Bash calls — allow silently
exit 0
