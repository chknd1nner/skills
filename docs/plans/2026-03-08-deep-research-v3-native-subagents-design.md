# Deep Research v3: Native Subagents Design

Date: 2026-03-08

## Problem

The deep-research skill uses `claude -p` bash subprocesses for research subagents and the citations agent. This introduces:
- Filesystem coordination (tmp files, polling, cleanup)
- Process management (`&`, `wait`, orphaned processes on failure)
- Shell escaping complexity for long prompts
- An adaptation layer (file-based citations) that diverges from the Claude.ai production design

## Solution

Replace all `claude -p` subprocess calls within the lead agent with native Agent tool subagents. The lead agent's `claude -p` session runs as a main thread and can spawn subagents via the Agent tool. Researcher and citations subagent types are defined via the `--agents` CLI flag as inline JSON.

## Architecture

```
Outer session (interactive)
  └─ claude -p --agents '{"researcher":{...}, "citations":{...}}'
       │         --tools "Agent,WebSearch,WebFetch,Write,Read,Bash,Edit"
       │
       ├─ Agent(researcher, background) x N
       │    Each does research, returns full detailed findings with
       │    inline source URLs directly to lead agent context
       │
       ├─ Lead agent synthesises draft report from findings in context
       │    Inserts [^?] citation markers for claims derived from sources
       │
       ├─ Agent(citations, foreground)
       │    Receives draft + all source findings in task prompt
       │    Structured as <synthesized_text> and <sources> tags
       │    Returns cited report with [^N] footnotes and References section
       │
       └─ Lead agent writes final cited report to {OUTPUT_PATH}
```

### Key design decisions

1. **No filesystem coordination.** Research findings flow through context, not tmp files. The citations agent receives everything in its task prompt. No tmp directory, no cleanup step.

2. **Researchers return full findings.** Not summaries. The lead agent needs the complete, dense research findings with all source URLs to produce a comprehensive multi-page report. ~2-3k tokens per subagent x 5-8 subagents = ~15-20k tokens, well within the 200k context window.

3. **Citations agent mirrors Claude.ai production design.** Uses `<synthesized_text>` and `<sources>` tags passed in-prompt, matching the original Claude.ai deep research citations pattern. More faithful than the current file-based adaptation.

4. **Subagent definitions via `--agents` JSON.** The SKILL.md constructs a JSON object with `researcher` and `citations` entries, embedding the contents of subagent.md and citations-agent.md as their `prompt` fields. Written to a tmp file and loaded via `$(cat)` shell expansion.

## Files changed

### SKILL.md
- **Purpose**: Updated to reflect native subagent architecture
- **Instructions**: Steps 2-3 read subagent.md and citations-agent.md for content (no need to resolve absolute paths)
- **Step 3**: Constructs agents JSON (embedding prompt contents), writes both lead-prompt.txt and agents.json to tmp dir
- **Task context**: Remove ABS_PATH fields (no longer needed)
- **Step 5**: Launch command adds `--agents "$(cat agents.json)"` and adds `Agent` to `--tools`; removes `Edit` if not needed by lead agent directly
- **Step 6**: No cleanup step needed (no tmp files). Just confirmation. Actually, we still need the tmp dir for lead-prompt.txt and agents.json — add a simple cleanup or accept the minimal footprint.

### lead-agent.md
- **`<delegation_instructions>`**: Replace `claude -p` subprocess pattern with Agent tool. Launch researchers via `Agent(researcher)` with `run_in_background: true`. Each researcher's task prompt includes the research objective and instructs it to return full findings with source URLs.
- **`<use_parallel_tool_calls>`**: Replace "Bash background processes (`&`) followed by `wait`" with "Launch multiple Agent(researcher) calls in parallel using background mode"
- **`<answer_formatting>`**:
  - Step 3: Lead agent synthesises draft in context (no Write to file needed for draft)
  - Step 5: Replace `claude -p` citations launch with Agent(citations) call. Task prompt contains `<synthesized_text>` (the draft) and `<sources>` (all research findings from context)
  - Step 6: Lead agent writes the citations agent's returned output to {OUTPUT_PATH} via Write tool
  - Remove: `rm -rf {TMP_DIR}` cleanup (no tmp files from research)
- **Last paragraph**: Remove references to absolute paths for subagent.md and citations-agent.md

### subagent.md (researcher prompt)
- Remove final instruction to write findings to a filepath via Write tool
- Instead: instruct to return findings as the final response with all source URLs inline as markdown links
- Rest of prompt unchanged (research process, guidelines, source quality, parallel tool calls, tool call limits)

### citations-agent.md
- Rewrite to match Claude.ai production pattern:
  - Receives `<synthesized_text>` and `<sources>` in task prompt
  - Returns cited text with [^N] footnotes and appended References section
  - No file I/O (no Read, no Edit, no Bash ls)
  - Keep citation guidelines and technical requirements
- Tools needed: none (pure text transformation) — though model may still benefit from having Read for edge cases

## Context window budget

| Component | Tokens (est.) |
|-----------|---------------|
| Lead agent system prompt | ~3k |
| Research findings (5-8 subagents) | ~15-20k |
| Draft synthesis | ~5-8k |
| Citations agent prompt overhead | ~2k |
| **Total lead agent context** | **~25-33k / 200k** |

Comfortable margin. Even with 10 subagents returning detailed findings, we stay under 50k.
