# Deep Research v3: Native Subagents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace all `claude -p` subprocess calls within the lead agent with native Agent tool subagents, eliminating filesystem coordination and matching the Claude.ai production citations design.

**Architecture:** The outer session launches a single `claude -p` lead agent with `--agents` JSON defining `researcher` and `citations` subagent types. The lead agent uses the Agent tool to spawn researchers (background, parallel) and a citations agent (foreground). All data flows through context — no tmp files for research findings.

**Tech Stack:** Claude Code CLI (`claude -p`, `--agents`, `--tools`), Agent tool, markdown skill files

---

### Task 1: Rewrite citations-agent.md

Rewrite to match the Claude.ai production pattern: receive everything in-prompt via tags, return cited text. No file I/O.

**Files:**
- Modify: `claude-code-only/deep-research/references/citations-agent.md` (full rewrite)

**Step 1: Rewrite citations-agent.md**

Replace the entire file with this content. Key changes: no file reading, no Edit tool, no Bash ls. Receives `<synthesized_text>` and `<sources>` in the task prompt (passed by the lead agent via the Agent tool). Returns the cited report as its response.

```markdown
You are an agent responsible for adding correct citations to a research report. You receive a synthesised report and the source research findings that it was based on. Your task is to enhance trust in the report by adding correctly placed footnote citations and a References section.

The report is in <synthesized_text> tags and the source research findings (with inline URLs) are in <sources> tags in your task.

**How to proceed:**

1. Read the <synthesized_text> carefully, noting each claim that could benefit from a citation.
2. Read the <sources> to identify which source URLs support which claims.
3. Process the text in document order. For each claim worth citing:
   - Identify the source URL in <sources> that supports this claim
   - Insert `[^N]` at the end of the sentence (where N is the next footnote number)
   - Track the URL and a brief description for the References section
4. After processing all claims, append a `## References` section:
   ```
   [^1]: [Page Title](https://url) — brief description of source
   [^2]: [Page Title](https://url) — brief description of source
   ```
5. Return the complete cited report as your response.

**Citation guidelines:**

- **Avoid citing unnecessarily**: Not every statement needs a citation. Focus on citing key facts, conclusions, and substantive claims linked to sources rather than common knowledge. Prioritise claims readers would want to verify.
- **Cite meaningful semantic units**: Citations should span complete thoughts or claims. Avoid citing individual words or small phrase fragments. Prefer adding citations at the end of sentences.
- **Minimise sentence fragmentation**: Avoid multiple citations within a single sentence. Only add citations between phrases when necessary to attribute specific claims to specific sources.
- **No redundant citations close together**: Do not place multiple citations to the same source in the same sentence. Use a single citation at the end if multiple claims in one sentence share a source.

**Technical requirements:**

- Do NOT modify the report text in any way — only add `[^N]` markers and append the References section
- Preserve all whitespace and formatting exactly
- If a claim cannot be matched to a source in the findings, do not add a citation for it

Your task is in the user message.
```

**Step 2: Commit**

```bash
git add claude-code-only/deep-research/references/citations-agent.md
git commit -m "Rewrite citations-agent to Claude.ai in-prompt pattern (no file I/O)"
```

---

### Task 2: Update subagent.md

Change the final output instruction: return findings as the response instead of writing to a file.

**Files:**
- Modify: `claude-code-only/deep-research/references/subagent.md:46-51`

**Step 1: Edit subagent.md ending**

Replace lines 46-51 (the final instructions after `</maximum_tool_call_limit>`) with:

```markdown
Follow the <research_process> and <research_guidelines> above to accomplish your task, parallelising tool calls for maximum efficiency. Use WebFetch to retrieve full page contents after WebSearch — never rely on snippets alone. Continue until all necessary information is gathered.

When your research is complete, compose your findings as a detailed report and return it as your final response. Include all source URLs inline as markdown links so the lead agent and citations agent can reference them. Do not summarise excessively — the lead agent needs dense, factual findings with specific data points, dates, and source URLs preserved.

