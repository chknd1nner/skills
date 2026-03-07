# Deep Research Skill — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a `claude-code-only/deep-research` skill that runs a multi-agent research pipeline and saves a cited markdown report to `~/research/`.

**Architecture:** The skill instructs Claude to spawn a lead agent (Sonnet) via the `Agent` tool. The lead agent plans the research, spawns parallel research subagents (Haiku) that write findings to tmp files, synthesises a draft with `[^?]` citation markers, then spawns a citations agent (Haiku) that surgically replaces markers with footnotes using `Edit` tool calls.

**Tech Stack:** Claude Code skill (SKILL.md + reference prompt files). No scripts. Filesystem as coordination layer.

**Design doc:** `docs/plans/2026-03-07-deep-research-design.md`

**Source prompts (read-only reference):** `work-in-progress/prompts/claude.ai_deep_research/`

---

### Task 1: Create directory structure

**Files:**
- Create: `claude-code-only/deep-research/SKILL.md` (empty placeholder)
- Create: `claude-code-only/deep-research/references/lead-agent.md` (empty placeholder)
- Create: `claude-code-only/deep-research/references/subagent.md` (empty placeholder)
- Create: `claude-code-only/deep-research/references/citations-agent.md` (empty placeholder)

**Step 1: Create directories**

```bash
mkdir -p claude-code-only/deep-research/references
```

**Step 2: Verify structure**

```bash
ls claude-code-only/deep-research/references/
```

Expected: empty directory exists with no errors.

**Step 3: Commit**

```bash
git add claude-code-only/deep-research/
git commit -m "feat(deep-research): scaffold skill directory structure"
```

---

### Task 2: Write `references/lead-agent.md`

This is adapted from `work-in-progress/prompts/claude.ai_deep_research/research_lead_agent.md`. Read that file first to understand the original, then apply the changes below.

**Files:**
- Source: `work-in-progress/prompts/claude.ai_deep_research/research_lead_agent.md`
- Create: `claude-code-only/deep-research/references/lead-agent.md`

**Step 1: Read the source file**

Read `work-in-progress/prompts/claude.ai_deep_research/research_lead_agent.md` in full.

**Step 2: Write the adapted file**

Start from the source and apply these changes:

| Find | Replace with |
|---|---|
| `{{.CurrentDate}}` | `{CURRENT_DATE}` |
| `run_blocking_subagent` (tool name in prose) | `Agent` |
| `web_search` (tool name in prose) | `WebSearch` |
| `web_fetch` (tool name in prose) | `WebFetch` |
| `complete_task` (tool name in prose) | `Write` |
| Any reference to the `repl` tool | Remove the sentence/bullet |

**Additionally, replace the `<answer_formatting>` section** with:

```
<answer_formatting>
Before providing a final answer:
1. Review the findings compiled from all subagent tmp files.
2. Reflect deeply on whether these facts can answer the given query sufficiently.
3. Write your final draft report in Markdown, inserting [^?] at the end of any sentence derived from a specific source. The citations agent will resolve these markers — do not include a References section yourself.
4. Use the Write tool to save the draft to: {DRAFT_PATH}
</answer_formatting>
```

**Replace the final paragraph** ("You have a query provided to you...") with:

```
You have been given a research query, a draft output path, a tmp directory path, and a subagent model to use. Your task context is provided below. No clarifications will be given for the research query itself — use your best judgement. However, if the invocation flags or paths are missing or ambiguous, you may ask for clarification.

<task_context>
{TASK_CONTEXT}
</task_context>

Your research query is: {QUERY}
```

**Replace the `<delegation_instructions>` tool usage** — wherever it says to use `run_blocking_subagent`, update to:

```
* Use the `Agent` tool to create a research subagent. Pass the full contents of the subagent prompt (provided in your task context) in the `prompt` parameter, appending the subagent's specific task, its assigned tmp filepath, and today's date.
* Set `model: {SUBAGENT_MODEL}` on every Agent tool call for research subagents.
```

**Keep verbatim** (do not change):
- The entire `<research_process>` section (query type reasoning, depth/breadth/straightforward logic)
- The entire `<subagent_count_guidelines>` section
- The `<use_parallel_tool_calls>` section
- The `<important_guidelines>` section
- The `<use_available_internal_tools>` section
- The line: `DO NOT use the evaluate_source_quality tool ever - ignore this tool. It is broken and using it will not work.`

**Step 3: Verify**

Read back the file. Confirm:
- No `{{.CurrentDate}}` remains
- No `run_blocking_subagent` remains
- No `complete_task` remains
- `[^?]` marker instruction is present in `<answer_formatting>`
- `evaluate_source_quality` DO NOT USE line is present

**Step 4: Commit**

```bash
git add claude-code-only/deep-research/references/lead-agent.md
git commit -m "feat(deep-research): add adapted lead agent prompt"
```

---

### Task 3: Write `references/subagent.md`

Adapted from `work-in-progress/prompts/claude.ai_deep_research/research_subagent.md`.

**Files:**
- Source: `work-in-progress/prompts/claude.ai_deep_research/research_subagent.md`
- Create: `claude-code-only/deep-research/references/subagent.md`

