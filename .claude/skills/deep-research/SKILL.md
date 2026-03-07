---
name: deep-research
description: Conduct multi-agent deep research on any topic and save a cited report to a markdown file. Use when the user asks to research a topic deeply, do deep research, or wants a comprehensive research report with citations. Supports optional --model and --output flags.
---

# Purpose

Runs a multi-agent research pipeline modelled on Claude.ai's Deep Research feature. The outer session launches the lead agent (Sonnet) via `claude -p --dangerously-skip-permissions`. The lead agent plans the research, launches parallel `claude -p` research subprocesses (Haiku) via Bash, synthesises their findings into a draft report with `[^?]` citation markers, then launches a `claude -p` citations subprocess (Haiku) for surgical footnote insertion, and finally cleans up tmp files. The final cited report is saved to a markdown file.

## Variables

```
LEAD_MODEL: claude-haiku-4-5-20251001
SUBAGENT_MODEL: claude-haiku-4-5-20251001
CITATIONS_MODEL: claude-haiku-4-5-20251001
DEFAULT_OUTPUT_DIR: ~/research
```

## Instructions

1. Read `references/lead-agent.md` — this is the prompt for the lead agent
2. Read `references/subagent.md` and resolve its absolute path — included in the task context passed to the lead agent, which uses it as `--system-prompt-file` when launching research subprocesses
3. Read `references/citations-agent.md` and resolve its absolute path — same: passed to lead agent in task context for use as `--system-prompt-file` with the citations subprocess

## Workflow

When the skill is invoked:

**1. Parse invocation**

Extract from the user's message:
- `QUERY`: the research topic (everything that is not a flag)
- `LEAD_MODEL`: if `--model opus` is present, use `claude-opus-4-6`; otherwise default `claude-haiku-4-5-20251001`
- `OUTPUT_DIR`: if `--output <path>` is present, use that path; otherwise use `~/research`

**2. Derive paths**

- `SLUG`: convert QUERY to kebab-case, max 5 words (e.g. "ai impact on healthcare" → "ai-impact-on-healthcare")
- `DATE`: today's date in YYYY-MM-DD format
- `OUTPUT_PATH`: `{OUTPUT_DIR}/{DATE}-{SLUG}.md`
- `TMP_DIR`: `{OUTPUT_DIR}/.tmp/{DATE}-{SLUG}/`
- `DRAFT_PATH`: `{TMP_DIR}/draft-report.md`

**3. Prepare lead agent prompt**

Construct the full lead agent prompt: take the contents of `references/lead-agent.md` (substituting `{CURRENT_DATE}` with `{DATE}`), then append the task context block below. Use the Write tool to save the result to `{TMP_DIR}/lead-prompt.txt` — this implicitly creates `{TMP_DIR}`.

```
---

<task_context>
Current date: {DATE}
Research query: {QUERY}
Draft output path: {DRAFT_PATH}
Final output path: {OUTPUT_PATH}
Tmp directory: {TMP_DIR}
Absolute path to subagent.md: {ABS_PATH_SUBAGENT_MD}
Absolute path to citations-agent.md: {ABS_PATH_CITATIONS_MD}
</task_context>
```

**4. Announce**

Tell the user:
> Starting deep research on: "{QUERY}"
> Lead model: {LEAD_MODEL} | Subagents: {SUBAGENT_MODEL}
> Report will be saved to: {OUTPUT_PATH}

**5. Launch lead agent**

Run the lead agent via Bash:

```bash
claude -p "$(cat {TMP_DIR}/lead-prompt.txt)" \
  --model {LEAD_MODEL} \
  --tools "WebSearch,WebFetch,Write,Read,Bash" \
  --dangerously-skip-permissions \
  --no-session-persistence 2>&1
```

The lead agent handles all research, synthesis, citations, and tmp cleanup internally. Wait for it to complete — it writes the final cited report to `{OUTPUT_PATH}` before finishing.

**6. Confirm**

Tell the user:
> Research complete. Report saved to: {OUTPUT_PATH}

## Cookbook

### Scenario 1: Standard invocation

- **IF**: User says "deep research [topic]" with no flags
- **THEN**: Use LEAD_MODEL=claude-haiku-4-5-20251001, OUTPUT_DIR=~/research
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
