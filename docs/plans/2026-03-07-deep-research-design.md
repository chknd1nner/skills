# Deep Research Skill — Design

**Date:** 2026-03-07
**Status:** Approved, ready for implementation

---

## Overview

A Claude Code skill that replicates Claude.ai's Deep Research feature: a multi-agent research pipeline that plans, researches, synthesises, and cites — saving the final report to a markdown file.

---

## Architecture

**Approach: Delegated lead agent (nested agents)**

The skill kicks off a dedicated lead agent via the `Agent` tool. The lead agent is responsible for all orchestration. Claude's main context is kept clean — it just invokes the lead agent and waits.

```
User invokes skill
  └─ Agent (lead agent)
        ├─ Plans research (query type: depth-first / breadth-first / straightforward)
        ├─ Spawns parallel Agent calls (research subagents)
        │     └─ Each subagent: WebSearch + WebFetch → writes findings to tmp file
        ├─ Reads all tmp files → synthesises → writes draft report (with [^?] markers)
        └─ Agent (citations agent)
              └─ Reads draft + tmp files → surgical Edit calls → appends References section
                    └─ Cleanup tmp directory
```

The filesystem is the coordination layer between agents — a pattern consistent with orchestration harnesses like RALPH loops.

---

## Output

- **Final report:** `~/research/YYYY-MM-DD-topic-slug.md` (default)
- **User-specified path:** supported at invocation time — overrides the default
- **Topic slug:** derived by the lead agent from the research query (kebab-case, max 5 words)

---

## File Structure (runtime)

```
~/research/
  2026-03-07-topic-slug.md          ← final report (with citations)
  .tmp/
    2026-03-07-topic-slug/
      subagent-1.md                 ← findings from research subagent 1
      subagent-2.md                 ← findings from research subagent 2
      subagent-N.md
      draft-report.md               ← lead agent's synthesis (pre-citation)
```

The `.tmp/` directory is deleted after the citations pass completes.

---

## Skill File Structure

```
claude-code-only/deep-research/
  SKILL.md
  references/
    lead-agent.md
    subagent.md
    citations-agent.md
```

Lives in `claude-code-only/` — requires `Agent`, `WebSearch`, `WebFetch`, and filesystem tools unavailable in Claude.ai.

---

## Prompt Adaptation

The reference prompts are adapted from Anthropic's Claude.ai production prompts. The goal is to preserve as much original language as possible — these are known-good, production-grade prompts. Only tool names and output mechanisms are changed.

### `lead-agent.md` (from `research_lead_agent.md`)

| Original | Adapted |
|---|---|
| `{{.CurrentDate}}` | Injected at skill invocation from `currentDate` in CLAUDE.md |
| `run_blocking_subagent` tool | `Agent` tool |
| `complete_task` tool | `Write` tool — write draft to `.tmp/.../draft-report.md` |
| `web_search` | `WebSearch` |
| `web_fetch` | `WebFetch` |
| `repl` tool | Removed — Claude can do simple calculations natively |
| `evaluate_source_quality` tool | Keep the DO NOT USE line verbatim (see note below) |
| Google Suite / Slack / Asana / GitHub tools | Keep conditionally — available if user has MCP integrations configured |
| "No clarifications will be given" | Relaxed — Claude Code supports `AskUserQuestion` |
| Subagent coordination | Add: lead agent assigns each subagent a specific tmp filepath to write findings to |
| Citation instruction | Keep as-is: "Do not include any citations — a separate agent handles this" |

**Note on `evaluate_source_quality`:** This appears to be a deliberate prompt engineering technique — a fake tool whose `DO NOT USE` instruction suppresses the model's tendency to expend excessive tokens on source verification loops. The tool name precisely targets the behavioral cluster being suppressed. Keep verbatim in both lead and subagent prompts.

### `subagent.md` (from `research_subagent.md`)

| Original | Adapted |
|---|---|
| `web_search` / `web_fetch` | `WebSearch` / `WebFetch` |
| `complete_task` tool | `Write` tool — write findings to the tmp filepath passed by the lead agent |
| `repl` tool | Removed |
| `evaluate_source_quality` | Keep the DO NOT USE line verbatim |
| Google Suite / internal tools | Keep conditionally |
| Output format | Add: "Write your complete findings report as markdown to the filepath provided in your instructions" |

