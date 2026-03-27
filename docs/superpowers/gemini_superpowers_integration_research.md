# Integrating Gemini CLI into the Superpowers Workflow

Research into offloading token-heavy Superpowers subagent roles from Claude to Gemini CLI, reducing Claude Pro subscription pressure while leveraging Gemini's 1M token context window.

## Executive Summary

The Superpowers v5.0.5 workflow dispatches **6 distinct subagent roles** via Claude Code's `Task` tool. Several of these are **read-heavy, review-oriented tasks** that don't need Claude's tool-use capabilities — they just need to read files, reason about them, and return structured text. These are ideal candidates for Gemini CLI replacement via `bash` tool calls.

> [!IMPORTANT]
> Gemini CLI's `-p` flag is deprecated in favour of positional prompts, but both work. The key capability is: pipe content via stdin + provide instructions as the prompt → get structured text output on stdout. With `--model` you can select Flash (fast/cheap) vs Pro (deep reasoning), and with `--output-format json` you get machine-parseable output.

## The Superpowers Subagent Roles

| Role | Dispatched By | What It Does | Claude Tools Needed? | Gemini Candidate? |
|------|--------------|--------------|---------------------|-------------------|
| **Spec Document Reviewer** | `brainstorming` | Reads spec file, checks completeness/consistency | Read-only | ✅ **Excellent** |
| **Plan Document Reviewer** | `writing-plans` | Reads plan + spec, checks alignment/buildability | Read-only | ✅ **Excellent** |
| **Spec Compliance Reviewer** | `subagent-driven-development` | Reads code + spec, verifies implementation matches | Read-only | ✅ **Excellent** |
| **Code Quality Reviewer** | `subagent-driven-development` | Reviews git diff for quality, architecture, testing | Read-only | ✅ **Excellent** |
| **Code Reviewer** (agent) | `requesting-code-review` | Full code review against plan | Read-only | ✅ **Excellent** |
| **Implementer** | `subagent-driven-development` | Writes code, runs tests, commits | **Yes** (Bash, Write) | ❌ Not suitable |
| **Explorer** (Haiku) | Ad-hoc codebase questions | Reads files, answers questions | Read-only | ✅ **Excellent** |

> [!TIP]
> **5 of 7 roles are pure read+reason tasks** — perfect for Gemini CLI. Only the Implementer needs Claude's file editing and bash tools. The Explorer is currently Haiku (200k context) — Gemini offers **5× the context window** (1M tokens).

## Integration Architecture

### How It Works

Claude Code's main agent calls Gemini CLI via `bash` tool instead of dispatching a Claude `Task` subagent:

```
┌─────────────────────────────────────────────────────┐
│  Claude Code (Main Agent / Superpowers Controller)  │
│                                                     │
│  Instead of:  Task("Review this spec...")           │
│  Does:        bash("cat spec.md | gemini ...")      │
│                                                     │
│  Gemini returns structured text on stdout            │
│  Claude parses the response and continues workflow   │
└─────────────────────────────────────────────────────┘
```

### The Bash Invocation Pattern

```bash
# General pattern - pipe file content + provide review prompt
cat "$FILE_PATH" | gemini --model gemini-2.5-flash \
  "You are a spec document reviewer. [FULL PROMPT HERE]. 
   Review the spec piped to you via stdin." 2>/dev/null

# For multi-file reviews (spec + plan, or code + spec)
{
  echo "=== SPEC DOCUMENT ==="
  cat "$SPEC_PATH"
  echo "=== PLAN DOCUMENT ==="  
  cat "$PLAN_PATH"
} | gemini --model gemini-2.5-pro \
  "You are a plan document reviewer. [PROMPT]. 
   The spec and plan are provided via stdin." 2>/dev/null

# For git diff reviews
git diff "$BASE_SHA..$HEAD_SHA" | gemini --model gemini-2.5-pro \
  "You are a senior code reviewer. [PROMPT].
   The git diff is provided via stdin." 2>/dev/null

# For codebase exploration (replacing Haiku explorer)
find src/ -name '*.ts' -exec cat {} + | gemini --model gemini-2.5-flash \
  "You are exploring a codebase. [QUESTION].
   The source files are provided via stdin." 2>/dev/null
```

