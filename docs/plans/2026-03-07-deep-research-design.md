# Deep Research Skill — Design

**Date:** 2026-03-07
**Status:** Revised — v2 corrected architecture (lead agent as subagent, research via CLI subprocesses)

---

## Overview

A Claude Code skill that replicates Claude.ai's Deep Research feature: a multi-agent research pipeline that plans, researches, synthesises, and cites — saving the final report to a markdown file.

---

## Architecture

**Approach: Lead agent as subagent + CLI subprocesses for research/citations**

The main session delegates all research work to a lead agent subagent (via the `Agent` tool), keeping the main context clean. The lead agent — which cannot itself use the `Agent` tool to spawn further subagents — launches research subagents and the citations agent as independent `claude -p` CLI subprocesses via `Bash`.

```
User invokes skill
  └─ Claude (main session)
        └─ Agent tool → Lead agent subagent (following lead-agent.md)
                ├─ Plans research (query type: depth-first / breadth-first / straightforward)
                ├─ Bash: launches N parallel `claude -p` subprocesses (research subagents)
                │     └─ Each subprocess: WebSearch + WebFetch → writes findings to tmp file → exits
                ├─ Reads all tmp files → synthesises → writes draft report (with [^?] markers)
                └─ Bash: launches `claude -p` subprocess (citations agent)
                      └─ Reads draft + tmp files → surgical Edit calls → appends References → exits
                            └─ Cleanup tmp directory
```

**Why this architecture:**

- **Lead agent as `Agent` subagent:** The main session context is kept clean — no research tool calls, web fetches, or draft content polluting the conversation. The main session simply invokes the Agent tool and gets back a completion when the report is written.

- **Research/citations via `claude -p`:** Claude Code subagents (spawned via the `Agent` tool) cannot themselves spawn further subagents. This is the v1 failure mode — the lead agent subagent silently fell back to doing all research in a single context. The `claude -p` workaround is targeted specifically at this constraint: each CLI subprocess is an independent Claude Code session with full tool access, not a constrained subagent. Only the lead agent needs this workaround; the main session does not.

**The filesystem is still the coordination layer** — consistent with orchestration harnesses like RALPH loops.

---

## Output

- **Final report:** `~/research/YYYY-MM-DD-topic-slug.md` (default)
- **User-specified path:** supported at invocation time via `--output` flag
- **Topic slug:** derived from the research query (kebab-case, max 5 words)

---

## File Structure (runtime)

```
~/research/
  2026-03-07-topic-slug.md          ← final report (with citations)
  .tmp/
    2026-03-07-topic-slug/
      subagent-1.md                 ← findings from research subprocess 1
      subagent-2.md                 ← findings from research subprocess 2
      subagent-N.md
      draft-report.md               ← lead's synthesis (pre-citation)
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

Lives in `claude-code-only/` — requires `Agent`, `Bash` (to launch CLI subprocesses from within the lead agent), `WebSearch`, `WebFetch`, and filesystem tools unavailable in Claude.ai.

---

## Lead Agent Invocation

The main session (following SKILL.md) reads `lead-agent.md` and passes its content as the task prompt to the `Agent` tool, along with the research query and current date:

```
Agent tool call:
  prompt: "[full content of lead-agent.md]\n\nQuery: {user_query}\nDate: {current_date}\nOutput: {output_path}"
  model: claude-sonnet-4-6 (default) or claude-opus-4-6 (--model opus override)
```

The lead agent runs entirely in its own context. When it completes, the final report is written to disk and the main session reports success.

---

## Subprocess Invocation Pattern

The lead agent launches research subagents via Bash using `claude -p`:

```bash
claude -p "DETAILED_TASK_DESCRIPTION. Write your findings to: /path/to/subagent-N.md" \
  --system-prompt-file /abs/path/to/references/subagent.md \
  --model claude-haiku-4-5-20251001 \
  --tools "WebSearch,WebFetch,Write,Read,Bash" \
  --dangerously-skip-permissions \
  --no-session-persistence > /dev/null 2>&1 &
```

Multiple subagents run in parallel with `&`; the lead waits for all with `wait`.

The citations agent is launched the same way after the draft is written:

```bash
claude -p "Draft: /path/to/draft-report.md. Sources: /path/to/.tmp/. Final output: /path/to/report.md." \
  --system-prompt-file /abs/path/to/references/citations-agent.md \
  --model claude-haiku-4-5-20251001 \
  --tools "Read,Write,Edit,Bash" \
  --dangerously-skip-permissions \
  --no-session-persistence > /dev/null 2>&1
