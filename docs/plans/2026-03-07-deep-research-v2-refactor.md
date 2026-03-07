# Deep Research v2 Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the deep-research skill from v1 (Agent tool spawning) to v2 (corrected CLI subprocess orchestration) as specified in the design doc.

**Architecture:** Lead agent subagent (spawned via `Agent` tool) handles all orchestration. The lead agent uses `claude -p` Bash subprocesses for research subagents and the citations agent — the targeted workaround for the subagent-can't-spawn-subagents constraint. The main session invokes the Agent tool and waits; it does NOT act as lead agent itself.

**Tech Stack:** Markdown prompt files only — no code. Verification is manual re-read of each file.

**Design doc:** `docs/plans/2026-03-07-deep-research-design.md`

**Files touched:**
- `claude-code-only/deep-research/references/lead-agent.md`
- `claude-code-only/deep-research/references/subagent.md`
- `claude-code-only/deep-research/references/citations-agent.md`
- `claude-code-only/deep-research/SKILL.md`

---

### Task 1: Refactor `lead-agent.md`

Two changes: (a) update delegation to use `claude -p` subprocess pattern, (b) update `{TASK_CONTEXT}`/`{QUERY}` block at bottom to reference corrected inputs.

**Note:** Do NOT remove `{CURRENT_DATE}`. The lead agent is a subagent and does not have SKILL.md context — the date is injected by SKILL.md before the Agent tool call.

**File:** `claude-code-only/deep-research/references/lead-agent.md`

---

**Step 1a: Update delegation instructions — replace Agent tool with `claude -p`**

In the `<delegation_instructions>` section, find the two bullet points that read:

```
* Use the `Agent` tool to create a research subagent. Pass the full contents of the subagent prompt (provided in your task context) in the `prompt` parameter, replacing `{CURRENT_DATE}` with today's date, and appending the subagent's specific task and its assigned tmp filepath at the end.
* Set `model: {SUBAGENT_MODEL}` on every Agent tool call for research subagents.
```

Replace with:

```
* Use the `Bash` tool to launch each research subagent as an independent `claude -p` subprocess. Pass the subagent's specific task description and assigned tmp filepath as the `-p` query. Use `--system-prompt-file` with the absolute path to `references/subagent.md`:
  ```bash
  claude -p "DETAILED_TASK_DESCRIPTION. Write your findings to: /path/to/subagent-N.md" \
    --system-prompt-file /abs/path/to/references/subagent.md \
    --model claude-haiku-4-5-20251001 \
    --tools "WebSearch,WebFetch,Write,Read,Bash" \
    --dangerously-skip-permissions \
    --no-session-persistence > /dev/null 2>&1 &
  ```
* Launch all subagents with `&` so they run in parallel. After launching all of them, call `wait` to block until every subprocess has finished.
```

**Step 1b: Update the parallel tool calls instruction**

Find the sentence in `<use_parallel_tool_calls>`:
```
You MUST use parallel tool calls for creating multiple subagents (typically running 3 subagents at the same time) at the start of the research, unless it is a straightforward query.
```

Replace with:
```
You MUST launch multiple subagents in parallel using Bash background processes (`&`) followed by `wait`. Launch all subagents at once at the start of the research, unless it is a straightforward query.
```

**Step 1c: Update the `{TASK_CONTEXT}` / `{QUERY}` block at the bottom**

Find the last section of the file:
```
You have been given a research query, a draft output path, a tmp directory path, and a subagent model to use. Your task context is provided below. No clarifications will be given for the research query itself — use your best judgement. However, if the invocation flags or paths are missing or ambiguous, you may ask for clarification.

<task_context>
{TASK_CONTEXT}
</task_context>

Your research query is: {QUERY}
```

Replace with:
```
Your task context is in the user message. It contains: the research query, the draft output path, the tmp directory path, the final output path, and the absolute paths to `references/subagent.md` and `references/citations-agent.md`. Use these absolute paths as the `--system-prompt-file` argument when launching subagents and the citations agent via Bash. No clarifications will be given for the research query itself — use your best judgement.
```

**Step 1d: Verify**

Re-read the file. Confirm:
- `{CURRENT_DATE}` IS still present on line 2 (do not remove)
- No `Agent` tool in delegation instructions
- `claude -p` subprocess pattern with all 5 flags is present
- No `{TASK_CONTEXT}` or `{QUERY}` placeholders anywhere
- Updated task context block references absolute paths to subagent.md and citations-agent.md

**Step 1e: Commit**

```bash
git add claude-code-only/deep-research/references/lead-agent.md
git commit -m "refactor(deep-research): update lead-agent to claude -p subprocess pattern"
```

---

### Task 2: Refactor `subagent.md`

Two changes: (a) remove `{CURRENT_DATE}` line, (b) replace `{TASK}` placeholder block with "task is in user message".

**File:** `claude-code-only/deep-research/references/subagent.md`

---

**Step 2a: Remove `{CURRENT_DATE}` line**

Find and remove from line 1:
```
The current date is {CURRENT_DATE}.
```

After removal, the file should start with `You are a research subagent working as part of a team.`

**Step 2b: Replace the `{TASK}` block**

