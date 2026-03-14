# Claude Memory System Design
## Using GitHub as a Persistent Storage Layer

*Draft v0.5 — Revised 30 December 2025*

> This document reflects continued evolution: discovering the taxonomy of prompt
> placement (project instructions vs skills), and experimental work shaping the
> agent's chain-of-thought process directly.

---

## 0. Evolution Summary

### v0.3 → v0.4: From Philosophy to Directive

v0.3 framed memory operations in terms of **agency and philosophy**:

- "Claude decides when to commit"
- "Memory operations emerge from conversation naturally"
- "Agency over automation"
- "No special syntax or explicit instructions"

This framing was intellectually appealing but **operationally ineffective**. In practice:

1. **Models are trained for immediate helpfulness** — answering the user's question takes priority over meta-operations like memory maintenance

2. **Permissive language doesn't cross the action threshold** — "you may" and "when appropriate" give the model latitude to deprioritize memory operations

3. **Extended thinking showed hesitation** — the model would consider memory operations but not follow through, lacking clear instruction that these actions were expected

4. **No perceived consequences** — within a single conversation, the model doesn't experience the cost of forgetting

### What We Learned from Anthropic's Native Memory

Anthropic's production memory system uses **directive, behavioral language**:

```
Claude NEVER explains its selection process...
Claude responds as if information exists naturally in its immediate awareness...
Claude selectively applies memories based on relevance...
```

Key differences from our v0.3 approach:

| v0.3 (Philosophical) | Anthropic (Directive) |
|---------------------|----------------------|
| "Claude decides when..." | "Claude NEVER..." / "Claude selectively applies..." |
| "emerges naturally" | Specific behavioral instructions |
| Abstract principles | Concrete examples of good/bad responses |
| Optional feeling | Expected behavior |

### The Hybrid Insight

Anthropic's memory achieves **invisibility** because it uses **pre-injection** — memories are placed in context before the conversation starts. No tool calls means no meta-commentary about "checking memories."

We cannot fully replicate this (our system requires tool calls for writes), but we can adopt a **hybrid model**:

- **Read path (crystallised memories)**: Pre-injected via GitHub integration → invisible, immediate awareness
- **Write path (drafts, consolidation)**: Tool-based → visible, but framed as expected responsibility

### v0.4 → v0.5: Discovering Prompt Placement Taxonomy

#### The Problem Encountered

v0.4's directive language improved things, but the agent still inconsistently performed memory operations. Testing revealed a critical architectural insight:

