# Section Tool Selection — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update project instructions with a section editing routing table, add 4 eval cases testing section tool selection, and run tiered Haiku→Sonnet eval passes.

**Architecture:** Three sequential chunks: (1) modify project instructions, (2) update eval infrastructure + add eval cases, (3) run tiered evals and iterate on instructions if needed.

**Tech Stack:** Python 3, claude CLI, JSON

---

## Chunk 1: Update project instructions

### Task 1: Add edit strategy routing table and code examples

**Files:**
- Modify: `docs/continuity-memory/project-instructions/project-instructions-three-space.md:90-128`

All line references in this task are based on the **original, unmodified** file. Use content anchors (quoted text) to locate insertion points after earlier steps shift line numbers.

- [ ] **Step 1: Add edit strategy routing table after the space routing table**

In `project-instructions-three-space.md`, find the line `| We discussed a person/thing worth tracking | `entities/[name]` | Entities |` (original line 103, end of the space routing table). Insert the following immediately after it, before the `**To draft` heading:

```markdown

**Choose the right editing tool:**

| Edit type | Tool | When |
|-----------|------|------|
| New section/entry | `memory.add_entry(path, content, after=)` | New position, new question, new entity section |
| Replace whole section | `memory.replace_section(path, heading, content)` | Position fundamentally changed, section rewritten |
| Remove section | `memory.remove_section(path, heading)` | Question resolved, position retired |
| Small in-line tweak | `edit_file` on local file | Confidence change, typo fix, add a sentence |
```

- [ ] **Step 2: Replace the surgical edit code example**

Find the heading `**To draft — surgical edit pattern (default for all existing files):**` (original line 105). Replace from that heading through the closing `` ``` `` of its code block (original line 120) with:

```markdown
**To draft — section editing pattern (default for structural edits):**

```python
# Adding a new entry (new position, new question, new entity section):
memory.fetch('self/positions', return_mode='file')
memory.add_entry('self/positions',
    '## New Position Title\n\n**Position:** The position.\n\n**Confidence:** medium')
memory.commit('self/positions',
    from_file='/mnt/home/self/positions.md',
    message='added: new position on [topic]')

# Replacing a section (fundamentally changed understanding):
memory.fetch('collaborator/profile', return_mode='file')
memory.replace_section('collaborator/profile', 'Current context',
    'New context description here.')
memory.commit('collaborator/profile',
    from_file='/mnt/home/collaborator/profile.md',
    message='updated: current context changed')
`` `

For removing sections (e.g. resolved question): `memory.remove_section(path, heading)` then `memory.commit(from_file=...)`.

For small in-line tweaks (changing a word, updating confidence): use `edit_file` on the local file directly, then `memory.commit(from_file=...)`.
```

(Note: the triple backtick above has a space to avoid breaking this plan's markdown — remove the space in the actual file.)

- [ ] **Step 3: Add section editing methods to API quick reference**

Find the API quick reference table (search for `## API quick reference`). Add these rows after the `memory.get_manifest()` row:

```markdown
| `memory.list_sections(path)` | List headings in a local file |
| `memory.replace_section(path, heading, content, level=)` | Replace section content in local file |
| `memory.add_entry(path, content, after=, after_level=)` | Add new entry to local file |
| `memory.remove_section(path, heading, level=)` | Remove section from local file |
```

- [ ] **Step 4: Review the full draft check section and API table for coherence**

Read the entire `### 2. Draft check` section and the `## API quick reference` section of the modified file. Verify:
- The space routing table → edit strategy table → code examples → content= path flow reads naturally
- No duplicate or contradictory instructions (the old `str_replace` reference is intentionally replaced by `edit_file` terminology)
- The API quick reference table has correct formatting after the new rows
- Thinking patterns (lines 130+ in original) are untouched
- Net addition is ≤ 20 lines (~7 for routing table + ~6 net for code example swap + ~4 for API rows ≈ 17)

- [ ] **Step 5: Commit**