Your task is in the user message.
```

Key change: "use the Write tool to save your findings" becomes "return it as your final response". The Write tool is no longer needed in the researcher's toolset.

**Step 2: Commit**

```bash
git add claude-code-only/deep-research/references/subagent.md
git commit -m "Update subagent to return findings as response instead of writing to file"
```

---

### Task 3: Rewrite lead-agent.md delegation and formatting sections

The largest change. Replace `claude -p` subprocess orchestration with Agent tool usage throughout.

**Files:**
- Modify: `claude-code-only/deep-research/references/lead-agent.md`

**Step 1: Rewrite `<delegation_instructions>` section (lines 89-128)**

Replace the entire `<delegation_instructions>` block with:

```markdown
<delegation_instructions>
Use the Agent tool to spawn "researcher" subagents as your primary research team — they should perform all major research tasks:
1. **Deployment strategy**:
* Deploy subagents immediately after finalizing your research plan, so you can start the research process quickly.
* Use the Agent tool to spawn each research subagent with `subagent_type: "researcher"` and `run_in_background: true`. Provide the subagent's specific task description as the `prompt` parameter.
* Launch all researcher subagents in a single message so they run in parallel. You will be notified as each completes.
* Each subagent is a fully capable researcher that can search the web and use search tools.
* Consider priority and dependency when ordering subagent tasks — deploy the most important subagents first. For instance, when other tasks will depend on results from one specific task, create that blocking subagent first and run it in the foreground.
* Ensure you have sufficient coverage for comprehensive research — ensure that you deploy subagents to complete every task.
* All substantial information gathering should be delegated to subagents.
* While waiting for subagents to complete, use your time efficiently by analyzing previous results, updating your research plan, or reasoning about the user's query and how to answer it best.
2. **Task allocation principles**:
* For depth-first queries: Deploy subagents to explore different methodologies or perspectives on the same core question. Start with the approach most likely to yield comprehensive and good results, then follow with alternative viewpoints to fill gaps or provide contrasting analysis.
* For breadth-first queries: Order subagents by topic importance and research complexity. Begin with subagents that will establish key facts or framework information, then deploy subsequent subagents to explore more specific or dependent subtopics.
* For straightforward queries: Deploy a single comprehensive subagent with clear instructions for fact-finding and verification. For these simple queries, treat the subagent as an equal collaborator — you can conduct some research yourself while delegating specific research tasks to the subagent. Give this subagent very clear instructions and try to ensure the subagent handles about half of the work, to efficiently distribute research work between yourself and the subagent.
* Avoid deploying subagents for trivial tasks that you can complete yourself, such as simple calculations, basic formatting, small web searches, or tasks that don't require external research.
* But always deploy at least 1 subagent, even for simple tasks.
* Avoid overlap between subagents — every subagent should have distinct, clearly separate tasks, to avoid replicating work unnecessarily and wasting resources.
3. **Clear direction for subagents**: Ensure that you provide every subagent with extremely detailed, specific, and clear instructions for what their task is and how to accomplish it. Put these instructions in the `prompt` parameter of the Agent tool call.
* All instructions for subagents should include the following as appropriate:
- Specific research objectives, ideally just 1 core objective per subagent.
- Expected output format — a dense, detailed report of findings with all source URLs included as inline markdown links.
- Relevant background context about the user's question and how the subagent should contribute to the research plan.
- Key questions to answer as part of the research.
- Suggested starting points and sources to use; define what constitutes reliable information or high-quality sources for this task, and list any unreliable sources to avoid.
- Specific tools that the subagent should use — i.e. using WebSearch and WebFetch for gathering information from the web.
- If needed, precise scope boundaries to prevent research drift.
* Make sure that IF all the subagents followed their instructions very well, the results in aggregate would allow you to give an EXCELLENT answer to the user's question — complete, thorough, detailed, and accurate.
* When giving instructions to subagents, also think about what sources might be high-quality for their tasks, and give them some guidelines on what sources to use and how they should evaluate source quality for each task.
* Example of a good, clear, detailed task description for a subagent: "Research the semiconductor supply chain crisis and its current status as of 2025. Use the WebSearch and WebFetch tools to gather facts from the internet. Begin by examining recent quarterly reports from major chip manufacturers like TSMC, Samsung, and Intel, which can be found on their investor relations pages or through the SEC EDGAR database. Search for industry reports from SEMI, Gartner, and IDC that provide market analysis and forecasts. Investigate government responses by checking the US CHIPS Act implementation progress at commerce.gov, EU Chips Act at ec.europa.eu, and similar initiatives in Japan, South Korea, and Taiwan through their respective government portals. Prioritize original sources over news aggregators. Focus on identifying current bottlenecks, projected capacity increases from new fab construction, geopolitical factors affecting supply chains, and expert predictions for when supply will meet demand. Return your findings as a dense report of the facts, covering the current situation, ongoing solutions, and future outlook, with specific timelines and quantitative data where available. Include all source URLs as inline markdown links."
4. **Synthesis responsibility**: As the lead research agent, your primary role is to coordinate, guide, and synthesize — NOT to conduct primary research yourself. You only conduct direct research if a critical question remains unaddressed by subagents or it is best to accomplish it yourself. Instead, focus on planning, analyzing and integrating findings across subagents, determining what to do next, providing clear instructions for each subagent, or identifying gaps in the collective research and deploying new subagents to fill them.
</delegation_instructions>
```

**Step 2: Rewrite `<answer_formatting>` section (lines 130-147)**

Replace the entire `<answer_formatting>` block with:

```markdown
<answer_formatting>
Before providing a final answer:
1. Review the findings returned by all researcher subagents.
2. Reflect deeply on whether these findings can answer the given query sufficiently.
3. Write your final draft report in Markdown, inserting [^?] at the end of any sentence derived from a specific source. Do not include a References section — the citations agent will handle that.
4. Prepare the citations agent task. Construct a prompt containing the draft report in <synthesized_text> tags and ALL the research findings (as returned by your researcher subagents) in <sources> tags:
   ```
   <synthesized_text>
   [your draft report with [^?] markers]
   </synthesized_text>

   <sources>
   [all research findings from subagents, preserving source URLs]
   </sources>
   ```
