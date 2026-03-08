---
name: deep-research
description: Conduct multi-agent deep research on any topic and save a cited report to a markdown file. Use when the user asks to research a topic deeply, do deep research, or wants a comprehensive research report with citations. Supports optional --model, --output, and --interactive flags.
---

# Purpose

Runs a multi-agent research pipeline modelled on Claude.ai's Deep Research feature. The outer session expands the user's query into a detailed research brief (mirroring claude.ai's launch_extended_search_task pattern), then launches the lead agent (Sonnet) via `claude -p` with native subagent definitions passed via `--agents`. The lead agent uses the Agent tool to spawn parallel researcher subagents (Haiku) and a citations subagent (Haiku). Research findings flow through context — no filesystem coordination. The final cited report is saved to a markdown file.

## Variables

```
LEAD_MODEL: claude-sonnet-4-6
SUBAGENT_MODEL: claude-haiku-4-5-20251001
CITATIONS_MODEL: claude-haiku-4-5-20251001
DEFAULT_OUTPUT_DIR: ~/research
INTERACTIVE: false
```

## Instructions

1. Read `references/lead-agent.md` — this is the system prompt for the lead agent (the only reference file you need in context)

## Workflow

When the skill is invoked:

**1. Parse invocation**

Extract from the user's message:
- `QUERY`: the research topic (everything that is not a flag)
- `LEAD_MODEL`: if `--model opus` is present, use `claude-opus-4-6`; otherwise default `claude-sonnet-4-6`
- `OUTPUT_DIR`: if `--output <path>` is present, use that path; otherwise use `~/research`
- `INTERACTIVE`: if `--interactive` or `-i` is present, set to `true`; otherwise default `false`

**2. Clarifying questions**

- **IF** `INTERACTIVE` is `true`: always ask clarifying questions before proceeding.
- **ELSE IF** the query is ambiguous, very short (under ~10 words), or has unclear scope: ask clarifying questions.
- **ELSE**: skip to step 3.

Rules for clarifying questions:
- Ask a maximum of 3 questions, presented as a numbered list.
- Use AskUserQuestion to collect answers.
- Questions should be easy to answer in a few words; prefer multiple-choice options where possible.
- Never ask the same question twice.
- Use natural, conversational language — never say "deep research" or "extended search" in the questions.

**3. Expand the research brief**

This is the most important step. Build a detailed research brief that will be passed to the lead agent in place of the raw query.

*High-fidelity preservation* — the brief must retain:
- The user's exact request and verbatim phrasing for critical instructions.
- All constraints, exclusions, and preferences stated by the user.

*Enrichment* — augment the query with:
- Research scope and boundaries.
- Query type assessment: depth-first (deep dive into one area), breadth-first (survey across many areas), or straightforward (factual/well-scoped).
- Suggested angles and sub-questions worth investigating.
- Source types to prioritise or avoid.
- Output expectations (length, format, audience).
- Any conversation context the lead agent will not have.

The brief can be as long as needed to fully capture the above.

**4. Derive paths**

- `SLUG`: convert QUERY to kebab-case, max 5 words (e.g. "ai impact on healthcare" -> "ai-impact-on-healthcare")
- `DATE`: today's date in YYYY-MM-DD format
- `OUTPUT_PATH`: `{OUTPUT_DIR}/{DATE}-{SLUG}.md`
- `BOOTSTRAP_DIR`: `{OUTPUT_DIR}/.tmp/{DATE}-{SLUG}/` (temporary, holds only launch files)

**5. Prepare launch files**

Construct two files needed to launch the lead agent:

**a) Lead agent prompt:** Read `references/lead-agent.md` (substituting `{CURRENT_DATE}` with `{DATE}`), then append the expanded research brief as a task context block:

```
---

<task_context>
Current date: {DATE}
Final output path: {OUTPUT_PATH}

<research_brief>
{EXPANDED_BRIEF}
</research_brief>
</task_context>
```

Use the Write tool to save the result to `{BOOTSTRAP_DIR}/lead-prompt.txt` — this implicitly creates `{BOOTSTRAP_DIR}`.

**b) Agents JSON:** Construct the agents JSON via Bash using cat/sed/jq — do NOT read `references/subagent.md` or `references/citations-agent.md` into context. Use the following pattern:

```bash
SKILL_DIR="<absolute path to claude-code-only/deep-research>"
DATE="{DATE}"
jq -n \
  --arg sub "$(sed "s/{CURRENT_DATE}/$DATE/g" "$SKILL_DIR/references/subagent.md")" \
  --arg cit "$(cat "$SKILL_DIR/references/citations-agent.md")" \
  '{
    researcher: {
      description: "Research subagent for deep research tasks. Spawned by the lead agent to investigate specific research questions.",
      prompt: $sub,
      tools: ["WebSearch", "WebFetch", "Read", "Bash"],
      model: "haiku"
    },
    citations: {
      description: "Citations agent for resolving citation markers in research reports. Spawned by the lead agent after draft synthesis.",
      prompt: $cit,
      model: "haiku"
    }
  }' > "{BOOTSTRAP_DIR}/agents.json"
```

**6. Announce**

Tell the user:
> Starting deep research on: "{QUERY}"
> Lead model: {LEAD_MODEL} | Subagents: {SUBAGENT_MODEL}
> Report will be saved to: {OUTPUT_PATH}

**7. Launch lead agent**

Run the lead agent via Bash:

```bash
unset CLAUDECODE && cclaude -p "$(cat {BOOTSTRAP_DIR}/lead-prompt.txt)" \
  --model {LEAD_MODEL} \
  --tools "Agent,WebSearch,WebFetch,Write,Read,Bash" \
  --agents "$(cat {BOOTSTRAP_DIR}/agents.json)" \
  --dangerously-skip-permissions \
  --no-session-persistence 2>&1
```

The lead agent uses the Agent tool to spawn researcher and citations subagents internally. Wait for it to complete — it writes the final cited report to `{OUTPUT_PATH}` before finishing.

**8. Confirm and clean up**

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

### Scenario 4: Interactive mode

- **IF**: User includes `--interactive` or `-i`
- **THEN**: Always ask 1-3 clarifying questions before expanding the research brief
- **EXAMPLES**:
  - "deep research --interactive the future of quantum computing"
  - "deep research -i renewable energy trends"