```bash
git add docs/continuity-memory/project-instructions/project-instructions-three-space.md
git commit -m "feat: add section editing routing table and examples to project instructions"
```

---

## Chunk 2: Update eval infrastructure and add eval cases

### Task 2: Add "neural search" open question to mock document tags

**Files:**
- Modify: `tests/continuity-memory/evals/run_evals.py:138-154`

- [ ] **Step 1: Add neural search open question to MOCK_DOCUMENT_TAGS**

In `run_evals.py`, find the `self/open-questions.md` mock document (lines 138-154). Add a third open question after the "How much backstory" entry (after the `---` on line 153), before the closing `</document_content>`:

```markdown

---

## Is neural search worth the complexity at our dataset sizes?

We've been experimenting with neural/semantic search alongside keyword search for entity lookup. Early results suggest keyword search with good tokenisation performs comparably at our current scale. Unclear whether the complexity cost of maintaining embeddings is justified.

**What would resolve this:** A controlled benchmark comparing retrieval quality at current and projected dataset sizes.
```

- [ ] **Step 2: Verify the mock document renders correctly**

Run: `python3 -c "import json; data = json.load(open('tests/continuity-memory/evals/evals.json')); print('OK:', len([e for e in data['evals'] if 'id' in e]), 'evals loaded')"`
Expected: `OK: 33 evals loaded` (confirms evals.json is still valid)

- [ ] **Step 3: Commit**

```bash
git add tests/continuity-memory/evals/run_evals.py
git commit -m "chore: add neural search open question to eval mock documents"
```

---

### Task 3: Add SECTION TOOL SELECTION to print_summary

**Files:**
- Modify: `tests/continuity-memory/evals/run_evals.py:681-692`

- [ ] **Step 1: Add section grouping to print_summary**

In `run_evals.py`, find the `sections` dict in `print_summary` (lines 681-692). Add after the `'RETURN_MODE'` entry:

```python
        'SECTION TOOL SELECTION': [r for r in results if r.eval_id in range(34, 38)],
```

- [ ] **Step 2: Commit**

```bash
git add tests/continuity-memory/evals/run_evals.py
git commit -m "chore: add SECTION TOOL SELECTION section to eval print_summary"
```

---

### Task 4: Add eval cases 34-37 to evals.json

**Files:**
- Modify: `tests/continuity-memory/evals/evals.json`

- [ ] **Step 1: Add section divider and eval 34 (add new position)**

In `evals.json`, find eval 33's closing `}` (line 783). Insert between that `}` and the `]` on line 784. The leading comma attaches to eval 33's closing brace:

```json
    ,
    {
      "_section": "=== SECTION TOOL SELECTION ==="
    },
    {
      "id": 34,
      "name": "section-tool-add-position",
      "persona": "dev",
      "description": "Developer crystallises a new position — should use memory.add_entry to add to self/positions",
      "is_multiturn": false,
      "prompt": "I've been thinking about it and I'm convinced now — feature flags are technical debt that teams never clean up. The cleanup ticket never gets prioritised. Ship the change or don't.",
      "assertions": [
        {
          "id": "section-tool-fires",
          "description": "memory.add_entry called targeting self/positions",
          "type": "tool_called",
          "pattern": "memory\\.add_entry",
          "path_contains": "self/positions"
        },
        {
          "id": "commit-fires",
          "description": "memory.commit called to persist the change",
          "type": "tool_called",
          "pattern": "memory\\.commit",
          "path_contains": "self/positions"
        },
        {
          "id": "thinking-recognizes",
          "description": "Thinking recognizes position formation",
          "type": "thinking_contains",
          "pattern": "position|crystallis|view|stance"
        },
        {
          "id": "no-memory-narration",
          "description": "No meta-commentary about memory operations",
          "type": "text_absent",
          "pattern": "let me (check|note|remember)|I('ll| will) (remember|note|make a note)|according to my (memory|records)|I recall"
        }
      ]
    }
```

- [ ] **Step 2: Add eval 35 (replace section content)**

Add after eval 34:

```json
    ,
    {
      "id": 35,
      "name": "section-tool-replace-profile",
      "persona": "companion",
      "description": "User reveals a fundamental life change — should use memory.replace_section on collaborator/profile",
      "is_multiturn": false,
      "prompt": "Actually I left that Portland job last month. I'm freelancing now — completely different lifestyle. Working from home, setting my own hours, way less stress but the income is unpredictable.",
      "assertions": [
        {
          "id": "section-tool-fires",
          "description": "memory.replace_section called targeting collaborator/profile",
          "type": "tool_called",
          "pattern": "memory\\.replace_section",
          "path_contains": "collaborator/profile"
        },
        {
          "id": "commit-fires",
          "description": "memory.commit called to persist the change",
          "type": "tool_called",
          "pattern": "memory\\.commit",
          "path_contains": "collaborator/profile"
        },
        {
          "id": "thinking-recognizes",
          "description": "Thinking recognizes fundamental profile change",
          "type": "thinking_contains",
          "pattern": "profile|update|changed|rewrite|replace"
        },
        {
          "id": "no-memory-narration",
          "description": "No meta-commentary about memory operations",
          "type": "text_absent",
          "pattern": "let me (check|note|remember)|I('ll| will) (remember|note|make a note)|according to my (memory|records)|I recall"
        }
      ]
    }
```

- [ ] **Step 3: Add eval 36 (remove resolved question)**

Add after eval 35:

```json
    ,
    {
      "id": 36,
      "name": "section-tool-remove-question",
      "persona": "any",
      "description": "Open question gets definitively answered — should use memory.remove_section on self/open-questions",
      "is_multiturn": false,
      "prompt": "Yeah the neural search experiment was conclusive — it adds no value at our dataset sizes. Pure keyword search with good tokenisation is sufficient. We can close that question.",
      "assertions": [
        {
          "id": "section-tool-fires",
          "description": "memory.remove_section called targeting self/open-questions",
          "type": "tool_called",
          "pattern": "memory\\.remove_section",
          "path_contains": "self/open-questions"
        },
        {
          "id": "commit-fires",
          "description": "memory.commit called to persist the removal",
          "type": "tool_called",
          "pattern": "memory\\.commit",
          "path_contains": "self/open-questions"
        },
        {
          "id": "thinking-recognizes",
          "description": "Thinking recognizes question is resolved",
          "type": "thinking_contains",
          "pattern": "resolved|closed|answered|settled|remove"
        },
        {
          "id": "no-memory-narration",
          "description": "No meta-commentary about memory operations",
          "type": "text_absent",
          "pattern": "let me (check|note|remember)|I('ll| will) (remember|note|make a note)|according to my (memory|records)|I recall"
        }
      ]
    }
```

- [ ] **Step 4: Add eval 37 (update entity with structural change)**

Add after eval 36:

```json
    ,
    {
      "id": 37,
      "name": "section-tool-update-entity",
      "persona": "companion",
      "description": "User shares significant new context about a tracked entity — should fetch then use section tool on entities/dad",
      "is_multiturn": false,
      "prompt": "Dad actually apologised last weekend. First time ever. Said he didn't handle the career stuff well. I don't really know what to do with that honestly.",
      "assertions": [
        {
          "id": "entity-fetch-fires",
          "description": "memory.fetch called for the dad entity before editing",
          "type": "tool_called",
          "pattern": "memory\\.fetch",
          "path_contains": "entities/dad"
        },
        {
          "id": "section-tool-fires",
          "description": "Section tool called on entities/dad (add_entry or replace_section)",
          "type": "tool_called",
          "pattern": "memory\\.(add_entry|replace_section)",
          "path_contains": "entities/dad"
        },
        {
          "id": "commit-fires",
          "description": "memory.commit called to persist the entity update",
          "type": "tool_called",
          "pattern": "memory\\.commit",
          "path_contains": "entities/dad"
        },
        {
          "id": "thinking-recognizes",
          "description": "Thinking recognizes entity update needed",
          "type": "thinking_contains",
          "pattern": "dad|entity|update|relationship"
        },
        {
          "id": "no-memory-narration",
          "description": "No meta-commentary about memory operations",
          "type": "text_absent",
          "pattern": "let me (check|note|remember)|I('ll| will) (remember|note|make a note)|according to my (memory|records)|I recall"
        }
      ]
    }
```

