# 💬 Search doco. Tell me everythin…

### User

Search doco. Tell me everything about running Claude Code in headless mode

---

### Assistant

I'll search the documentation for Claude Code headless mode information.

Here's everything about running Claude Code in headless mode (now officially called "programmatic CLI" or "Agent SDK"):

## Core Concept

The CLI was previously called "headless mode." The -p flag and all CLI options work the same way. Headless mode runs Claude Code without interaction, suitable for CI/CD pipelines, automation scripts, and batch processing.

## Basic Usage

Add `-p` (or `--print`) to run non-interactively:

```bash
# Basic query
claude -p "Explain the architecture of this project"

# JSON output with metadata
claude -p "List all TODO comments" --output-format json

# Streaming JSON for real-time processing
claude -p "Review recent changes" --output-format stream-json
```

## Output Formats

Claude Code v1.0.33+ offers three output formats via `--output-format`:

| Format | Use Case |
|--------|----------|
| `text` | Default, human-readable stdout |
| `json` | Structured with metadata, tokens, session_id |
| `stream-json` | Real-time newline-delimited JSON |

Extract specific fields with jq:
```bash
claude -p "Analyze this code" --output-format json | jq -r '.result'
claude -p "Summarize this file" --output-format json | jq '.usage'
```

## Tool Permissions

Use `--allowedTools` to let Claude use certain tools without prompting. The `--allowedTools` flag uses permission rule syntax. The trailing `*` enables prefix matching, so `Bash(git diff *)` allows any command starting with `git diff`. The space before `*` is important.

```bash
# Run tests and fix failures
claude -p "Run tests and fix failures" --allowedTools "Bash,Read,Edit"

# Git operations with prefix matching
claude -p "Create appropriate commit" \
  --allowedTools "Bash(git diff *),Bash(git log *),Bash(git status *),Bash(git commit *)"

# Read-only analysis
claude -p "Analyze codebase" --allowedTools "Read,Glob,Grep"

# Disallow specific tools
claude -p "Review code" --disallowedTools "Write,Edit,Bash"
```

## Permission Modes

```bash
# Plan mode (read-only)
claude --permission-mode plan -p "Analyze auth system"

# Auto-accept edits (use with caution)
claude --permission-mode acceptEdits -p "Add type annotations"

# Bypass all permissions (CI containers only!)
claude -p "Generate tests" --dangerously-skip-permissions
```

⚠️ `--dangerously-skip-permissions` should only be used in isolated environments (CI containers).

## Session Management

Capture session ID for later resumption:

```bash
# Capture session ID
session_id=$(claude -p "Start a review" --output-format json | jq -r '.session_id')

# Resume that session
claude -p "Continue that review" --resume "$session_id"

# Or resume most recent
claude --resume -p "Continue previous work"
```

## Piping & Stdin

The -p flag accepts context via stdin. In practice, this combination with Unix pipes covers 80% of headless use cases.

```bash
# Analyze git diff
git diff HEAD~5 | claude -p "Review these changes"

# Process file content
cat error.log | claude -p "Explain these errors"

# PR review
gh pr diff "$1" | claude -p "Review for vulnerabilities" --output-format json
```

## System Prompt Injection

```bash
# Append to default system prompt
claude -p "Review this code" \
  --append-system-prompt "You are a security engineer. Focus on vulnerabilities."
```

`--append-system-prompt` is ephemeral - NOT re-applied on `--resume`.

## Structured Output with JSON Schema

You can specify a JSON schema for structured output:

```bash
claude -p "Extract function names from auth.py" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}'
```

Result appears in `structured_output` field.

## CI/CD Integration Examples

**GitHub Actions:**
```yaml
- name: Code Review
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    claude -p "Review code for issues" \
      --output-format json > review.json
```

**GitLab CI:**
```yaml
claude-review:
  script:
    - claude -p "Review the code in this MR" --output-format json > review.json
```

## Environment Variables

Set these variables in your CI file to avoid repeating flags:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export CLAUDE_CODE_MAX_TURNS=5
export CLAUDE_CODE_OUTPUT_FORMAT=json
```

## Critical Gotchas

1. `--verbose` is required with `stream-json` output - without it, Claude exits silently with status 1
2. File writes silently fail without `--permission-mode bypassPermissions`
3. Session hooks don't run in `--print` mode - no SessionStart/SessionEnd
4. User-invoked skills like `/commit` and built-in commands are only available in interactive mode. In `-p` mode, describe the task you want to accomplish instead.
5. Headless mode doesn't persist between sessions - must restart each time

## Agent SDK (Python/TypeScript)

The Agent SDK gives you the same tools, agent loop, and context management that power Claude Code, programmable in Python and TypeScript.

**Python:**
```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="What files are in this directory?",
    options=ClaudeAgentOptions(allowed_tools=["Bash", "Glob"]),
):
    if hasattr(message, "result"):
        print(message.result)