> [!NOTE]
> `2>/dev/null` suppresses Gemini CLI's stderr debug/progress output so Claude only sees the actual response on stdout.

## Implementation Strategies

There are **four approaches**, from most to least automated:

---

### Strategy 1: PreToolUse Hook Interception (Recommended — Deterministic)

> [!IMPORTANT]
> This is the approach you asked about — and it **works**. Claude Code's `PreToolUse` hook with matcher `Agent` receives the full subagent parameters as JSON on stdin and can deterministically intercept, run Gemini, and inject the result back. Superpowers doesn't need to be modified at all.

#### How Claude Code Hooks Work for This

The `PreToolUse` event fires **before** any tool executes. When matched on `Agent`, the hook receives JSON like:

```json
{
  "session_id": "abc123",
  "cwd": "/Users/martinkuek/project",
  "hook_event_name": "PreToolUse",
  "tool_name": "Agent",
  "tool_input": {
    "prompt": "You are a spec document reviewer. Verify this spec...",
    "description": "Review spec document",
    "subagent_type": "general-purpose",
    "model": "sonnet"
  }
}
```

The hook can return JSON to control what happens:

| Action | JSON Output | Effect |
|--------|------------|--------|
| **Deny + inject result** | `permissionDecision: "deny"` + `permissionDecisionReason: "<gemini output>"` | Blocks Claude subagent, returns Gemini's review as if it were the deny reason — Claude sees this as context |
| **Allow** | `permissionDecision: "allow"` | Let Claude subagent proceed normally (for implementers) |
| **Modify** | `updatedInput: {...}` | Change the subagent's parameters before it runs |

#### The Interception Flow

```
Superpowers Controller                PreToolUse Hook                    Gemini CLI
        │                                   │                               │
        │── Agent("Review spec...") ──────►│                               │
        │                                   │── detect review subagent ───►│
        │                                   │   extract prompt + files      │
        │                                   │                               │
        │                                   │◄── Gemini review result ─────│
        │                                   │                               │
        │◄── deny + additionalContext ─────│                               │
        │    (contains Gemini's review)      │                               │
        │                                   │                               │
        │── continues workflow with ────────►                               │
        │   Gemini's review result                                          │
```

> [!CAUTION]
> **Key design decision**: The hook **denies** the Agent call and passes the Gemini output back via `additionalContext`. The controller Claude sees this context and treats it the same as a subagent response. This works because the Superpowers controller parses the text content of the review — it doesn't care whether it came from a Claude subagent or from hook context.

#### Hook Configuration

Place in `~/.claude/settings.json` (user-level, applies to all projects):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/martinkuek/Documents/Projects/skills/claude-code-only/gemini-bridge/gemini-intercept.sh",
            "timeout": 120
          }
        ]
      }
    ]
  }
}
```

#### The Intercept Script: `gemini-intercept.sh`

This is the core of the system. It reads the hook's JSON input, decides whether this subagent should go to Gemini, and if so, runs the review and returns the result.

```bash
#!/bin/bash
# gemini-intercept.sh — PreToolUse hook for Agent tool
# Intercepts review subagents and redirects to Gemini CLI
set -euo pipefail

# Read JSON input from stdin
INPUT=$(cat)

