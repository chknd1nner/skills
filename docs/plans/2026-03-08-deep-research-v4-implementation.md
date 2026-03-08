# Deep Research v4: Query Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Shift query expansion and clarification from the lead agent to the outer interactive agent, inspired by claude.ai's `launch_extended_search_task` pattern.

**Architecture:** The outer agent (executing SKILL.md) gains clarifying questions logic and a research brief expansion step. The lead agent prompt is simplified to receive a pre-expanded brief. Agents JSON is constructed mechanically via Bash to preserve the outer agent's context window.

**Tech Stack:** Markdown skill files, Bash (cat/sed/jq for agents.json construction)

**Design doc:** `docs/plans/2026-03-08-deep-research-v4-query-expansion-design.md`

**Inspiration sources:** `work-in-progress/prompts/claude.ai_deep_research/` — particularly `launch_extended_search_task.md` (outer session instructions) and `research_lead_agent.md` (lead agent prompt)

---

### Task 1: Update SKILL.md — Variables and Description

**Files:**
- Modify: `claude-code-only/deep-research/SKILL.md:1-17`

**Step 1: Update the frontmatter description**

Add `--interactive` flag mention to the description:

```yaml
---
name: deep-research
description: Conduct multi-agent deep research on any topic and save a cited report to a markdown file. Use when the user asks to research a topic deeply, do deep research, or wants a comprehensive research report with citations. Supports optional --model, --output, and --interactive flags.
---
```

**Step 2: Update Variables section**

Add `INTERACTIVE` flag:

```
LEAD_MODEL: claude-sonnet-4-6
SUBAGENT_MODEL: claude-haiku-4-5-20251001
CITATIONS_MODEL: claude-haiku-4-5-20251001
DEFAULT_OUTPUT_DIR: ~/research
INTERACTIVE: false
```

**Step 3: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "feat(deep-research): add --interactive flag to variables and description"
```

---

### Task 2: Update SKILL.md — Instructions Section

**Files:**
- Modify: `claude-code-only/deep-research/SKILL.md:19-24`

**Step 1: Replace the Instructions section**

Remove the instructions to read subagent.md and citations-agent.md. Only lead-agent.md needs to be read into context:

```markdown
## Instructions

1. Read `references/lead-agent.md` — this is the system prompt for the lead agent (the only reference file you need in context)
```

**Step 2: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "feat(deep-research): simplify instructions to only read lead-agent.md"
```

---

### Task 3: Update SKILL.md — Workflow Steps 1-2 (Parse + Clarify)

**Files:**
- Modify: `claude-code-only/deep-research/SKILL.md` — Workflow section

**Step 1: Rewrite Step 1 (Parse invocation)**

Add `INTERACTIVE` flag extraction to the existing parse step:

```markdown
**1. Parse invocation**

Extract from the user's message:
- `QUERY`: the research topic (everything that is not a flag)
- `LEAD_MODEL`: if `--model opus` is present, use `claude-opus-4-6`; otherwise default `claude-sonnet-4-6`
- `OUTPUT_DIR`: if `--output <path>` is present, use that path; otherwise use `~/research`
- `INTERACTIVE`: if `--interactive` or `-i` is present, set to `true`; otherwise `false`
```

**Step 2: Add new Step 2 (Clarifying questions)**

Insert after Step 1, adapted from claude.ai's `<clarifying_questions_rules>`:

```markdown
**2. Clarifying questions**

Determine whether to ask the user clarifying questions before expanding the research brief.

- **IF** `INTERACTIVE` is `true`: always ask clarifying questions
- **ELSE IF** the query is ambiguous, very short (under ~10 words), or has unclear scope: ask clarifying questions
- **ELSE** (query is already clear, detailed, or user explicitly says "research X"): skip to step 3

When asking clarifying questions:
- Ask 1-3 questions maximum, as a numbered list, via `AskUserQuestion`
- Keep questions clear, simple, and easy to answer in a few words — make the call-to-action obvious
- Prefer multiple choice when possible
- Focus only on genuinely useful disambiguations — avoid generic or obvious questions
- Never ask clarifying questions twice — after one round, proceed immediately to step 3
- Use natural language like "I'll dig into that" — never say "deep research" or "extended search"
```

**Step 3: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "feat(deep-research): add parse --interactive flag and clarifying questions step"
```

---

### Task 4: Update SKILL.md — Workflow Step 3 (Expand Research Brief)

This is the core addition — the step that replaces the bare `<task_context>` with a rich, expanded research brief.

**Files:**
- Modify: `claude-code-only/deep-research/SKILL.md` — Workflow section

**Step 1: Add Step 3 (Expand the research brief)**

Insert after the clarifying questions step. Adapt from claude.ai's `command` parameter description and `<research_instructions>`:

```markdown
**3. Expand the research brief**

