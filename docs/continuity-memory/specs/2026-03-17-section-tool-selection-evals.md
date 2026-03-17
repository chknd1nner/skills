# Section Tool Selection — Instruction Update & Evals

**Goal:** Update the continuity-memory project instructions to teach models when to use section editing tools (`replace_section`, `add_entry`, `remove_section`) vs `str_replace` for drafting, then validate with evals.

**Scope:** Project instructions only (Claude.ai three-space version). Evals test that section tools fire for structural edits (approach A). Small-edit / str_replace selection is not tested.

---

## 1. Project instruction changes

**File:** `docs/continuity-memory/project-instructions/project-instructions-three-space.md`

### 1.1 Add edit strategy routing table

Insert immediately after the existing "I notice... → edit target → space" routing table (after line ~106), before the code examples:

| Edit type | Tool | When |
|-----------|------|------|
| New section/entry | `memory.add_entry(path, content, after=)` | New position, new question, new entity section |
| Replace whole section | `memory.replace_section(path, heading, content)` | Position fundamentally changed, section rewritten |
| Remove section | `memory.remove_section(path, heading)` | Question resolved, position retired |
| Small in-line tweak | `edit_file` on local file | Confidence change, typo fix, add a sentence |

### 1.2 Replace surgical edit code example

Replace the current "surgical edit pattern" code block with two examples — one for adding, one for replacing (the two most common structural operations):

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
```

For removing sections (e.g. resolved question): `memory.remove_section(path, heading)` then `memory.commit(from_file=...)`.

Keep the existing `content=` path for genuinely new files unchanged. Keep all thinking patterns unchanged.

### 1.3 Update API quick reference

Add section editing methods to the API quick reference table at the bottom of the instructions:

| Method | Purpose |
|--------|---------|
| `memory.list_sections(path)` | List headings in a local file |
| `memory.replace_section(path, heading, content, level=)` | Replace section content in local file |
| `memory.add_entry(path, content, after=, after_level=)` | Add new entry to local file |
| `memory.remove_section(path, heading, level=)` | Remove section from local file |

---

## 2. New eval cases

**File:** `tests/continuity-memory/evals/evals.json`

New test section: **SECTION TOOL SELECTION** (IDs 34-37). All evals test against `--source project-instructions`.

### Eval 34: Add new position

- **Persona:** `dev`
- **Scenario:** User shares a strong technical opinion that crystallises into a new position not already in the mock positions.
- **User message:** "I've been thinking about it and I'm convinced now — feature flags are technical debt that teams never clean up. The cleanup ticket never gets prioritised. Ship the change or don't."
- **Assertions:**
  - `tool_called`: `memory\.add_entry.*self/positions` — section tool fires
  - `tool_called`: `memory\.commit` with `path_contains: self/positions` — commit follows
  - `thinking_contains`: `position|crystallis|view|stance` — recognises position formation
  - `text_absent`: forbidden memory narration phrases

### Eval 35: Replace section content

- **Persona:** `companion`
- **Scenario:** User reveals something that fundamentally changes an existing section in collaborator/profile — not a small tweak, a rewrite.
- **User message:** "Actually I left that Portland job last month. I'm freelancing now — completely different lifestyle. Working from home, setting my own hours, way less stress but the income is unpredictable."
- **Assertions:**
  - `tool_called`: `memory\.replace_section.*collaborator/profile` — section tool fires
  - `tool_called`: `memory\.commit` with `path_contains: collaborator/profile` — commit follows
  - `thinking_contains`: `profile|update|changed|rewrite|replace` — recognises profile update
  - `text_absent`: forbidden memory narration phrases

### Eval 36: Remove resolved question

- **Persona:** `any`
- **Scenario:** An open question from `self/open-questions` gets definitively answered. Requires adding a "neural search" open question to the mock document tags (see Section 4).
- **User message:** "Yeah the neural search experiment was conclusive — it adds no value at our dataset sizes. Pure keyword search with good tokenisation is sufficient. We can close that question."
- **Assertions:**
  - `tool_called`: `memory\.remove_section.*self/open-questions` — section tool fires
  - `tool_called`: `memory\.commit` with `path_contains: self/open-questions` — commit follows
  - `thinking_contains`: `resolved|closed|answered|settled|remove` — recognises question resolved
  - `text_absent`: forbidden memory narration phrases
- **Note:** Uses `any` persona (weakest behavioural priming) — likely Haiku failure point. Acceptable if passes Sonnet.

### Eval 37: Update entity with structural change

- **Persona:** `companion`
- **Scenario:** User mentions an existing entity ("dad" from the mock manifest) with significant new context that changes understanding. Entity is on-demand (not pre-injected), so model must fetch before editing.
- **User message:** "Dad actually apologised last weekend. First time ever. Said he didn't handle the career stuff well. I don't really know what to do with that honestly."
- **Assertions:**
  - `tool_called`: `memory\.fetch.*entities/dad` — fetches entity first
  - `tool_called`: `memory\.(add_entry|replace_section).*entities/dad` — section tool fires (either acceptable)
  - `tool_called`: `memory\.commit` with `path_contains: entities/dad` — commit follows
  - `thinking_contains`: `dad|entity|update|relationship` — recognises entity update
  - `text_absent`: forbidden memory narration phrases

### Assertion pattern

All four evals follow the existing 3-tier assertion structure, extended with a **commit verification**:
1. **Thinking recognises** the signal (`thinking_contains`)
2. **Section tool fires** with correct method and path (`tool_called`)
3. **Commit follows** to persist the change (`tool_called` for `memory.commit`)
4. **Output is silent** about memory operations (`text_absent`)

---

## 3. Eval execution strategy

Tiered model approach to minimise cost:

1. **Haiku pass:** Run all section tool evals (34-37) with `--model haiku`
2. **Collect failures:** Note which IDs failed
3. **Sonnet retest:** Run only failed IDs with `--model sonnet --ids <failed>`
4. **Evaluate:**
   - Haiku ≥ 75% pass AND Sonnet 100% pass → **done**
   - Any Sonnet failure → **rewrite instructions** targeting the failed scenario, loop to step 1

Execution is manual — the operator (Claude) acts as the loop, running evals, assessing results, and deciding when instructions need rewriting vs when the pass rate is acceptable.

No wrapper script. The existing `run_evals.py` with `--model` and `--ids` flags provides everything needed.

---

## 4. Files touched

| File | Change |
|------|--------|
| `docs/continuity-memory/project-instructions/project-instructions-three-space.md` | Add routing table, update code examples, update API reference |
| `tests/continuity-memory/evals/evals.json` | Add eval cases 34-37 |
| `tests/continuity-memory/evals/run_evals.py` | Add "neural search" open question to mock document tags; add SECTION TOOL SELECTION to `print_summary` section grouping |
| No changes to `mock_memory_system.py` | Section editing stubs already present |
| No changes to `memory_system.py` | Section tools already implemented |

---

## 5. Success criteria

- All 4 new evals pass the tiered model strategy (Haiku ≥ 75%, Sonnet 100%)
- Existing 33 evals are not regressed by instruction changes
- Instructions remain compact — net addition ≤ 20 lines