```

**Key flags:**
- `--system-prompt-file` — loads the agent's role prompt from the reference file
- `--model` — sets model per role (Haiku for subagents/citations, inherited for lead)
- `--tools` — restricts each process to only the tools it needs
- `--dangerously-skip-permissions` — required for unattended headless operation
- `--no-session-persistence` — subprocesses are fire-and-forget, no need to resume
- `> /dev/null 2>&1` — suppresses stdout/stderr; coordination happens via file writes

**System prompt file path:** Claude resolves the absolute path to the skill's reference files at invocation time (they were read earlier in the workflow). The absolute path is used in the `--system-prompt-file` flag.

---

## Prompt Adaptation

The reference prompts are adapted from Anthropic's Claude.ai production prompts. Goal: preserve as much original language as possible. Changes from v1:

### `lead-agent.md`

| Change | Detail |
|---|---|
| `run_blocking_subagent` → `Bash` | Lead agent launches `claude -p` subprocesses — it cannot use the Agent tool from within a subagent |
| `{TASK_CONTEXT}` / `{QUERY}` / `{CURRENT_DATE}` | Injected by main session into the Agent tool prompt at invocation time |
| `complete_task` → `Write` | Write draft to draft output path |
| `web_search` → `WebSearch`, `web_fetch` → `WebFetch` | Tool name substitution |
| `repl` tool | Removed |
| `evaluate_source_quality` DO NOT USE | Keep verbatim (see note) |
| Google Suite / Slack / internal tools | Keep conditionally |

Delegation instructions updated to describe the `claude -p` subprocess pattern including flags.

### `subagent.md`

| Change | Detail |
|---|---|
| `web_search` → `WebSearch`, `web_fetch` → `WebFetch` | Tool name substitution |
| `complete_task` → `Write` | Write findings to filepath in user message |
| `repl` tool | Removed |
| `evaluate_source_quality` DO NOT USE | Keep verbatim |
| `{TASK}` placeholder at end | Replaced with "Your task is in the user message" — task/filepath passed via `-p` query |

### `citations-agent.md`

| Change | Detail |
|---|---|
| `<cite>` tags | Replaced with standard markdown footnotes `[^N]` |
| `<exact_text_with_citation>` output | Removed — agent uses surgical `Edit` calls |
| `<synthesized_text>` input | Agent reads draft file directly |
| `{TASK_CONTEXT}` placeholder | Replaced with "task is in the user message" — paths passed via `-p` query |
| Validation layer | Removed — no automated validation in Claude Code |

Preserve as-is: citation placement philosophy, whitespace preservation instruction.

---

## Citation Mechanism

### Lead agent: insert `[^?]` markers at write time

As the lead writes the draft report, it inserts `[^?]` at the end of sentences derived from specific sources:

```markdown
The company was founded in 2010.[^?] Revenue grew 40% YoY.[^?]
```

**Why `[^?]`:** Valid markdown, visually signals unresolved footnote, unambiguous regex target (`\[\^\?\]`), won't collide with real footnotes.

### Citations agent: surgical `Edit` tool calls

The citations agent does NOT rewrite the document. Instead:

1. Reads `draft-report.md` and all subagent tmp files
2. For each `[^?]` in document order, makes a surgical `Edit` call:
   ```
   Find:    "founded in 2010.[^?]"
   Replace: "founded in 2010.[^1]"
   ```
3. Appends a `## References` section with all footnote definitions
4. Writes the cited draft to the final output path

**v2 alternative (noted for future):** Tag markers with originating subagent — `[^?:subagent-2]` — to give the citations agent a routing hint. Trade-off: more work for the lead at write time.

---

## Error Handling

- If a subagent subprocess fails to write its tmp file, the lead detects the missing file and either re-launches the subprocess or proceeds with available results, noting the gap
- `claude -p` subprocess exit codes can be checked after `wait` to detect failures
- If the citations pass fails partway, `[^?]` markers remaining in the file make it obvious — draft remains readable
- `.tmp/` directory only deleted after citations agent confirms completion

---

## Model Selection

| Role | Model | How set |
|---|---|---|
| Lead agent (Agent subagent) | `claude-sonnet-4-6` default, `claude-opus-4-6` with `--model opus` | `model` parameter on Agent tool call; SKILL.md parses `--model` flag |
| Research subprocesses | `claude-haiku-4-5-20251001` (hardcoded) | `--model` flag in `claude -p` invocation |
| Citations subprocess | `claude-haiku-4-5-20251001` (hardcoded) | `--model` flag in `claude -p` invocation |

**Lead model:** Sonnet default; user overrides with `--model opus` at invocation for complex queries.

**Cost profile:** Majority of spend is in research subprocesses (parallel, many tool calls each). Haiku hardcoded there has the most significant cost impact.

---

## Prompt Engineering Notes

- **`evaluate_source_quality` fake tool:** Keep verbatim in both lead and subagent prompts. This is deliberate prompt engineering — the DO NOT USE instruction suppresses token-expensive source verification loops by precisely targeting that behavioral cluster.
- **Parallel subprocess launches:** The lead agent uses Bash background processes (`&`) + `wait` for true parallelism. This replaces the original parallel `Agent` tool calls, which the lead agent cannot make from within a subagent context.
- **Subagent count guidelines:** Preserved from original (1 for straightforward, 2–3 standard, 3–5 medium, 5–20 high complexity, never exceed 20).
