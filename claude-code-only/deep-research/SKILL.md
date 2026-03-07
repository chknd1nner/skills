---
name: deep-research
description: Conduct multi-agent deep research on any topic and save a cited report to a markdown file. Use when the user asks to research a topic deeply, do deep research, or wants a comprehensive research report with citations. Supports optional --model and --output flags.
---

# Purpose

Runs a multi-agent research pipeline modelled on Claude.ai's Deep Research feature. A lead agent (Sonnet) plans the research, dispatches parallel research subagents (Haiku) to search and gather sources, synthesises their findings into a draft report with `[^?]` citation markers, then passes the draft to a citations agent (Haiku) for surgical footnote insertion. The final cited report is saved to a markdown file.

## Variables

```
LEAD_MODEL: claude-sonnet-4-6
SUBAGENT_MODEL: claude-haiku-4-5-20251001
CITATIONS_MODEL: claude-haiku-4-5-20251001
DEFAULT_OUTPUT_DIR: ~/research
```

## Instructions

1. Read `references/lead-agent.md` — this is the prompt for the lead agent
2. Read `references/subagent.md` — the lead agent passes this verbatim to each research subagent
3. Read `references/citations-agent.md` — the lead agent passes this to the citations agent

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
- `TMP_DIR`: `{OUTPUT_DIR}/.tmp/{DATE}-{SLUG}/`
- `DRAFT_PATH`: `{TMP_DIR}/draft-report.md`

**3. Create directories**

Use Bash to create the output and tmp directories:

```bash
mkdir -p {OUTPUT_DIR}/.tmp/{DATE}-{SLUG}
```

**4. Announce**

Tell the user:
> Starting deep research on: "{QUERY}"
> Lead model: {LEAD_MODEL} | Subagents: {SUBAGENT_MODEL}
> Report will be saved to: {OUTPUT_PATH}

**5. Spawn lead agent**

Read `references/lead-agent.md` and `references/subagent.md`. Invoke the Agent tool with:
- `model`: the resolved LEAD_MODEL
- `prompt`: the full contents of `references/lead-agent.md`, followed by the task context block below

The task context block to append:

```
---

<task_context>
Current date: {DATE}
Research query: {QUERY}
Draft output path: {DRAFT_PATH}
Final output path: {OUTPUT_PATH}
Tmp directory: {TMP_DIR}
Subagent model: {SUBAGENT_MODEL}
Citations model: {CITATIONS_MODEL}

Subagent prompt — pass this verbatim to each Agent tool call for research subagents, appending the specific task description and assigned tmp filepath at the end:
---
{full contents of references/subagent.md}
---
</task_context>

Your research query is: {QUERY}
```

Wait for the lead agent to complete. It will write `{DRAFT_PATH}` before finishing.

**6. Spawn citations agent**

Read `references/citations-agent.md`. Invoke the Agent tool with:
- `model`: `claude-haiku-4-5-20251001`
- `prompt`: the full contents of `references/citations-agent.md`, with `{TASK_CONTEXT}` replaced by:

```
Resolve all [^?] markers in the draft report and add citations. Draft report path: {DRAFT_PATH}. Subagent source files are in: {TMP_DIR}. Write the final cited report to: {OUTPUT_PATH}.
```

Wait for the citations agent to complete.

**7. Cleanup and confirm**

```bash
rm -rf {TMP_DIR}
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