```

**TypeScript:**
```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Fix the bug in auth.py",
  options: { allowedTools: ["Read", "Edit", "Bash"] }
})) {
  console.log(message);
}
```

The Claude Code CLI is automatically bundled with the Python package - no separate installation required!

## Performance Notes

With Node.js 22 LTS and Claude Code v1.0.33+, headless mode performance reaches an average startup time of 800 ms. Memory consumption stays under 256 MB for most executions.

---

This covers the main headless/programmatic patterns. Given your interest in autonomous agent architectures and Ralph Wiggum loops, the Agent SDK with hooks and custom tools is probably the most interesting angle for building more sophisticated automation chains.

---

### User

I want to know if a session launched headless can use the 'agent' tool to avail itself of subagents

---

### Assistant

Good question — let me dig into that specifically.

This is the key answer, Max:

**Yes, headless sessions CAN use subagents** — but with important nuances.

## How It Works

Even without defining custom subagents, Claude can spawn the built-in general-purpose subagent when Task is in your allowedTools. This is useful for delegating research or exploration tasks without creating specialized agents.

So in headless mode:
```bash
claude -p "Research the codebase and fix auth bugs" \
  --allowedTools "Task,Read,Edit,Bash,Glob,Grep"
```

The Task tool must be included in allowedTools since Claude invokes subagents through the Task tool.

## Built-in Subagents Available

From the reverse engineered resources/leaked system prompt, it's possible to see that the sub-agents are spawned via the Task tool. It defines 5 agent types: general-purpose (full tool access, inherits context), Explore (fast read-only codebase search), Plan (software architect for implementation planning).

A research agent used during plan mode to gather context before presenting a plan. Purpose: Codebase research for planning.

## Critical Limitation: No Nesting

This prevents infinite nesting (subagents cannot spawn other subagents).

Currently, sub-agents spawned via the Task tool in Claude Code cannot themselves spawn additional sub-agents. When a sub-agent attempts to use the Task tool, it reports that the tool is not available.

## The Hacky Workaround (Which You'll Appreciate)

Some users have discovered they can work around this limitation by having sub-agents call `claude -p` through the Bash tool to spawn non-interactive Claude instances.

```bash
# Inside a sub-agent, instead of using Task tool:
claude -p "Review the CI logs in /tmp/ci_output.log" < /tmp/ci_output.log > /tmp/ci_summary.txt
```

But the downsides are real:
No Context Sharing: The nested Claude instance starts with zero context about the parent task, requiring extensive prompt engineering to pass necessary information. Inconsistent Behavior: The CLI interface may have different capabilities, models, or behaviors compared to the Task-spawned agents.

## Custom Subagents in Headless Mode

You can also define subagents as markdown files in `.claude/agents/` directories. Programmatically defined agents take precedence over filesystem-based agents with the same name.

A subagent's context window starts fresh (no parent conversation) but isn't empty. The only channel from parent to subagent is the Task prompt string, so include any file paths, error messages, or decisions the subagent needs directly in that prompt.

## SDK Approach (Python/TypeScript)

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="Research three approaches to implement OAuth2 in parallel",
    options=ClaudeAgentOptions(
        allowed_tools=["Task", "Read", "Glob", "Grep", "Bash"]
    )
):
    print(message)
```

---

**TL;DR**: Yes, headless `-p` mode can spawn subagents via the Task tool. Just include `Task` in `--allowedTools`. But subagents can't spawn further subagents natively — the recursive `claude -p` via Bash hack exists but loses context. This is basically the "Ralph Wiggum loop" constraint you'd run into when trying to build deeper hierarchical agent trees.

---

### User

I was just trying to create a skill for the Claude code environment that replicates the launch extended Web search tool you have here.

I did indeed have everything use headless mode. The lead researcher/agent is a bash command in the "deep research" skill.

The lead agent prompt says to also launch research subagents via Claude -p.

Everything communicates via the filesystem.

But if headless cli sessions can use subagents it may be possible to change the architecture slightly to have the lead agent (in a headless session) spawn the researchers as subagents rather than additional headless cli sessions.

---

### Assistant

That's a clever architecture shift, and yes — it should work better in several ways.

**Current architecture:**
```
Skill (bash) → claude -p (lead) → multiple claude -p (researchers)
```

**Proposed architecture:**
```
Skill (bash) → claude -p (lead, with Task in allowedTools) → Task subagents (researchers)
```

## Why native subagents would be cleaner

1. **Parallel execution is built-in** — Task can spawn multiple subagents concurrently without you managing background processes
2. **Results return to the lead agent cleanly** — no file-watching or polling needed for that handoff
3. **Context isolation is handled properly** — each researcher gets a fresh context window, reports back a summary
4. **The lead agent can coordinate** — it sees all subagent results and synthesizes them, rather than relying on filesystem-based aggregation

## What you'd need to change

```bash
# Your skill's bash command would become:
claude -p "You are a research coordinator. Use the Task tool to spawn parallel research subagents for: $TOPIC" \
  --allowedTools "Task,Read,Write,Bash,WebSearch,WebFetch" \
  --output-format json
```

The lead agent's prompt would shift from "launch claude -p processes" to "use the Task tool to delegate to subagents."

## The one constraint that still applies

Researchers (the subagents) **cannot spawn their own subagents**. So if your current design has researchers spawning sub-researchers, that layer would still need the `claude -p` via Bash hack — or you flatten the hierarchy.

## Hybrid option

You could do both: lead agent spawns researchers via Task (clean, parallel), but if any researcher needs to go deeper, *that* layer uses `claude -p`. Filesystem communication still works as your fallback channel for cross-session coordination.

---

Want me to look at your current skill structure and sketch out what the refactored lead agent prompt would look like? I could also check if there's any documentation on passing custom subagent definitions programmatically via the CLI flags (rather than needing `.claude/agents/` files).

---