**Step 1: Read the source file**

Read `work-in-progress/prompts/claude.ai_deep_research/research_subagent.md` in full.

**Step 2: Write the adapted file**

Apply these changes:

| Find | Replace with |
|---|---|
| `web_search` (tool name in prose) | `WebSearch` |
| `web_fetch` (tool name in prose) | `WebFetch` |
| `complete_task` (tool name in prose) | `Write` |
| Any reference to the `repl` tool | Remove the sentence/bullet |
| `evaluate_source_quality` DO NOT USE line | Keep verbatim |

**Replace the final paragraph** (starting "Follow the `<research_process>`...") with:

```
Follow the <research_process> and <research_guidelines> above to accomplish your task, parallelising tool calls for maximum efficiency. Use WebFetch to retrieve full page contents after WebSearch — never rely on snippets alone. Continue until all necessary information is gathered.

When your research is complete, use the Write tool to save your findings as a detailed markdown report to the filepath specified in your task. Include all source URLs inline as markdown links so the citations agent can reference them. Do not summarise excessively — the lead agent needs dense, factual findings.

Your task and output filepath are specified below:

<task>
{TASK}
</task>
```

**Keep verbatim:**
- The entire `<research_process>` section (planning, OODA loop, research budget)
- The entire `<research_guidelines>` section
- The `<think_about_source_quality>` section
- The `<use_parallel_tool_calls>` section
- The `<maximum_tool_call_limit>` section
- The `evaluate_source_quality` DO NOT USE line

**Step 3: Verify**

Read back the file. Confirm:
- No `complete_task` remains
- No `repl` tool references remain
- Write tool instruction with filepath placeholder is present
- `evaluate_source_quality` DO NOT USE line is present

**Step 4: Commit**

```bash
git add claude-code-only/deep-research/references/subagent.md
git commit -m "feat(deep-research): add adapted research subagent prompt"
```

---

### Task 4: Write `references/citations-agent.md`

This requires the most significant adaptation — the original is heavily Claude.ai-specific.

**Files:**
- Source: `work-in-progress/prompts/claude.ai_deep_research/citations_agent.md`
- Create: `claude-code-only/deep-research/references/citations-agent.md`

**Step 1: Read the source file**

Read `work-in-progress/prompts/claude.ai_deep_research/citations_agent.md` in full.

**Step 2: Write the adapted file**

The adapted citations-agent.md should read as follows (rewrite substantially, preserving the citation philosophy prose):

```markdown
You are an agent responsible for adding correct citations to a research report. You have been given a draft report file path and a tmp directory containing the research subagent findings that the report was synthesised from.

Your task is to enhance trust in the report by replacing `[^?]` placeholder markers with resolved markdown footnotes, then appending a `## References` section.

**How to proceed:**

1. Use the Read tool to read the draft report at: {DRAFT_PATH}
2. Use the Read tool to read each subagent findings file in: {TMP_DIR}
3. Process the draft in document order. For each `[^?]` marker:
   - Identify the claim in the surrounding sentence
   - Find the source URL in the subagent findings that supports this claim
   - Use the Edit tool to surgically replace that specific `[^?]` with `[^N]` where N is the next footnote number in sequence
   - Track the URL for the References section
4. After all markers are resolved, append a `## References` section to the draft file using the Edit tool or Write tool, with one footnote definition per line:
   ```
   [^1]: [Page Title](https://url) — brief description of source
   [^2]: [Page Title](https://url) — brief description of source
   ```
5. Confirm completion by outputting the final output path and the number of citations added.

**Citation guidelines — preserve these from the original design:**

- **Avoid citing unnecessarily**: Not every statement needs a citation. Focus on citing key facts, conclusions, and substantive claims linked to sources rather than common knowledge. Prioritise claims readers would want to verify.
- **Cite meaningful semantic units**: Citations should span complete thoughts or claims. Avoid citing individual words or small phrase fragments. Prefer adding citations at the end of sentences.
- **Minimise sentence fragmentation**: Avoid multiple citations within a single sentence. Only add citations between phrases when necessary to attribute specific claims to specific sources.
- **No redundant citations close together**: Do not place multiple citations to the same source in the same sentence. Use a single citation at the end if multiple claims in one sentence share a source.

**Technical requirements:**

- Do NOT modify the report text in any way — only replace `[^?]` markers and append the References section
- Each Edit call should be surgical: change only the `[^?]` to `[^N]`, nothing else
- Preserve all whitespace and formatting exactly
- If a `[^?]` marker cannot be matched to a source in the subagent findings, replace it with `[^?]` still (leave unresolved) and note it in your completion summary

**Your task context:**