# Extract tool parameters
PROMPT=$(echo "$INPUT" | jq -r '.tool_input.prompt // empty')
DESCRIPTION=$(echo "$INPUT" | jq -r '.tool_input.description // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# Pattern-match the description/prompt to identify review subagents
# These patterns match the Superpowers prompt templates
IS_REVIEW=false
MODEL="gemini-2.5-flash"

if echo "$DESCRIPTION" | grep -qi "review spec document\|spec compliance\|spec review"; then
  IS_REVIEW=true
  MODEL="gemini-2.5-flash"
elif echo "$DESCRIPTION" | grep -qi "review plan document\|plan review"; then
  IS_REVIEW=true
  MODEL="gemini-2.5-pro"
elif echo "$DESCRIPTION" | grep -qi "code.quality\|code.review\|code-reviewer"; then
  IS_REVIEW=true
  MODEL="gemini-2.5-pro"
elif echo "$DESCRIPTION" | grep -qi "review.*compliance\|spec complian"; then
  IS_REVIEW=true
  MODEL="gemini-2.5-pro"
fi

# If not a review subagent, allow it through (implementers, etc.)
if [ "$IS_REVIEW" = false ]; then
  # Output nothing — exit 0 = allow
  exit 0
fi

# Run the review through Gemini CLI
# The prompt from the Agent tool already contains the full review instructions
GEMINI_RESULT=$(echo "$PROMPT" | gemini --model "$MODEL" \
  "You are being given a review task. The full instructions and context follow via stdin. 
   Execute the review and provide your assessment in the exact format requested." \
  2>/dev/null) || {
  # If Gemini fails, allow the original Claude subagent to proceed
  exit 0
}

# Return JSON that denies the Agent call and injects Gemini's review
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Review completed by Gemini CLI (saving Claude tokens). Result follows:",
    "additionalContext": $(echo "$GEMINI_RESULT" | jq -Rs .)
  }
}
EOF
```

#### Limitations and Gotchas

1. **The prompt must be self-contained**: The Superpowers prompt templates paste full task text into the `prompt` field — this is what we pipe to Gemini. If a subagent was supposed to *read files itself* (using Read/Glob tools), Gemini can't do that. Fortunately, the Superpowers review prompts are designed to include all context inline.

2. **File reading issue**: The spec/plan review prompts reference `[SPEC_FILE_PATH]` — the reviewer is supposed to read the file. We need to detect file paths in the prompt and pre-read them before piping to Gemini. See the enhanced version below.

3. **`deny` semantics**: When the hook denies an Agent call, Claude Code tells the controller "the tool call was denied." The `permissionDecisionReason` and `additionalContext` provide context. The controller should interpret this as "the review was done externally." You may need a small CLAUDE.md addition to help Claude understand this pattern.

#### Enhanced Script: File Path Extraction

```bash
# Enhanced version that extracts file paths from the prompt and pre-reads them
# Add this before the Gemini invocation:

# Extract any file paths mentioned in the prompt
FILE_PATHS=$(echo "$PROMPT" | grep -oE '/[a-zA-Z0-9_./-]+\.(md|py|ts|js|json|yaml|yml)' | sort -u)

# Build context by reading referenced files
CONTEXT=""
for fp in $FILE_PATHS; do
  if [ -f "$fp" ]; then
    CONTEXT+="
=== FILE: $fp ===
$(cat "$fp")
"
  elif [ -f "$CWD/$fp" ]; then
    CONTEXT+="
=== FILE: $fp ===
$(cat "$CWD/$fp")
"
  fi
done

# Pipe both the prompt and file contents to Gemini
GEMINI_RESULT=$(printf "%s\n\n%s" "$PROMPT" "$CONTEXT" | gemini --model "$MODEL" \
  "Execute the review task below. The review instructions and referenced file contents are provided." \
  2>/dev/null)
```

---

### Strategy 2: CLAUDE.md + Wrapper Scripts (Simpler, Less Automated)

If the hook approach feels too complex or fragile, the simpler alternative is wrapper scripts + CLAUDE.md instructions telling the controller to use them. This is **not deterministic** — it depends on Claude following the instructions — but is easier to debug.

#### Wrapper Scripts

Create scripts in your skills repo that Claude calls directly via Bash tool:

| Script | Replaces | Model |
|--------|----------|-------|
| `gemini-review-spec.sh` | Spec Document Reviewer | Flash |
| `gemini-review-plan.sh` | Plan Document Reviewer | Pro |
| `gemini-review-compliance.sh` | Spec Compliance Reviewer | Pro |
| `gemini-review-quality.sh` | Code Quality Reviewer | Pro |
| `gemini-review-code.sh` | Code Reviewer (agent) | Pro |
| `gemini-explore.sh` | Haiku Explorer | Flash |

#### CLAUDE.md Addition

```markdown
## Gemini CLI Integration for Superpowers Reviews

When using Superpowers skills that dispatch review subagents, use Gemini CLI 
wrapper scripts instead of Task/Agent tool for the following roles:

