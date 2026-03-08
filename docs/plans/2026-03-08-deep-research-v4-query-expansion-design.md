# Deep Research v4: Query Expansion Design

Date: 2026-03-08

## Problem

The current deep-research skill passes the user's raw query directly to the lead agent with minimal context. On claude.ai, the outer session does significant work *before* launching the research agent — it silently expands the user's request into a detailed, high-fidelity research brief (the `command` parameter of `launch_extended_search_task`). It also conditionally asks clarifying questions when the query is ambiguous.

Our skill skips both of these steps. The lead agent receives a bare query and must do all the analysis itself — without access to conversation history or the ability to ask the user for clarification.

## Solution

Shift query expansion and clarification responsibilities from the lead agent to the outer interactive agent (the one executing SKILL.md). The outer agent has conversation context, can interact with the user via `AskUserQuestion`, and produces a much richer research brief. The lead agent receives a pre-expanded, pre-typed brief and focuses on plan execution and synthesis.

## Architecture

```
User invokes /deep-research
  │
  ├─ 1. Parse invocation (QUERY, flags)
  │
  ├─ 2. Clarifying questions (conditional)
  │     IF --interactive OR query is ambiguous:
  │       Ask 1-3 questions via AskUserQuestion
  │     ELSE: skip
  │
  ├─ 3. Expand research brief (NEW — core addition)
  │     Outer agent constructs detailed research brief:
  │     - User's verbatim query
  │     - Research scope, angles, sub-questions
  │     - Source guidance, constraints
  │     - Output expectations
  │     - Conversation context
  │
  ├─ 4. Read lead-agent.md
  │
  ├─ 5. Prepare launch files
  │     - lead-prompt.txt: lead-agent.md + expanded brief in <task_context>
  │     - agents.json: constructed via Bash (cat + sed + jq)
  │       No Read of subagent.md or citations-agent.md into context
  │
  ├─ 6. Announce
  │
  ├─ 7. Launch lead agent (claude -p --agents ...)
  │
  └─ 8. Confirm and clean up
```

## Key Design Decisions

### 1. Outer agent does the query expansion

Inspired by claude.ai's `launch_extended_search_task` tool, where the `command` parameter description instructs the outer Claude to:
- Preserve the user's exact request with high fidelity
- Include ALL information: research scope, sources to use/avoid, formatting preferences, depth requirements, constraints
- Maintain verbatim phrasing for critical instructions
- Be meticulous about preserving constraints, exclusions, or preferences
- Make the brief as long as needed to capture every nuance

The outer agent is the only point with conversation history and user interaction capability. This is where the expansion must happen.

### 2. Conditional clarifying questions

Adapted from claude.ai's `<clarifying_questions_rules>`:
- **Default:** Skip clarification if the query is already clear, detailed, or the user explicitly says "research X"
- **`--interactive` flag:** Always ask 1-3 clarifying questions before expanding
- Rules: max 3 questions, numbered list, easy to answer in a few words, never ask twice — after one round, proceed immediately
- Future: `--interactive` could also reveal the expanded brief for user review before launch

### 3. Mechanical agents.json construction

The outer agent does NOT read `subagent.md` or `citations-agent.md` into its context. Instead, it constructs `agents.json` via Bash:

```bash
DATE="2026-03-08"
SUBAGENT=$(cat references/subagent.md | sed "s/{CURRENT_DATE}/$DATE/g")
CITATIONS=$(cat references/citations-agent.md)
jq -n --arg sub "$SUBAGENT" --arg cit "$CITATIONS" \
  '{researcher: {description: "...", prompt: $sub, tools: [...], model: "haiku"},
    citations: {description: "...", prompt: $cit, model: "haiku"}}' \
  > agents.json
```

This preserves the outer agent's context window for what matters — the conversation history and expansion logic.

### 4. Lead agent prompt simplified

The lead-agent.md is brought closer to the claude.ai production `research_lead_agent.md` with these changes:

**Removed:**
- `<use_available_internal_tools>` — irrelevant in Claude Code (no Google Drive, Slack, etc.)
- Heavy query type determination in steps 1-2 — the brief already contains this

**Simplified:**
- `<research_process>` steps 1-2 become "review and refine the research brief" rather than "analyse from scratch"
- The lead agent still does its own assessment but starts from a much stronger position

**Kept as-is:**
- `<subagent_count_guidelines>`
- `<delegation_instructions>` (already adapted for Agent tool)
- `<answer_formatting>` (citations agent flow)
- `<use_parallel_tool_calls>`
- `<important_guidelines>`

**Changed closing:**
- "You have a query provided to you by the user, which serves as your primary goal. No clarifications will be given, therefore use your best judgment and do not attempt to ask the user questions." (matches claude.ai production prompt)

### 5. SKILL.md format unchanged

The existing template format (Variables / Instructions / Workflow / Cookbook) fits well. The expansion logic lives in the Workflow section. `--interactive` joins the existing flags in Variables and gets a new Cookbook scenario.

## Files Changed

### SKILL.md
- **Variables:** Add `INTERACTIVE: false` flag
- **Instructions:** Only read `lead-agent.md` (not subagent/citations prompts)
- **Workflow Step 2 (new):** Clarifying questions logic adapted from claude.ai `<clarifying_questions_rules>`
- **Workflow Step 3 (new):** Research brief expansion logic adapted from claude.ai `command` parameter principles
- **Workflow Step 5:** Agents JSON constructed via Bash (cat + sed + jq), not Read + Write
- **Cookbook:** Add Scenario 4 for `--interactive` flag

### lead-agent.md
- Remove `<use_available_internal_tools>` section
- Simplify `<research_process>` steps 1-2 (brief is pre-expanded)
- Update closing paragraph to match claude.ai production prompt (no clarifications given)
- Keep all other sections faithful to claude.ai production prompt

### No changes
- `subagent.md` — already close to claude.ai production prompt
- `citations-agent.md` — already close to claude.ai production prompt

## Inspiration Sources

All claude.ai production prompts are in `work-in-progress/prompts/claude.ai_deep_research/`:
- `launch_extended_search_task.md` — tool definition and outer session instructions
- `research_lead_agent.md` — lead agent system prompt
- `research_subagent.md` — subagent system prompt
- `citations_agent.md` — citations agent system prompt