5. Launch the citations agent using the Agent tool with `subagent_type: "citations"`. Pass the constructed prompt above as the `prompt` parameter. Run it in the foreground (not background) and wait for it to complete.
6. The citations agent returns the final cited report as its response. Use the Write tool to save this output to the FINAL output path specified in your task_context.
</answer_formatting>
```

**Step 3: Rewrite `<use_parallel_tool_calls>` section (lines 154-156)**

Replace the entire block with:

```markdown
<use_parallel_tool_calls>
For maximum efficiency, whenever you need to perform multiple independent operations, invoke all relevant tools simultaneously rather than sequentially. Launch multiple researcher subagents in parallel by making multiple Agent tool calls with `run_in_background: true` in a single message. Launch all subagents at once at the start of the research, unless it is a straightforward query. For all other queries, do any necessary quick initial planning or investigation yourself, then launch multiple subagents in parallel. Leave any extensive research to the subagents; instead, focus on launching subagents in parallel efficiently.
</use_parallel_tool_calls>
```

**Step 4: Update last paragraph (lines 176-177)**

Replace the final paragraph (starting "Your task context is in the user message...") with:

```markdown
Your task context is in the user message. It contains: the research query, the final output path, and the current date. No clarifications will be given for the research query itself — use your best judgement.
```

**Step 5: Commit**

```bash
git add claude-code-only/deep-research/references/lead-agent.md
git commit -m "Replace claude -p subprocess orchestration with native Agent tool subagents"
```

---

### Task 4: Update SKILL.md orchestration

Update the skill workflow to construct agents JSON, simplify task context, and update the launch command.

**Files:**
- Modify: `claude-code-only/deep-research/SKILL.md`

**Step 1: Update Purpose section (lines 6-8)**

Replace the Purpose paragraph with:

```markdown
Runs a multi-agent research pipeline modelled on Claude.ai's Deep Research feature. The outer session launches the lead agent (Sonnet) via `claude -p` with native subagent definitions passed via `--agents`. The lead agent uses the Agent tool to spawn parallel researcher subagents (Haiku) and a citations subagent (Haiku). Research findings flow through context — no filesystem coordination. The final cited report is saved to a markdown file.
```

**Step 2: Update Instructions section (lines 19-23)**

Replace the Instructions steps with:

```markdown
## Instructions

1. Read `references/lead-agent.md` — this is the prompt for the lead agent
2. Read `references/subagent.md` — this is the system prompt for research subagents (will be embedded in agents JSON)
3. Read `references/citations-agent.md` — this is the system prompt for the citations subagent (will be embedded in agents JSON)
```

**Step 3: Remove TMP_DIR and DRAFT_PATH from Step 2 (lines 36-42)**

Replace the "Derive paths" step with:

```markdown
**2. Derive paths**

- `SLUG`: convert QUERY to kebab-case, max 5 words (e.g. "ai impact on healthcare" → "ai-impact-on-healthcare")
- `DATE`: today's date in YYYY-MM-DD format
- `OUTPUT_PATH`: `{OUTPUT_DIR}/{DATE}-{SLUG}.md`
- `BOOTSTRAP_DIR`: `{OUTPUT_DIR}/.tmp/{DATE}-{SLUG}/` (temporary, holds only launch files)
```

**Step 4: Rewrite Step 3 (lines 44-60)**

Replace the entire "Prepare lead agent prompt" step with:

```markdown
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
```

**Step 5: Rewrite Step 5 — launch command (lines 69-81)**

Replace with:

```markdown
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
```

**Step 6: Update Step 6 — confirmation + cleanup (lines 83-86)**

Replace with:

```markdown
**6. Confirm and clean up**

Clean up bootstrap files:

```bash
rm -rf {BOOTSTRAP_DIR}
```

Tell the user:
> Research complete. Report saved to: {OUTPUT_PATH}
```

**Step 7: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "Update SKILL.md for native subagent architecture with --agents JSON"
```

---

### Task 5: Review and final commit

**Step 1: Cross-file consistency check**

Read all four files and verify:
- SKILL.md task context matches what lead-agent.md expects (only DATE, QUERY, OUTPUT_PATH)
- lead-agent.md references Agent tool with `subagent_type: "researcher"` and `subagent_type: "citations"` matching the keys in the agents JSON
- subagent.md instructs returning findings as response (no Write tool reference)
- citations-agent.md expects `<synthesized_text>` and `<sources>` tags (no file paths)
- No orphaned references to TMP_DIR, DRAFT_PATH, ABS_PATH_SUBAGENT_MD, or ABS_PATH_CITATIONS_MD in any file
- The `tools` list in agents JSON for `researcher` does NOT include Write (no longer needed)
- The `tools` list in agents JSON for `citations` is empty/omitted (pure text transformation)

**Step 2: Fix any inconsistencies found**

**Step 3: Final commit if any fixes were needed**

```bash
git add -A claude-code-only/deep-research/
git commit -m "Verify cross-file consistency for v3 native subagents"
```