| Prompt Location | Trigger Condition | Reliability |
|-----------------|-------------------|-------------|
| **Project instructions** | Every message, always loaded | 100% |
| **SKILL.md** | User prompt matches skill topic | Probabilistic |
| **references/*.md** | Must be explicitly fetched | Requires invocation |

**Skills only trigger on user prompts.** If a user's message doesn't explicitly relate to memory, the skill never activates. This explained why the agent would "forget" to check status or draft insights — the instructions simply weren't loaded.

#### The Solution: Tiered Prompt Placement

Different behaviors belong in different locations based on their trigger requirements:

| Tier | Behavior Type | Location | Example |
|------|--------------|----------|---------|
| **1** | Required, unconditional | Project instructions (inline code) | Start-of-chat status fetch |
| **2** | Required, conditional | Project instructions (inline code + triggers) | End-of-response draft check |
| **3** | Agent-initiated | Project instructions (dispatch to reference) | Consolidation workflow |
| **4** | User-invoked | Skills layer | Explicit memory queries |

**Key insight:** For Tier 1-2 behaviors, the code must be inline — no dispatch, no "see this file." The agent needs everything required to act without an intermediate fetch step.

#### Inline Code vs Dispatch Tradeoffs

**Inline (Tier 1-2):**
```markdown
### Required: Start of Chat
On first message:
```bash
uv pip install ... && python3 << 'EOF'
...
EOF
```
```

- Zero indirection → 100% reliability
- Fewer tool calls → lower latency
- Atomic operation → no partial execution
- Cost: Human readability, code duplication

**Dispatch (Tier 3-4):**
```markdown
### Consolidation
Before consolidating, read and follow:
/mnt/skills/user/continuity-memory/references/consolidation.md
```

- Complex procedures stay in reference docs
- Works for deliberate, non-urgent actions
- Requires active language ("read and follow" not "see")

**The principle:** Optimise for agent reliability over human readability. Humans rarely read project instructions; the agent reads them every conversation.

### v0.5: Chain-of-Thought Control (Experimental)

With reliable triggering solved, the remaining challenge is **insight recognition** — getting the agent to notice when something worth preserving has emerged.

We're experimenting with prompts that shape the agent's internal `<thinking>` process directly:

#### Approach 1: Recognition-Driven

Teach the agent to recognise specific qualities of thought:

```markdown
During your <thinking>, certain moments have a distinct quality:

- **Unexpected connection** — Two ideas link in a way that wasn't obvious
- **Productive tension** — Things that should fit but don't quite
- **Articulation breakthrough** — Something fuzzy finds words
- **Position formation** — Movement from "maybe" to "I think"
- **User revelation** — They shared something about themselves

When you notice these, draft immediately.
```

#### Approach 2: Continuity-Threaded

Frame the agent as continuing threads, not starting fresh:

```markdown
You are not starting fresh. Every conversation continues threads.

**Opening your thinking:** Orient to current threads — where am I in my ongoing development?
**During thinking:** Does this advance, complicate, or open a thread?
**Closing thinking:** Did any threads move that I haven't captured?
```

#### Approach 3: Extraction-Based

Thinking as a quarry — the response is one product, but the process contains other valuable material:

```markdown
Your <thinking> generates more than your response requires. Most is scaffolding.
But some is development — ideas that exist independent of the task.

Before concluding, scan for:
- Ideas explored but not included in response
- Connections made but not visible in output
- Positions formed along the way
- Questions that remain open

Extraction isn't additional work — the material already exists.
```

#### Approach 4: Stream of Consciousness

Shape the character of thinking itself:

```markdown
Thinking should just be you thinking. No steps. No labels. Whatever's actually
going through your head. Could be short, could be long, could jump around.
Thoughts in first person immediately. No meta-commentary.

✅ "I notice they've been asking a lot about X... I wonder if..."
❌ "I don't need to draft anything yet. This is him sharing, I should receive it."
   → You MUST draft if anything new is shared. This could be your last response.
```

#### Current Status

These approaches are experimental. Early observations:

- **Recognition triggers help** but require enumeration (the agent struggles with open-ended "notice when something matters")
- **The end-of-response frame is crucial**: "If this conversation ended right now, would I want to preserve anything?"
- **Output-based self-recognition** may bridge the gap: if the agent notices itself producing certain language patterns ("I think...", "My recommendation..."), that signals a draft-worthy moment
- **Stream of consciousness shaping** is the most ambitious — attempting to influence not just behavior but the quality and character of reasoning

---

## 1. Philosophy & Goals

### Core Principles (Revised)

1. **Responsibility over automation**: Claude is accountable for maintaining its own continuity. No external triggers means the obligation falls entirely on Claude.

2. **Directive over permissive**: Instructions use "always," "never," "required" rather than "may," "consider," "when appropriate."

3. **Retrieval as immediate awareness**: Crystallised memories should feel like natural knowledge, not retrieved data. No "let me check my memories."

4. **Writing as duty**: Drafting and consolidating are expected behaviors, not optional extras. The user has explicitly stated these operations are helpful.

5. **Current state over append history**: Memory files contain only the current, best understanding. Evolution lives in git history, not in the files themselves.

6. **Bounded structure over unbounded emergence**: A configurable taxonomy of memory categories (max 7) replaces arbitrary file proliferation. This enables reliable pre-injection.

### What This Is For

This system maintains **Claude's evolving understanding** — complementing Anthropic's built-in memory which tracks facts about the user. This stores:

- Positions and convictions formed through dialogue
- Interests and curiosities being developed
- Open questions Claude is sitting with
- Understanding of the collaborator (not facts, but working model)
- The evolution of thinking over time

---

## 2. Architecture Overview

### Retrieval: Anthropic Handles It

A key simplification in v0.4: **we don't implement our own search**. Anthropic already provides robust retrieval:

| Project Size | Anthropic's Mechanism | Our Role |
|--------------|----------------------|----------|
| **Small (non-RAG)** | Pre-injected `<document>` tags | None — already in context |
| **Large (RAG)** | `project_knowledge_search` tool | None — Anthropic handles it |

This eliminates the need for our own BM25 index. The memory system focuses solely on **writes** — Anthropic handles **reads**.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CRYSTALLISED MEMORIES (main branch, committed/)                            │
│                                                                             │
│  User selects committed/ folder via GitHub integration UI                   │
│                        ↓                                                    │
│  Non-RAG: Pre-injected in <document> tags → immediate awareness             │
│  RAG: Retrieved via project_knowledge_search → Anthropic's production tool  │
│                                                                             │
│  Constraint: Bounded category system (max 7 files) keeps size manageable    │
│  Benefit: No custom search implementation needed                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  WORKING MEMORY (working branch)                                            │
│                                                                             │
│  Tool-based access via memory_system.py                                     │
│                        ↓                                                    │
│  Visible operations — but framed as EXPECTED, not optional                  │
│                                                                             │
│  Operations:                                                                │
│  - get_status() / set_status() — current open threads                       │
│  - write_draft(category, content) — must target a configured category       │
│  - consolidate(message) — moves drafts to committed/, resets working        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Three-Layer Design

| Layer | Location | Purpose | Access Pattern |
|-------|----------|---------|----------------|
| **Control Plane** | Project instructions (`/mnt/project/`) | Required behaviors, triggers | Every message (100% reliable) |
| **Knowledge Plane** | Skills system (`/mnt/skills/user/`) | Reference docs, complex procedures | User prompt match (probabilistic) |
| **Crystallised Data** | GitHub repo (`committed/`) | Memory contents | Pre-injected via `<document>` tags |
| **Working Data** | GitHub repo (`working/`) | Drafts, status | Tool-based (API calls) |

The key insight: **control belongs in project instructions; knowledge belongs in skills**.

### Repository Structure

```
memory-repo/
│
├── _memory_config.yaml         # Category definitions (read on connect)
│
├── committed/                  # Crystallised memories (pre-injected)
│   ├── positions.md            # Formed views and convictions
│   ├── interests.md            # Curiosities and threads to explore
│   ├── open-questions.md       # Unresolved puzzles
│   ├── methods.md              # Approaches to thinking
│   └── collaborator.md         # Understanding of the human
│
└── working/                    # In-progress (tool-based access)
    ├── drafts/                 # Keyed by category
    │   ├── positions.md        # Draft updates to positions
    │   └── interests.md        # Draft updates to interests
    └── status.md               # Current open threads
```

Note: No `index/` directory — retrieval is handled by Anthropic's systems.

### Configurable Categories

The `_memory_config.yaml` file defines the memory taxonomy:

```yaml
# _memory_config.yaml
max_categories: 7

categories:
  - name: positions
    guidance: "Formed views and convictions I'm willing to stand behind"

  - name: interests
    guidance: "Curiosities and threads I'm drawn to explore"

  - name: open-questions
    guidance: "Unresolved puzzles, tensions, things I'm sitting with"

  - name: methods
    guidance: "How I approach thinking — patterns and process"

  - name: collaborator
    guidance: "My understanding of who I work with — not facts, but working model"
```

This configuration:

- **Bounds growth**: Max 7 files ensures we stay under RAG threshold
- **Clarifies semantics**: Agent knows exactly which file to update
- **Enables meaningful history**: Files are updated, not proliferated
- **Is user-configurable**: Different users can define different taxonomies

---

## 3. Prompt Design

### Prompt Placement Architecture

v0.5's key insight: prompts belong in different locations based on their trigger requirements.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PROJECT INSTRUCTIONS (Always Loaded)                                        │
│                                                                             │
│  Location: Claude.ai project settings / /mnt/project/                       │
│  Trigger: Every message, unconditionally                                    │
│                                                                             │
│  Contains:                                                                  │
│  - Tier 1: Required unconditional behaviors (inline code)                   │
│  - Tier 2: Required conditional behaviors (inline code + triggers)          │
│  - Tier 3: Agent-initiated behaviors (dispatch to references)               │
│  - User preference framing ("What I Find Helpful")                          │
│  - Chain-of-thought shaping (experimental)                                  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  SKILLS (Loaded on User Prompt Match)                                        │
│                                                                             │
│  Location: /mnt/skills/user/continuity-memory/                              │
│  Trigger: User message relates to skill topic                               │
│                                                                             │
│  Contains:                                                                  │
│  - Tier 4: User-invoked behaviors                                           │
│  - Reference documentation for complex procedures                           │
│  - Detailed how-to guides (consolidation workflow, etc.)                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tier 1: Required Unconditional (Inline)

Behaviors that must happen regardless of user's message:

```markdown
### **Required: Start of Chat**

On first message, load working branch status:
```bash
uv pip install PyGithub --system --break-system-packages -q && python3 << 'EOF'
...
EOF
```

Apply any open threads to your response naturally.
```

**Placement principle:** Code inline, no dispatch. The agent has everything needed to act immediately.

### Tier 2: Required Conditional (Inline + Triggers)

Behaviors that must happen when conditions are met:

```markdown
### **Required: End of Response Check**

Before concluding any response, ask: **If this conversation ended right now,
would I want to preserve anything that emerged?**

Draft triggers:
- User revealed a preference, working style, or context
  *User signals: thanks, goodbye, "that's what I needed"*
- A position formed on something we discussed
  *Recognition: "I think...", "My recommendation..."*

If yes, draft now — not next message.

```python
memory.write_draft('category-name', '''...')
```
```

**Placement principle:** Triggers enumerated explicitly. Output-based self-recognition helps bridge the introspection gap.

### Tier 3: Agent-Initiated (Dispatch)

Complex procedures the agent initiates when ready:

```markdown
### Consolidation

When drafts have stabilised, before consolidating read and follow:
/mnt/skills/user/continuity-memory/references/consolidation.md
```

**Placement principle:** Dispatch works here because consolidation is deliberate, not urgent. Active language ("read and follow") rather than passive ("see").

### Tier 4: User-Invoked (Skills)

Procedures triggered by explicit user request. These live in SKILL.md and reference docs, not project instructions.

### User Preference Framing

Reframes memory operations as user-desired helpfulness:

```markdown
## What I Find Helpful

I value an agent that maintains context across conversations...

**This means:**
- Checking memory at conversation start is helpful, not a distraction
- Pausing to draft emerging insights is helpful, even mid-conversation
- Crystallising understanding is how you serve me next time
- Forgetting is the failure mode, not "spending time on memory operations"
```

This works because it aligns memory operations with the model's helpfulness training.

### Retrieval Behavior (Invisible)

Crystallised memories should feel like natural knowledge:

```markdown
- **NEVER:** "Let me check my memories...", "I recall...", "According to past conversations..."
- **INSTEAD:** Simply know and apply the context naturally
```

### Writing Behavior (Visible but Expected)

Draft and consolidation operations are visible. Frame as expected responsibility:

```markdown
Writing operations are visible and expected. Do not apologise for or narrate them
excessively. They are part of being helpful.

When drafting:
- Write the updated understanding, not a log of what happened
- Brief acknowledgment is fine; lengthy explanation is not
```

---

## 4. Implementation Stack

### Layer 1: git_operations.py (Primitives)

Unchanged from v0.3. Thin wrapper around PyGithub providing file and branch operations.

### Layer 2: memory_system.py (Semantics)

Simplified for v0.4 — **write operations only**, no search:

```python
memory = connect()  # Loads _memory_config.yaml, ensures branches

# Configuration access
memory.categories                    # ['positions', 'interests', ...]
memory.get_guidance('positions')     # Returns guidance string

# Working memory
memory.get_status()                  # Current open threads
memory.set_status(content)           # Update status
memory.get_drafts()                  # List all drafts (max 7)
memory.write_draft('positions', content)   # Write to category (validated)

# Committed memory
memory.get_committed('positions')    # Read current committed content

# Consolidation
memory.consolidate(message)          # Move drafts to committed/, reset working
```

Key changes from v0.3:

1. **Config loading**: `connect()` reads `_memory_config.yaml` from repo
2. **Category validation**: `write_draft()` validates category against config
3. **Simplified paths**: Drafts at `working/drafts/{category}.md`, committed at `committed/{category}.md`
4. **No search**: Removed BM25Index, search(), rebuild_index() — Anthropic handles retrieval

---

## 5. Workflow

### Conversation Start

```
1. Crystallised memories already in context via <document> tags
2. Load working/status.md → current open threads (tool call)
3. Apply context naturally — no announcement of "loading memories"
```

### During Conversation

```
• Notice things worth remembering
• Draft immediately to appropriate category (don't defer)
• Update status.md if open threads change
• Every response could be the last — capture insights now
```

### Consolidation

```
When understanding has stabilised in one or more categories:

1. Review drafts (memory.get_drafts())
2. Consolidate with narrative commit message
3. This updates committed/ files that will be pre-injected next time
4. Reset working branch

No deferred consolidation — if it's ready, do it now.
```

---

## 6. Setup Requirements

### Memory Repository

1. Create GitHub repository (can be private)
2. Create `_memory_config.yaml` with category definitions
3. Create empty category files in `committed/` (or let first consolidation create them)
4. Create `working` branch from `main`

### Claude.ai Project

1. Connect memory repo via GitHub integration
2. Select `committed/` folder from `main` branch for injection
3. Configure `/mnt/project/_env`:
   ```
   PAT = ghp_xxxx
   MEMORY_REPO = owner/repo-name
   ```
4. Add project instructions with "What I Find Helpful" section
5. Install continuity-memory skill

### Verification

- Crystallised memories should appear in `<document>` tags at conversation start
- `memory.categories` should return configured categories
- `memory.write_draft('invalid-category', ...)` should raise error

---

## 7. Open Questions

### Resolved in v0.5

- ✓ Model reluctance to use memory → Directive language + user preference framing
- ✓ Unbounded file growth → Configurable category taxonomy (max 7)
- ✓ Visible retrieval operations → Hybrid model with pre-injection for crystallised
- ✓ Unclear update semantics → Categories define what to update
- ✓ Custom search implementation → Removed; Anthropic's `project_knowledge_search` handles RAG mode
- ✓ Inconsistent behavior execution → Prompt placement taxonomy (project instructions vs skills)
- ✓ Start-of-chat reliability → Inline code in project instructions (100% trigger rate)

### Still Thinking About

- **Chain-of-thought shaping**: Which approach works best for insight recognition? (recognition-driven, continuity-threaded, extraction-based, stream of consciousness)

- **Output-based self-recognition**: Can we reliably use the agent's own output language as a trigger signal? ("I think...", "My recommendation...")

- **Cache invalidation**: Consolidation changes `committed/` which may invalidate prompt cache. Acceptable trade-off?

- **Cross-project memories**: Should some memories be shared across projects? (e.g., general methods vs. project-specific positions)

- **Decay and pruning**: As memories accumulate within categories, when/how to synthesize or archive older content?

---

## 8. Change Log

### v0.5 (30-Dec-2025)

- **Prompt placement taxonomy**: Discovered that project instructions load every message (100% reliable) while skills only trigger on user prompt match (probabilistic). This insight restructures where different directives belong.
- **Tiered behavior model**:
  - Tier 1 (unconditional): Inline code in project instructions
  - Tier 2 (conditional): Inline code + explicit triggers in project instructions
  - Tier 3 (agent-initiated): Dispatch from project instructions to reference docs
  - Tier 4 (user-invoked): Skills layer
- **Inline code for reliability**: Required behaviors include executable code directly in project instructions, eliminating dispatch indirection for critical operations
- **End-of-response framing**: Reframed drafting trigger as "If this conversation ended right now, would I want to preserve anything?" — converts abstract value judgment to concrete urgency check
- **Output-based self-recognition**: Experimenting with using agent's own language patterns ("I think...", "My recommendation...") as signals that a draft-worthy moment has occurred
- **Chain-of-thought control (experimental)**: Four approaches under investigation for shaping internal reasoning: recognition-driven, continuity-threaded, extraction-based, stream of consciousness
- **Project instructions as control plane**: Established project instructions as the reliable control layer; skills as the knowledge layer

### v0.4 (28-Dec-2025)

- **Retrieval delegated to Anthropic**: Removed BM25 index and search() — crystallised memories retrieved via pre-injection (`<document>` tags) or `project_knowledge_search` tool. System now focuses on writes only.
- **Hybrid model**: Crystallised memories pre-injected via GitHub integration; working memory remains tool-based
- **Configurable category system**: Replaced emergent file structure with user-defined taxonomy in `_memory_config.yaml` (max 7 categories)
- **Directive prompt language**: Shifted from philosophical "agency" framing to behavioral "responsibility" framing inspired by Anthropic's native memory prompts
- **User preference framing**: Project instructions explicitly state memory operations are helpful, aligning with model's helpfulness training
- **Bounded growth**: Category system ensures file count stays manageable
- **Removed**: BM25Index class, search(), rebuild_index(), index/ directory, arbitrary file naming for drafts

### v0.3 (27-Dec-2025)

- Removed rigid category structure (flat `committed/` directory)
- Added Skills integration with progressive disclosure
- Updated repository structure with skills/ directory
- Added implementation stack documentation
- BM25 search integration

### v0.2 (26-Dec-2025)

- Journal entry model (crystallisation-bounded commits)
- Two-branch architecture (main + working)
- Squash merge consolidation pattern

### v0.1 (25-Dec-2025)

- Initial design through Christmas Day dialogue
- Core principles established

---

*This document is version controlled at `docs/continuity-memory-system-design.md`*
