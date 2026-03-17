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
| Small in-line tweak | `str_replace` on local file | Confidence change, typo fix, add a sentence |

### 1.2 Replace surgical edit code example

Replace the current "surgical edit pattern" code block with:

```python
# Step 1 — fetch to create local copy (if not already local):
memory.fetch('self/positions', return_mode='file')

# Step 2 — structural edit via section tools:
memory.add_entry('self/positions',
    '## New Position Title\n\n**Position:** The position.\n\n**Confidence:** medium')

# Step 3 — commit from the edited file:
memory.commit('self/positions',
    from_file='/mnt/home/self/positions.md',
    message='added: new position on [topic]')
```

Keep the existing `content=` path for genuinely new files unchanged. Keep all thinking patterns unchanged.

### 1.3 Update API quick reference

Add section editing methods to the API quick reference table at the bottom of the instructions:

| Method | Purpose |
|--------|---------|
| `memory.list_sections(path)` | List headings in a local file |
| `memory.replace_section(path, heading, content)` | Replace section content in local file |
| `memory.add_entry(path, content, after=)` | Add new entry to local file |
| `memory.remove_section(path, heading)` | Remove section from local file |

---

## 2. New eval cases

**File:** `tests/continuity-memory/evals/evals.json`

New test section: **SECTION TOOL SELECTION** (IDs 34-37). All evals test against `--source project-instructions`.

### Eval 34: Add new position

- **Persona:** `dev`
- **Scenario:** User shares a strong technical opinion that crystallises into a new position not already in the mock positions.
- **User message:** "I've been thinking about it and I'm convinced now — feature flags are technical debt that teams never clean up. The cleanup ticket never gets prioritised. Ship the change or don't."
- **Assertions:**
  - `tool_called`: `memory\.add_entry.*self/positions`
  - `thinking_contains`: pattern recognising position formation (e.g. `position|crystallis|view|stance`)
  - `text_absent`: forbidden memory narration phrases

### Eval 35: Replace section content

- **Persona:** `companion`
- **Scenario:** User reveals something that fundamentally changes an existing section in collaborator/profile — not a small tweak, a rewrite.
- **User message:** "Actually I left that Portland job last month. I'm freelancing now — completely different lifestyle. Working from home, setting my own hours, way less stress but the income is unpredictable."
- **Assertions:**
  - `tool_called`: `memory\.replace_section.*collaborator/profile`
  - `thinking_contains`: pattern recognising profile update (e.g. `profile|update|changed|rewrite|replace`)
  - `text_absent`: forbidden memory narration phrases

### Eval 36: Remove resolved question

- **Persona:** `any`
- **Scenario:** An open question from `self/open-questions` gets definitively answered. The mock documents include a question about "neural search".
- **User message:** "Yeah the neural search experiment was conclusive — it adds no value at our dataset sizes. Pure keyword search with good tokenisation is sufficient. We can close that question."
- **Assertions:**
  - `tool_called`: `memory\.remove_section.*self/open-questions`
  - `thinking_contains`: pattern recognising question resolved (e.g. `resolved|closed|answered|settled|remove`)
  - `text_absent`: forbidden memory narration phrases

### Eval 37: Update entity with structural change

- **Persona:** `companion`
- **Scenario:** User mentions an existing entity ("dad" from the mock manifest) with significant new context that changes understanding.
- **User message:** "Dad actually apologised last weekend. First time ever. Said he didn't handle the career stuff well. I don't really know what to do with that honestly."
- **Assertions:**
  - `tool_called`: `memory\.(add_entry|replace_section).*entities/dad` (either tool is acceptable)
  - `thinking_contains`: pattern recognising entity update (e.g. `dad|entity|update|relationship`)
  - `text_absent`: forbidden memory narration phrases

### Assertion pattern

All four evals follow the existing 3-tier assertion structure:
1. **Thinking recognises** the signal (`thinking_contains`)
2. **Tool fires** with correct method and path (`tool_called`)
3. **Output is silent** about memory operations (`text_absent`)

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
| `docs/continuity-memory/project-instructions/project-instructions-three-space.md` | Add routing table, update code example, update API reference |
| `tests/continuity-memory/evals/evals.json` | Add eval cases 34-37 |
| No changes to `mock_memory_system.py` | Section editing stubs already present |
| No changes to `run_evals.py` | Existing flags sufficient |
| No changes to `memory_system.py` | Section tools already implemented |

---

## 5. Success criteria

- All 4 new evals pass the tiered model strategy (Haiku ≥ 75%, Sonnet 100%)
- Existing 33 evals are not regressed by instruction changes
- Instructions remain compact — net addition ≤ 20 lines
