---
name: deep-research
description: Conduct multi-agent deep research on any topic and save a cited report to a markdown file. Use when the user asks to research a topic deeply, do deep research, or wants a comprehensive research report with citations. Supports optional --model and --output flags.
---

# Purpose

Runs a multi-agent research pipeline modelled on Claude.ai's Deep Research feature. The outer session launches the lead agent (Sonnet) via `claude -p` with native subagent definitions passed via `--agents`. The lead agent uses the Agent tool to spawn parallel researcher subagents (Haiku) and a citations subagent (Haiku). Research findings flow through context — no filesystem coordination. The final cited report is saved to a markdown file.

## Variables

```
LEAD_MODEL: claude-sonnet-4-6
SUBAGENT_MODEL: claude-haiku-4-5-20251001
CITATIONS_MODEL: claude-haiku-4-5-20251001
DEFAULT_OUTPUT_DIR: ~/research
```

## Instructions

1. Read `references/lead-agent.md` — this is the prompt for the lead agent
2. Read `references/subagent.md` — this is the system prompt for research subagents (will be embedded in agents JSON)
3. Read `references/citations-agent.md` — this is the system prompt for the citations subagent (will be embedded in agents JSON)

## Workflow

When the skill is invoked:

**1. Parse invocation**

Extract from the user's message:
- `QUERY`: the research topic (everything that is not a flag)
- `LEAD_MODEL`: if `--model opus` is present, use `claude-opus-4-6`; otherwise default `claude-sonnet-4-6`
- `OUTPUT_DIR`: if `--output <path>` is present, use that path; otherwise use `~/research`

**2. Derive paths**

- `SLUG`: convert QUERY to kebab-case, max 5 words (e.g. "ai impact on healthcare" → "ai-impact-on-healthcare")
- `DATE`: today's date in YYYY-MM-DD format
- `OUTPUT_PATH`: `{OUTPUT_DIR}/{DATE}-{SLUG}.md`
- `BOOTSTRAP_DIR`: `{OUTPUT_DIR}/.tmp/{DATE}-{SLUG}/` (temporary, holds only launch files)

**3. Prepare launch files**

Construct two files needed to launch the lead agent:

**a) Lead agent prompt:** Take the contents of `references/lead-agent.md` (substituting `{CURRENT_DATE}` with `{DATE}`), then append the task context block:

```
---

<task_context>
Current date: {DATE}
Research query: {QUERY}
Final output path: {OUTPUT_PATH}
</task_context>
```

Use the Write tool to save the result to `{BOOTSTRAP_DIR}/lead-prompt.txt` — this implicitly creates `{BOOTSTRAP_DIR}`.

**b) Agents JSON:** Construct a JSON object defining the `researcher` and `citations` subagent types. Embed the contents of `references/subagent.md` as the `prompt` for `researcher`, and `references/citations-agent.md` as the `prompt` for `citations`. Escape the prompt contents for JSON (newlines as `\n`, quotes as `\"`).

```json
{
  "researcher": {
    "description": "Research subagent for deep research tasks. Spawned by the lead agent to investigate specific research questions.",
    "prompt": "<contents of references/subagent.md, JSON-escaped>",
    "tools": ["WebSearch", "WebFetch", "Read", "Bash"],
    "model": "haiku"
  },
  "citations": {
    "description": "Citations agent for resolving citation markers in research reports. Spawned by the lead agent after draft synthesis.",
    "prompt": "<contents of references/citations-agent.md, JSON-escaped>",
    "model": "haiku"
  }
}
```

Note: the `citations` subagent needs no tools — it performs pure text transformation on content received in its prompt.

Use the Write tool to save the result to `{BOOTSTRAP_DIR}/agents.json`.

**4. Announce**

Tell the user:
> Starting deep research on: "{QUERY}"
> Lead model: {LEAD_MODEL} | Subagents: {SUBAGENT_MODEL}
> Report will be saved to: {OUTPUT_PATH}

**5. Launch lead agent**

Run the lead agent via Bash:

```bash
claude -p "$(cat {BOOTSTRAP_DIR}/lead-prompt.txt)" \
  --model {LEAD_MODEL} \
  --tools "Agent,WebSearch,WebFetch,Write,Read,Bash" \
  --agents "$(cat {BOOTSTRAP_DIR}/agents.json)" \
  --dangerously-skip-permissions \
  --no-session-persistence 2>&1
```

The lead agent uses the Agent tool to spawn researcher and citations subagents internally. Wait for it to complete — it writes the final cited report to `{OUTPUT_PATH}` before finishing.

**6. Confirm and clean up**

Clean up bootstrap files:

```bash
rm -rf {BOOTSTRAP_DIR}
```

Tell the user:
> Research complete. Report saved to: {OUTPUT_PATH}

## Cookbook

### Scenario 1: Standard invocation

- **IF**: User says "deep research [topic]" with no flags
- **THEN**: Use LEAD_MODEL=claude-sonnet-4-6, OUTPUT_DIR=~/research
- **EXAMPLES**:
  - "deep research the current state of fusion energy"
  - "do deep research on Anthropic's competitors"

### Scenario 2: Complex query requiring Opus

- **IF**: User says "deep research --model opus [topic]"
- **THEN**: Use LEAD_MODEL=claude-opus-4-6
- **EXAMPLES**:
  - "deep research --model opus the geopolitical implications of rare earth mineral supply chains"

### Scenario 3: Custom output path

- **IF**: User includes `--output <path>`
- **THEN**: Use that path as OUTPUT_DIR instead of ~/research
- **EXAMPLES**:
  - "deep research --output ~/Documents/research the history of mRNA vaccines"