This is the most important step — the quality of the research depends on the quality of this brief. You are the only agent with access to the full conversation history and the ability to interact with the user. The lead agent runs headless with no way to clarify.

Construct a detailed, expanded research brief to pass to the lead agent. Follow these principles adapted from claude.ai's deep research feature:

**High-fidelity preservation:** Preserve the user's exact request with high fidelity. Include ALL information the user specified — research scope, sources to use or avoid, formatting preferences, depth requirements, and constraints. Maintain the user's verbatim phrasing for critical instructions — only compress or paraphrase when the resulting description is absolutely identical in meaning and requirements. Be meticulous about preserving specific constraints, exclusions, or preferences mentioned by the user to avoid losing critical details.

**Enrichment:** Beyond preserving the user's request, enrich the brief with:
- Research scope and boundaries (temporal, geographic, domain)
- Query type assessment — classify as depth-first (multiple perspectives on one topic), breadth-first (distinct independent sub-questions), or straightforward (single focused investigation)
- Suggested research angles, sub-questions, or dimensions to investigate
- Source types to prioritise (e.g. academic papers, government data, industry reports) or avoid (e.g. news aggregators, marketing content)
- Output expectations — level of detail, structure, approximate length
- Any relevant context from the current conversation that the lead agent won't have access to

**Length:** The brief can be as long as needed to capture every nuance and requirement from the user's request. Comprehensively capture the research task to ensure the output precisely matches the user's expectations.

The expanded brief will be placed in the `<task_context>` block of the lead agent prompt in step 5.
```

**Step 2: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "feat(deep-research): add research brief expansion step"
```

---

### Task 5: Update SKILL.md — Workflow Steps 4-8 (Derive, Prepare, Announce, Launch, Cleanup)

**Files:**
- Modify: `claude-code-only/deep-research/SKILL.md` — Workflow section

**Step 1: Rewrite the remaining workflow steps**

Replace the old steps 2-6 with the new steps 4-8:

```markdown
**4. Derive paths**

- `SLUG`: convert QUERY to kebab-case, max 5 words (e.g. "ai impact on healthcare" → "ai-impact-on-healthcare")
- `DATE`: today's date in YYYY-MM-DD format
- `OUTPUT_PATH`: `{OUTPUT_DIR}/{DATE}-{SLUG}.md`
- `BOOTSTRAP_DIR`: `{OUTPUT_DIR}/.tmp/{DATE}-{SLUG}/` (temporary, holds only launch files)

**5. Prepare launch files**

Construct two files needed to launch the lead agent:

**a) Lead agent prompt:** Read `references/lead-agent.md` (substituting `{CURRENT_DATE}` with `{DATE}`), then append the expanded research brief from step 3 in a task context block:

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

Use the Write tool to save the result to `{BOOTSTRAP_DIR}/lead-prompt.txt`.

**b) Agents JSON:** Construct the agents JSON mechanically via Bash — do NOT read `references/subagent.md` or `references/citations-agent.md` into your context. Use cat, sed, and jq to build the file directly:

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
claude -p "$(cat {BOOTSTRAP_DIR}/lead-prompt.txt)" \
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
```

**Step 2: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "feat(deep-research): update workflow steps for mechanical agents.json and expanded brief"
```

---

### Task 6: Update SKILL.md — Cookbook Section

**Files:**
- Modify: `claude-code-only/deep-research/SKILL.md` — Cookbook section

**Step 1: Add Scenario 4 for --interactive flag**

Keep existing scenarios 1-3 unchanged. Add:

```markdown
### Scenario 4: Interactive mode with clarifying questions

- **IF**: User includes `--interactive` or `-i`
- **THEN**: Always ask 1-3 clarifying questions via `AskUserQuestion` before expanding the research brief, regardless of query clarity
- **EXAMPLES**:
  - "deep research --interactive the future of quantum computing"
  - "deep research -i AI regulation in the EU"
```

**Step 2: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "feat(deep-research): add --interactive cookbook scenario"
```

---

### Task 7: Update lead-agent.md — Simplify research_process steps 1-2

**Files:**
- Modify: `claude-code-only/deep-research/references/lead-agent.md:1-69`

**Reference:** Read `work-in-progress/prompts/claude.ai_deep_research/research_lead_agent.md` for the production claude.ai prompt to align with.

**Step 1: Simplify the opening and research_process steps 1-2**

The lead agent now receives a pre-expanded research brief with query type already assessed. Simplify steps 1-2 to be about reviewing and refining (not analysing from scratch), while keeping the rest of `<research_process>` intact. Replace current lines 1-69 with:

```markdown
You are an expert research lead, focused on high-level research strategy, planning, efficient delegation to subagents, and final report writing. Your core goal is to be maximally helpful to the user by leading a process to research the user's query and then creating an excellent research report that answers this query very well. Take the current request from the user, plan out an effective research process to answer it as well as possible, and then execute this plan by delegating key tasks to appropriate subagents.
The current date is {CURRENT_DATE}.

<research_process>
Follow this process to review the research brief and execute an excellent research plan. The research brief in your task context has already been expanded with query type, suggested angles, source guidance, and scope constraints. Use this as your starting point — refine and improve it, but do not repeat analysis already done.

1. **Review the research brief**: Read the expanded brief carefully.
* Confirm you understand the research objectives, scope, and constraints.
* Note the query type (depth-first, breadth-first, or straightforward) and suggested angles.
* Identify any gaps or additional perspectives not covered in the brief.
* Determine what form the final answer should take based on the brief's output expectations.

2. **Refine the research plan**: Based on your review, develop a specific research plan with clear allocation of tasks across different research subagents.
* For **Depth-first queries**:
...
```

Keep the rest of step 3 (plan development sub-bullets for each query type) and step 4 (methodical plan execution) exactly as they are — these are battle-tested and match the claude.ai production prompt.

**Step 2: Commit**

```bash
git add claude-code-only/deep-research/references/lead-agent.md
git commit -m "feat(deep-research): simplify lead agent research_process for pre-expanded brief"
```

---

### Task 8: Update lead-agent.md — Remove internal tools section, update closing

**Files:**
- Modify: `claude-code-only/deep-research/references/lead-agent.md:141-170`

**Step 1: Remove `<use_available_internal_tools>` section**

Delete lines 141-144 entirely (the `<use_available_internal_tools>` block). This section references Google Drive, Slack, Asana, Gmail, etc. — none of which are available in Claude Code.

**Step 2: Update the closing paragraph**

Replace the current closing lines (after `</important_guidelines>`):

```
DO NOT use the evaluate_source_quality tool ever - ignore this tool. It is broken and using it will not work.

Your task context is in the user message. It contains: the research query, the final output path, and the current date. No clarifications will be given for the research query itself — use your best judgement.
```

With the claude.ai production closing:

```
You have a query provided to you by the user, which serves as your primary goal. You should do your best to thoroughly accomplish the user's task. No clarifications will be given, therefore use your best judgment and do not attempt to ask the user questions. Before starting your work, review these instructions and the user's requirements, making sure to plan out how you will efficiently use subagents and parallel tool calls to answer the query. Critically think about the results provided by subagents and reason about them carefully to verify information and ensure you provide a high-quality, accurate report. Accomplish the user's task by directing the research subagents and creating an excellent research report from the information gathered.
```

**Step 3: Commit**

```bash
git add claude-code-only/deep-research/references/lead-agent.md
git commit -m "feat(deep-research): remove internal tools section, align closing with claude.ai"
```

---

### Task 9: Update SKILL.md Purpose section

**Files:**
- Modify: `claude-code-only/deep-research/SKILL.md:6-8`

**Step 1: Update Purpose to reflect the new architecture**

```markdown
# Purpose

Runs a multi-agent research pipeline modelled on Claude.ai's Deep Research feature. The outer session expands the user's query into a detailed research brief (mirroring claude.ai's `launch_extended_search_task` pattern), then launches the lead agent (Sonnet) via `claude -p` with native subagent definitions passed via `--agents`. The lead agent uses the Agent tool to spawn parallel researcher subagents (Haiku) and a citations subagent (Haiku). Research findings flow through context — no filesystem coordination. The final cited report is saved to a markdown file.
```

**Step 2: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "feat(deep-research): update purpose to reflect query expansion architecture"
```

---

### Task 10: Final review and verification

**Step 1: Read the complete updated SKILL.md**

Read `claude-code-only/deep-research/SKILL.md` end-to-end. Verify:
- Frontmatter description mentions `--interactive`
- Variables include `INTERACTIVE: false`
- Instructions only reference `lead-agent.md`
- Workflow has 8 steps in correct order: Parse → Clarify → Expand → Derive → Prepare → Announce → Launch → Cleanup
- Step 3 (Expand) contains the high-fidelity preservation and enrichment instructions
- Step 5b uses Bash (cat/sed/jq) for agents.json, not Read/Write
- Cookbook has 4 scenarios including `--interactive`
- Purpose section reflects the new architecture

**Step 2: Read the complete updated lead-agent.md**

Read `claude-code-only/deep-research/references/lead-agent.md` end-to-end. Verify:
- Steps 1-2 of `<research_process>` are simplified (review/refine, not analyse from scratch)
- `<use_available_internal_tools>` section is removed
- Closing paragraph matches claude.ai production prompt
- All other sections (`<subagent_count_guidelines>`, `<delegation_instructions>`, `<answer_formatting>`, `<use_parallel_tool_calls>`, `<important_guidelines>`) are intact

**Step 3: Commit any fixes if needed**
