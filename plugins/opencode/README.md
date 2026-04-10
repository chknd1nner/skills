# Opencode Plugin for Claude Code

Dispatch code reviews to a running [Opencode](https://github.com/anomalyco/opencode) server from Claude Code.

## Quick start

1. Install Opencode and start the server:

   ```bash
   opencode serve
   ```

2. Load the plugin in Claude Code:

   ```bash
   claude --plugin-dir ./plugins/opencode
   ```

3. Run a review:

   ```
   /opencode:review
   ```

## Commands

### `/opencode:review`

Run a code review on your current git changes.

```
/opencode:review                          # Auto-detect scope
/opencode:review --scope working-tree     # Review uncommitted changes
/opencode:review --scope branch           # Review branch vs upstream
/opencode:review --base origin/main       # Review against a specific base
/opencode:review --json                   # Machine-readable output
```

### `/opencode:setup`

Verify the plugin is configured correctly and the server is reachable.

## Configuration

Config file: `~/.config/opencode-plugin/config.toml`

Created automatically on first run. Edit to customize:

```toml
[server]
url = "http://localhost:4096"
# password = "your-bearer-token"

[commands.review]
agent    = "code-reviewer"
provider = "poe"
model    = "openai/gpt-5.4"

[transcript]
directory         = ".opencode/reviews"
include_reasoning = false
```

## Transcripts

Each review produces two files under `.opencode/reviews/`:

- **`{id}.log.md`** — chat-transcript-style activity log (tool calls, thinking phases, timing)
- **`{id}.review.md`** — the clean final review text

You can `tail -f .opencode/reviews/{id}.log.md` in another terminal to watch the review live.

## Requirements

- Node.js 20+
- A running Opencode server (`opencode serve`)
- Claude Code