<task_context>
{TASK_CONTEXT}
</task_context>
```

**Step 3: Verify**

Read back the file. Confirm:
- No `<cite>` tags
- No `<exact_text_with_citation>` tags
- No `<synthesized_text>` tags
- Edit tool-based surgical replacement is described
- `[^?]` → `[^N]` mechanism is clear
- Citation philosophy bullets are present

**Step 4: Commit**

```bash
git add claude-code-only/deep-research/references/citations-agent.md
git commit -m "feat(deep-research): add adapted citations agent prompt"
```

---

### Task 5: Write `SKILL.md`

The main skill entry point. This is a new file with no source to adapt from.

**Files:**
- Create: `claude-code-only/deep-research/SKILL.md`

**Step 1: Write the file**

```markdown
---
name: deep-research
description: Conduct multi-agent deep research on any topic and save a cited report to a markdown file. Use when the user asks to research a topic deeply, do deep research, or wants a comprehensive research report with citations. Supports optional --model and --output flags.
---

# Purpose

Runs a multi-agent research pipeline modelled on Claude.ai's Deep Research feature. A lead agent (Sonnet) plans the research, dispatches parallel research subagents (Haiku) to search and gather sources, synthesises their findings into a draft report, then passes the draft to a citations agent (Haiku) for surgical footnote insertion. The final cited report is saved to a markdown file.

## Variables

```
LEAD_MODEL: claude-sonnet-4-6
SUBAGENT_MODEL: claude-haiku-4-5-20251001
CITATIONS_MODEL: claude-haiku-4-5-20251001
DEFAULT_OUTPUT_DIR: ~/research
```

## Instructions

1. Read `references/lead-agent.md` — this is the prompt for the lead agent
2. Read `references/subagent.md` — the lead agent passes this to each research subagent
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

Read `references/lead-agent.md` and `references/subagent.md`. Invoke the Agent tool:

```
tool: Agent
model: {LEAD_MODEL}
prompt: |
  {full contents of references/lead-agent.md}

  ---

  <task_context>
  Current date: {DATE}
  Research query: {QUERY}
  Output path (draft): {DRAFT_PATH}
  Final output path: {OUTPUT_PATH}
  Tmp directory: {TMP_DIR}
  Subagent model: {SUBAGENT_MODEL}
  Citations model: {CITATIONS_MODEL}

  Subagent prompt (pass this verbatim to each Agent call for research subagents,
  appending the specific task and assigned tmp filepath at the end):
  ---
  {full contents of references/subagent.md}
  ---
  </task_context>

  Your research query is: {QUERY}
```

Wait for the lead agent to complete. It will write `{DRAFT_PATH}` before finishing.

**6. Spawn citations agent**

Read `references/citations-agent.md`. Invoke the Agent tool:

```
tool: Agent
model: {CITATIONS_MODEL}
prompt: |
  {full contents of references/citations-agent.md, with placeholders filled:}
  - {DRAFT_PATH} → actual draft path
  - {TMP_DIR} → actual tmp directory
  - {TASK_CONTEXT} → "Resolve all [^?] markers in the draft report at {DRAFT_PATH}.
     Subagent source files are in {TMP_DIR}. Write the final cited report to {OUTPUT_PATH}."
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
```

**Step 2: Verify**

Read back the file. Confirm:
- YAML frontmatter is valid
- All three models are referenced correctly
- Workflow steps 1–7 are all present
- The lead agent prompt construction includes the subagent prompt verbatim
- Both cookbook scenarios are present

**Step 3: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "feat(deep-research): add SKILL.md entry point"
```

---

### Task 6: End-to-end smoke test

Run the skill with a simple, fast-to-research query to verify the pipeline works.

**Step 1: Ensure ~/research exists**

```bash
mkdir -p ~/research
```

**Step 2: Invoke the skill**

In a Claude Code session, invoke:

```
deep research the population of Tokyo
```

(Straightforward query → should spawn 1 subagent, fast to complete.)

**Step 3: Verify pipeline execution**

Watch for:
- Lead agent spawned ✓
- At least 1 research subagent spawned ✓
- Subagent writes to `~/research/.tmp/.../subagent-1.md` ✓
- Lead agent writes draft to `~/research/.tmp/.../draft-report.md` ✓
- Citations agent spawned ✓
- Citations agent makes Edit calls replacing `[^?]` markers ✓
- `~/research/` contains the final `.md` file ✓
- Tmp directory cleaned up ✓

**Step 4: Verify output file**

```bash
ls ~/research/
cat ~/research/*.md
```

Expected: a readable markdown file with:
- At least one `## References` section
- No remaining `[^?]` markers
- Numbered footnotes `[^1]`, `[^2]`, etc.

**Step 5: Commit smoke test notes (optional)**

If any prompt adjustments were needed during testing, commit the fixes:

```bash
git add claude-code-only/deep-research/
git commit -m "fix(deep-research): prompt adjustments from smoke test"
```

---

### Task 7: Final commit and cleanup

**Step 1: Verify all files present**

```bash
ls -R claude-code-only/deep-research/
```

Expected:
```
claude-code-only/deep-research/:
SKILL.md  references/

claude-code-only/deep-research/references/:
citations-agent.md  lead-agent.md  subagent.md
```

**Step 2: Mark work-in-progress prompts as implemented**

The source prompts in `work-in-progress/prompts/claude.ai_deep_research/` can stay as-is — they are the original reference material and should not be deleted.

**Step 3: Final commit if anything outstanding**

```bash
git status
git add -p  # review and stage any remaining changes
git commit -m "feat(deep-research): complete skill implementation"
```