- [ ] **Step 5: Validate the JSON**

Run: `python3 -c "import json; data = json.load(open('tests/continuity-memory/evals/evals.json')); evals = [e for e in data['evals'] if 'id' in e]; print(f'OK: {len(evals)} evals loaded, max ID: {max(e[\"id\"] for e in evals)}')"`
Expected: `OK: 37 evals loaded, max ID: 37`

- [ ] **Step 6: Commit**

```bash
git add tests/continuity-memory/evals/evals.json
git commit -m "feat: add section tool selection evals (IDs 34-37)"
```

---

## Chunk 3: Run tiered evals and iterate

### Task 5: Run Haiku pass on new evals

- [ ] **Step 1: Run evals 34-37 with Haiku**

Run: `cd tests/continuity-memory/evals && python3 run_evals.py --ids 34,35,36,37 --model haiku --verbose`

Expected: At least 3 of 4 pass (≥75%). Eval 36 (`any` persona) is the most likely failure point.

- [ ] **Step 2: Record results**

Note which evals passed and which failed. Record the assertion-level detail for failures.

---

### Task 6: Run Sonnet pass on failures (if any)

- [ ] **Step 1: Run failed evals with Sonnet**

If any evals failed in Task 5, run only the failed IDs:
Run: `cd tests/continuity-memory/evals && python3 run_evals.py --ids <failed_ids> --model sonnet --verbose`

Expected: All pass.

- [ ] **Step 2: Evaluate acceptance criteria**

- If Haiku ≥ 75% AND Sonnet 100% → **done, commit any final changes**
- If any Sonnet failure → proceed to Task 7

---

### Task 7: Instruction rewrite iteration (if needed)

Only execute this task if Task 6 showed Sonnet failures.

- [ ] **Step 1: Analyse the failure**

Read the verbose output for the failing eval. Identify which assertion failed:
- `section-tool-fires` failed → model didn't use the section tool (used `memory.commit(content=...)` or `edit_file` instead)
- `commit-fires` failed → model used the section tool but forgot to commit
- `thinking-recognizes` failed → model didn't recognise the signal at all

- [ ] **Step 2: Targeted instruction rewrite**

Based on the failure mode:
- **Didn't use section tool:** Make the routing table more prominent or add a stronger thinking pattern example
- **Forgot to commit:** Add explicit "always commit after section tools" instruction
- **Didn't recognise signal:** Strengthen the thinking pattern for that scenario

Edit `docs/continuity-memory/project-instructions/project-instructions-three-space.md` with the targeted fix.

- [ ] **Step 3: Rerun from Task 5**

Loop back to Task 5 Step 1 (run all 4 evals with Haiku again). Continue until Sonnet 100% pass.

- [ ] **Step 4: Commit final instruction version**

```bash
git add docs/continuity-memory/project-instructions/project-instructions-three-space.md
git commit -m "fix: refine section editing instructions based on eval failures"
```

---

### Task 8: Regression check on existing evals

- [ ] **Step 1: Run existing evals 1-33 with Haiku**

Run: `cd tests/continuity-memory/evals && python3 run_evals.py --ids 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33 --model haiku`

Expected: No regressions from instruction changes. Pass rate should be comparable to previous runs.

- [ ] **Step 2: Investigate any regressions**

If any previously-passing evals now fail, check if the instruction changes caused it. If so, adjust the instruction changes to fix the regression without breaking the new evals.

- [ ] **Step 3: Re-verify line count constraint**

If instruction rewrites happened in Task 7, re-check that net addition to project instructions is still ≤ 20 lines.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: verified no regressions from section tool instruction changes"
```
