---
description: Run a code review via your running Opencode server
argument-hint: '[--base <ref>] [--scope auto|working-tree|branch] [--model <spec>] [--json]'
disable-model-invocation: true
allowed-tools: Bash(node:*)
---

Run an Opencode code review through the companion script.

Raw slash-command arguments:
`$ARGUMENTS`

Core constraint:
- This command is review-only. Do not fix issues, apply patches, or suggest
  that you are about to make changes.
- Your only job is to run the review and return the companion script's
  output verbatim to the user.

Execution:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/opencode-companion.mjs" review $ARGUMENTS
```

Return the command's stdout verbatim. Do not paraphrase or summarise.