Preserve as-is: OODA loop, research budget concept, source quality reasoning, parallel tool call instructions.

### `citations-agent.md` (from `citations_agent.md`)

This prompt requires the most significant adaptation — it is the most Claude.ai-specific.

| Original | Adapted |
|---|---|
| `<cite>` tags | Replaced with standard markdown footnotes: `[^1]`, `[^2]`, etc. |
| `<exact_text_with_citation>` output tags | Removed — agent writes directly to the file using surgical `Edit` tool calls |
| `<synthesized_text>` input | Agent reads the draft report file directly |
| "Text will be compared to original" validation | Removed — no automated validation layer in Claude Code |

Preserve as-is: citation placement philosophy (not every statement, meaningful semantic units, no redundant citations, minimise fragmentation), whitespace preservation instruction.

---

## Citation Mechanism

### Lead agent: insert `[^?]` markers at write time

As the lead agent writes the draft report, it inserts `[^?]` markers at the end of sentences derived from sources:

```markdown
The company was founded in 2010.[^?] Revenue grew 40% YoY.[^?]
```

The lead agent knows which claims came from sources — it just synthesised from the subagent tmp files. Marking citation points at write time is essentially free.

**Why `[^?]`:**
- Valid markdown — draft is readable before the citation pass
- Visually signals "unresolved footnote"
- Unambiguous regex target: `\[\^\?\]`
- Won't collide with real footnotes in the final document

### Citations agent: surgical `Edit` tool calls

The citations agent does NOT rewrite the document. Instead:

1. Reads `draft-report.md` and all subagent tmp files
2. For each `[^?]` in document order, finds the supporting source and makes a surgical `Edit` call:
   ```
   Find:    "founded in 2010.[^?]"
   Replace: "founded in 2010.[^1]"
   ```
3. Appends a `## References` section to the file with all footnote definitions

**v2 alternative (noted for future consideration):** Tag markers with the originating subagent — `[^?:subagent-2]` — to give the citations agent a routing hint, reducing the search space per citation. Trade-off: slightly more work for the lead agent at write time.

---

## Error Handling

- If a subagent fails to write its tmp file, the lead agent detects the missing file and either retries with a new subagent or proceeds with available results, noting the gap in the report
- If the citations pass fails partway through, `[^?]` markers remaining in the file make it obvious which citations are missing — the draft remains readable
- The `.tmp/` directory is only deleted after the citations agent confirms completion

---

## Model Selection

The `Agent` tool in Claude Code accepts a `model` parameter, enabling different models per agent role.

| Agent | Model | Rationale |
|---|---|---|
| Lead agent | `claude-sonnet-4-6` (default) or `claude-opus-4-6` (user override) | Responsible for planning, synthesis, and report writing — benefits from strong reasoning |
| Research subagents | `claude-haiku-4-5-20251001` (hardcoded) | Mechanical task: search, fetch, summarise, write to file. Haiku is faster and cheaper with no quality trade-off |
| Citations agent | `claude-haiku-4-5-20251001` (hardcoded) | Transformation task: pattern matching and footnote insertion. No deep reasoning required |

**Lead agent model selection:**

Default is Sonnet. The user can override to Opus at invocation time for queries they know are complex:

```
deep research --model opus "Compare the geopolitical implications of..."
```

**Why not complexity-based auto-selection?**

An alternative design would have the outer Claude session assess query complexity and choose the lead model automatically. This is appealing but adds a reasoning step before any work starts, and complexity is often hard to judge from the query alone. User-specified override is simpler and respects user judgement. This could be revisited in v2 if users find they frequently need to override.

**Cost profile:**

The majority of token spend is in research subagents (many parallel calls, each doing multiple web searches). Fixing these at Haiku has the most significant cost impact. Lead agent and citations agent are single calls and their model choice is a secondary cost concern.

---

## Prompt Engineering Notes

- **`evaluate_source_quality` fake tool:** Keep verbatim in both lead and subagent prompts. Removing it risks reinstating the token-expensive source verification loops it suppresses.
- **Parallel subagent calls:** The lead agent prompt explicitly instructs parallel `Agent` tool calls — preserve this instruction. Research subagents should run concurrently.
- **Subagent count guidelines:** Preserved from original (1 for straightforward, 2–3 standard, 3–5 medium, 5–20 high complexity, never exceed 20).
