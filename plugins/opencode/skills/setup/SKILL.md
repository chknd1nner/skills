---
description: Verify Opencode plugin setup and create the config file if missing
disable-model-invocation: true
allowed-tools: Bash(node:*)
---

Run the Opencode plugin setup helper.

Execution:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/opencode-companion.mjs" setup
```

Return the command's stdout verbatim.