Find the last section of the file:
```
Your task and output filepath are specified below:

<task>
{TASK}
</task>
```

Replace with:
```
Your task and output filepath are in the user message.
```

**Step 2c: Verify**

Re-read the file. Confirm:
- No `{CURRENT_DATE}` anywhere
- No `{TASK}` placeholder anywhere
- File ends with "Your task and output filepath are in the user message."

**Step 2d: Commit**

```bash
git add claude-code-only/deep-research/references/subagent.md
git commit -m "refactor(deep-research): remove placeholders from subagent prompt"
```

---

### Task 3: Refactor `citations-agent.md`

One change: replace `{TASK_CONTEXT}` placeholder with "task is in user message".

**File:** `claude-code-only/deep-research/references/citations-agent.md`

---

**Step 3a: Replace `{TASK_CONTEXT}` block**

Find the last section of the file:
```
**Your task context:**

<task_context>
{TASK_CONTEXT}
</task_context>
```

Replace with:
```
**Your task context:**

Your task is in the user message. It contains the draft report path, the tmp directory path with subagent source files, and the final output path.
```

**Step 3b: Verify**

Re-read the file. Confirm:
- No `{TASK_CONTEXT}` anywhere
- File ends with the updated task context instruction

**Step 3c: Commit**

```bash
git add claude-code-only/deep-research/references/citations-agent.md
git commit -m "refactor(deep-research): remove {TASK_CONTEXT} placeholder from citations-agent"
```

---

### Task 4: Refactor `SKILL.md` + smoke test

Three changes: (a) update Purpose and Instructions sections, (b) update step 5 "Spawn lead agent" to pass absolute paths in task context and drop subagent model field, (c) remove step 6 — citations are launched internally by the lead agent via `claude -p`, not by the main session.

**File:** `claude-code-only/deep-research/SKILL.md`

---

**Step 4a: Update Purpose section**

Find in the Purpose paragraph:
```
A lead agent (Sonnet) plans the research, dispatches parallel research subagents (Haiku) to search and gather sources, synthesises their findings into a draft report with `[^?]` citation markers, then passes the draft to a citations agent (Haiku) for surgical footnote insertion.
```

Replace with:
```
A lead agent subagent (Sonnet, spawned via Agent tool) plans the research, launches parallel `claude -p` research subprocesses (Haiku) via Bash, synthesises their findings into a draft report with `[^?]` citation markers, then launches a `claude -p` citations subprocess (Haiku) for surgical footnote insertion. The main session invokes the lead agent and waits.
```

**Step 4b: Update Instructions section**

Find:
```
2. Read `references/subagent.md` — the lead agent passes this verbatim to each research subagent
3. Read `references/citations-agent.md` — the lead agent passes this to the citations agent
```

Replace with:
```
2. Read `references/subagent.md` and resolve its absolute path — included in the task context passed to the lead agent, which uses it as `--system-prompt-file` when launching research subprocesses
3. Read `references/citations-agent.md` and resolve its absolute path — same: passed to lead agent in task context for use as `--system-prompt-file` with the citations subprocess
```

**Step 4c: Update step 5 — "Spawn lead agent"**

Find the entire step 5 block:
```
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
```

Replace the entire block with:

````markdown
**5. Spawn lead agent**

Invoke the Agent tool with:
- `model`: the resolved LEAD_MODEL
- `prompt`: the full contents of `references/lead-agent.md` (with `{CURRENT_DATE}` substituted), followed by this task context block:

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

The lead agent handles all research, synthesis, and citations internally. Wait for it to complete — it writes the final cited report to `{OUTPUT_PATH}` before finishing.
````

**Step 4d: Remove step 6**

Find the entire step 6 block (citations agent) and delete it. The citations agent is launched internally by the lead agent via `claude -p` Bash subprocess — it is not the main session's responsibility.

If a cleanup step exists after step 6 (deleting `.tmp/`), renumber it as step 6 and keep it.

**Step 4e: Smoke test — verify all 4 files**

Re-read all 4 files and confirm:

| File | Must NOT contain | Must contain |
|------|-----------------|--------------|
| `lead-agent.md` | `Agent` tool in delegation, `{TASK_CONTEXT}`, `{QUERY}` | `{CURRENT_DATE}` (kept), `claude -p`, `--system-prompt-file`, `--dangerously-skip-permissions`, `wait`, absolute path references |
| `subagent.md` | `{CURRENT_DATE}`, `{TASK}` | "Your task and output filepath are in the user message" |
| `citations-agent.md` | `{TASK_CONTEXT}` | "Your task is in the user message" |
| `SKILL.md` | "Act as lead agent", citations Agent tool call in step 6 | "Spawn lead agent" via Agent tool, absolute paths in task context |

**Step 4f: Commit**

```bash
git add claude-code-only/deep-research/SKILL.md
git commit -m "refactor(deep-research): lead agent as subagent, research via claude -p subprocesses"
```

---

## Summary of commits

```
refactor(deep-research): update lead-agent to claude -p subprocess pattern
refactor(deep-research): remove placeholders from subagent prompt
refactor(deep-research): remove {TASK_CONTEXT} placeholder from citations-agent
refactor(deep-research): lead agent as subagent, research via claude -p subprocesses
```