### Review Subagents → Gemini CLI
- **Spec Document Reviewer**: Run `bash ~/Documents/Projects/skills/claude-code-only/gemini-bridge/gemini-review-spec.sh <spec-path>`
- **Plan Document Reviewer**: Run `bash ~/Documents/Projects/skills/claude-code-only/gemini-bridge/gemini-review-plan.sh <plan-path> <spec-path>`
- **Code Quality/Review**: Run `bash ~/Documents/Projects/skills/claude-code-only/gemini-bridge/gemini-review-quality.sh <base-sha> <head-sha> <description> [plan-file]`

### Keep as Claude Subagents
- **Implementer subagents** must remain as Claude Agent subagents
- Any task requiring interactive tool use stays with Claude
```

---

### Strategy 3: Hybrid Hook + CLAUDE.md

Use the hook for deterministic interception of the clear-cut review roles (spec review, plan review), and CLAUDE.md instructions for the more nuanced ones (code quality, exploration).

---

### Strategy 4: Custom Superpowers Skill

Create a custom Superpowers skill that modifies the dispatch behaviour. Most fragile — Superpowers updates could conflict.

---

## Comparing the Strategies

| Factor | Hook Interception | CLAUDE.md + Scripts | Hybrid |
|--------|------------------|--------------------|---------| 
| **Deterministic?** | ✅ Yes — always intercepts | ❌ Claude may ignore | Partial |
| **Superpowers changes?** | None | None | None |
| **Complexity** | Medium (bash + jq parsing) | Low (scripts only) | Medium |
| **Fallback on failure** | ✅ Allows original subagent | ❌ No automatic fallback | ✅ |
| **Debug visibility** | Lower (happens in hook) | Higher (visible in transcript) | Mixed |
| **Handles all patterns** | May miss edge cases in prompt matching | Depends on Claude compliance | Best of both |

## Model Selection Guide

| Task Type | Recommended Model | Rationale |
|-----------|------------------|-----------|
| Spec review | `gemini-2.5-flash` | Checklist-style verification, fast |
| Plan review | `gemini-2.5-pro` | Needs to reason about plan↔spec alignment |
| Spec compliance review | `gemini-2.5-pro` | Must read code carefully and compare to spec |
| Code quality review | `gemini-2.5-pro` | Architectural judgment required |
| Codebase exploration | `gemini-2.5-flash` | Fast answers, large context is the main benefit |
| Simple Q&A about code | `gemini-2.5-flash` | Fast, 1M context handles large codebases |

## Cost/Benefit Analysis

### What You Save (Claude Pro)
- **5 review subagents per task** × 5-10 tasks per plan = **25-50 Claude subagent calls saved per feature**
- Each review subagent consumes significant context (full code, spec, diff) — the most token-heavy parts of the workflow
- Explorer subagent calls (currently Haiku, 200k limit) → Gemini with 1M context

### What You Gain (Gemini Pro)
- **1M token context** for exploration (5× Haiku's 200k)
- **No Claude subscription pressure** for review/exploration tasks
- Spread load across two subscriptions
- Gemini Flash for simple reviews is extremely fast

### Trade-offs
- **Latency**: Gemini CLI invocation has ~2-3s startup overhead per call
- **No tool use**: Gemini can't read files on its own — piping via stdin is required  
- **Prompt engineering**: Gemini doesn't have Claude's system prompt context
- **`deny` semantics**: When a hook denies an Agent call, the controller sees a denial — need `additionalContext` to carry the review result back. May need CLAUDE.md guidance so the controller interprets denials carrying review results correctly.
- **Error handling**: Scripts should fall back silently (exit 0 = allow original subagent)

## Next Steps

1. **Create `gemini-bridge/` skill in your skills repo** with the intercept script + wrapper scripts
2. **Start with hook interception for spec/plan reviews** — simplest prompt patterns to match
3. **Add the explorer replacement** via CLAUDE.md (highest immediate context window value)
4. **Test the deny + additionalContext pattern** to confirm the Superpowers controller correctly processes Gemini's review results
5. **Iterate on prompt matching** — refine the grep patterns in the intercept script as you see real prompts flow through
