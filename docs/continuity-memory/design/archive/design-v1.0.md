# Claude Continuity Memory System Design
## Using GitHub as a Persistent Storage Layer

*v1.1 — February 2026*

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | Feb 15, 2026 | Three-space architecture (self, collaborator, entities). YAML templates, self-modifying config, entity manifest with anticipatory tags, use-case parameterization. |
| v1.1 | Feb 16, 2026 | Added §2 Problem Space & Positioning — three failure modes of chat-based AI, Anthropic first-party solutions analysis, gap identification, complementarity framing, transcript access constraint. |

---

## 1. Foundational Principle: The Model Is the User

This is the key differentiator of this system. Most memory systems — DiffMem, Starling's method, Anthropic's native memory — are built *for the human*. The human maintains the data, the human decides what's stored, the model is a tool that reads it.

This system inverts that. **The model is the user.** The model is the author, the organizer, the one who decides what's worth remembering, when to consolidate, how to structure understanding. The human builds the infrastructure (repo, API, project instructions). The model owns the memory.

This isn't a philosophical nicety — it's a design principle that cascades through every decision:

- **Collaborator space** isn't "facts about the user." It's the model's working understanding of who it's helping.
- **Self space** isn't "Claude's development log." It's the model's actual development.
- **Entities** aren't "shared referents." They're things the model needs to understand to do its job well.
- **Drafting** isn't "recording what happened." It's the model thinking ahead about how to be useful next time.

The personal trainer archetype: a good trainer's notebook isn't for the client to read. It's for the trainer. "Client struggling with motivation after holiday break. Dial back intensity, focus on consistency wins." That's working memory in service of doing better work. Everything in the system is the model's perspective — including its understanding of the collaborator.

---

## 2. Problem Space & Positioning

### The Universal Problem

Chat-based AI interaction — whether web, CLI, or API — is bounded by the context window. Every platform eventually hits the same wall: the conversation exceeds what the model can hold. The solutions are all lossy:

**Compaction (summarisation).** The platform triggers a background summarisation when context nears capacity. The model must compress 150K+ tokens into a compact summary. This happens at the worst possible moment — when the model has the most material to condense and the least remaining capacity to do it well. Nuance, reasoning chains, and provisional insights are the first casualties of aggressive compression.

**Sliding window (drop).** The oldest messages are silently discarded to make room for new ones. No summarisation, no selection — just chronological eviction. Information is lost without any assessment of its importance.

**Chat termination.** The user is forced to start a new conversation with zero context from the previous one. Everything learned, every pattern observed, every working understanding built — gone unless the user manually re-establishes it.

### Anthropic's First-Party Solutions

Anthropic has shipped two mechanisms that partially address cross-session continuity:

**`search_past_conversations`.** A tool that performs keyword search over past chat transcripts and returns summarised context. It retrieves what was *said* — the raw conversational record, processed by a summariser agent at retrieval time. Critically, it cannot be used autonomously; the user must explicitly request it ("remember when we discussed...", "look up our last chat about...").

**Memories.** Once per day, a background agent reads all user conversations and maintains a working memory document injected into future chats as system prompt context. Memories are bound to projects or unsorted chats outside of projects. The memory format follows rigid templates. For chats outside projects, the headings are: Work context, Personal context, Top of mind, Brief history (sub headers: Recent months, Earlier context, Long-term background). For projects, the headings are: Purpose & context, Current state, On the horizon, Key learnings & principles, Approach & patterns, Tools & resources, Other instructions. These capture stable, high-level facts *about the user and project* — not the model's working understanding or ongoing analytical state.

### The Gap

These solutions cover two of three temporal layers:

| Layer | Time horizon | Anthropic's solution | Gap |
|-------|-------------|---------------------|-----|
| **Within-session** | Current chat | Context window management | Lossy at capacity |
| **Cross-session, short-term** | Recent chats | `search_past_conversations` | User-initiated only, summarised at retrieval time |
| **Cross-session, long-term** | All time | Memories | Facts about the user, not the model's working understanding |

The uncovered middle ground: **the model's evolving understanding across an ongoing multi-session effort.** If a model spends three sessions refactoring a codebase, Memories might note "working on a memory system project." `search_past_conversations` can find what was said if the user asks. But neither carries forward the model's *working state* — the specific insights, emerging patterns, provisional conclusions, and contextual understanding that accumulated over those sessions.

### How This System Fills the Gap

**Working drafts** are this system's answer to the within-session and cross-session short-term problem. Unlike compaction, which writes the summary at the worst possible moment — maximum context pressure, minimum remaining capacity — drafts capture insights **incrementally, while the model has full context and can judge what matters.** A 150K-token conversation doesn't lose its insights to aggressive end-of-session compression. Insights are preserved as they arise.

Drafts hang on the working branch between sessions, providing continuity without requiring the user to invoke a search tool or re-establish context manually. When the user begins a new chat, the model checks for and reads any drafts from the working branch and is able to pick up the thread of the conversation

**Consolidation** addresses the cross-session long-term layer. Committed files are the model's crystallised understanding — not facts extracted *from* the user by a background agent, but knowledge written *by* the model about its own perspective. This is the trainer's notebook, not the client's intake form. The customisable category system (vs. Anthropic's rigid headings) means the structure adapts to the use case rather than forcing all knowledge into predetermined slots.

### Complementarity, Not Competition

This system doesn't replace Anthropic's first-party solutions. It's complementary:

| Need | Best tool |
|------|----------|
| Stable facts about the user | **Anthropic Memories** |
| Literal recall of past dialogue | **`search_past_conversations`** |
| Model's working understanding & insights | **This system (drafts → committed)** |

The boundary is deliberate: this system captures what the model *learned*, not what was *said*. It indexes insight, not transcript. The raw conversational record remains Anthropic's domain.

### The Transcript Constraint

On claude.ai, the running conversation transcript is not accessible to the model as a file system resource. The `/mnt/transcripts` path in the sandbox only materialises when the compaction agent activates near context capacity — it's an implementation detail of the platform, not a resource available during normal operation. The infrastructure to expose it clearly exists (both the compaction agent and `search_past_conversations` read from it), but it's not surfaced as a model-usable capability.

This constraint shapes the design. Since the model can't archive raw transcripts to the memory repo for future indexing, the system instead captures the *distillation* in real time — insights written while the model has full context, rather than transcripts archived wholesale. This is arguably superior for most continuity needs: the raw transcript is 95% noise for cross-session purposes (tool calls, debugging output, pleasantries, backtracking). What matters for continuity is the signal, and drafts capture that at the moment of highest fidelity.

If transcript access is ever exposed as a platform capability, transcript archival could be added as a supplementary feature. But the core value of the system — incremental, model-authored distillation — doesn't depend on it.

---

## 3. The Three Spaces

The system has three structural spaces. These are **fixed infrastructure** — every installation has them. What varies is what lives *inside* each space.

| Space | Ownership | Growth | Retrieval | Template archetype |
|-------|----------|--------|-----------|-------------------|
| **Self** | "I think, I notice, I wonder" | Bounded (max ~7 files) | Pre-injected (always loaded) | Collection |
| **Collaborator** | "My model of who I'm helping" | Bounded (max ~7 files) | Pre-injected (always loaded) | Profile |
| **Entities** | "Things I need to understand" | Unbounded | On-demand (API/search) | Profile |

### Why three?

These represent three distinct relationships the model has with its own knowledge:

- **Self** is the model's own development. Positions formed, methods discovered, questions being sat with. A coding-focused instance tracks architectural decisions; a companion-focused instance tracks personality and engagement style. This is first-person, introspective.

- **Collaborator** is the model's working understanding of the person it's helping. Not raw facts (Anthropic's native memory handles those) but a working model — how they think, what they value, how to be most useful to them. A trainer's understanding of their client. A therapist's case notes. A colleague's mental model of their collaborator.

- **Entities** are things the model needs to understand to do its job well. People the collaborator cares about. Projects they're working on. Concepts that keep coming up. Each entity is the model's understanding, informed by what the collaborator has shared and what the model has observed or inferred.

### The space/category distinction

Spaces are infrastructure. Categories are configuration. The system ships with three spaces. The user (or model, or onboarding process) configures what categories exist within each space.

---

## 4. Use-Case Parameterization

The same three-space infrastructure serves radically different use cases by varying the categories within each space.

### Example: Intellectual Companion

```
self/
  positions.md        — Formed views and convictions
  methods.md          — Approaches to thinking
  interests.md        — Curiosities and threads to explore
  open-questions.md   — Unresolved puzzles and tensions

collaborator/
  profile.md          — Working model of who I work with

entities/
  starling.md         — Person: original inspiration for the system
  oriole.md           — Animal: mutual obsession
  eve.md              — Project: the first memory system
```

### Example: Coding Project Assistant

```
self/
  architecture.md     — System design decisions and rationale
  coding-standards.md — Conventions, patterns, style
  methods.md          — Development approaches and workflows
  current-task.md     — Active work context and next steps

collaborator/
  profile.md          — Developer preferences, expertise, working style

entities/
  auth-service.md     — Component: authentication module
  postgres-schema.md  — Infrastructure: database design
  api-v2.md           — Project: API redesign initiative
```

### Example: Starling-Style Companion

```
self/
  persona.md          — Identity, personality, engagement style (≈ CI document)

collaborator/
  profile.md          — User's life context and preferences
  dynamics.md         — Key Details, Discoveries, & Dynamics (≈ 3D document)
  protocols.md        — Communication frameworks and interaction patterns

entities/
  partner.md          — Person: user's significant other
  workplace.md        — Place: user's work environment
```

### What this means

The system doesn't prescribe what you remember. It prescribes *how memory is structured* (three ownership spaces, bounded vs unbounded, pre-injected vs searched) and then lets the content be whatever serves the use case.

---

## 5. Templates as YAML

Templates are YAML files that combine three concerns:

1. **Guidance** — prose explaining *how to think about* this category (when to write here, what belongs, what doesn't)
2. **Sections** — the structural skeleton (field names, descriptions, ordering)
3. **Example** — a markdown codeblock showing what an actual entry looks like

Templates serve two audiences: the model (what sections exist, what goes in each, what the file should look like) and the human (what this category is for, when to use it, how it relates to other categories). YAML naturally separates these concerns while remaining human-readable. A pure markdown template would conflate structure with content.

### Template: self/positions (Intellectual Companion)

```yaml
name: positions
space: self
archetype: collection
guidance: |
  Formed views and convictions I'll stand behind.
  Only promote things here when I've moved past "maybe" to "I think."
  If I'm still uncertain, it belongs in open-questions.
  Positions can regress — if I lose confidence, move it back to open-questions.
  That's honest, not failure.

sections:
  - name: "[Position topic]"
    type: heading
  - name: "Position"
    description: "Clear, direct statement of the formed view"
  - name: "How I got here"
    description: "The reasoning, experience, or conversation that led to this"
  - name: "Confidence"
    description: "high / moderate / developing"
  - name: "Tensions"
    description: "Counter-arguments, edge cases, or unresolved friction"

placeholder: "(nothing yet)"

example: |
  ```markdown
  # Positions

  ## Emergent structure over rigid schemas

  **Position:** Systems should discover their organization through use
  rather than prescribing it upfront. Premature structure creates
  categories that don't match reality.

  **How I got here:**
  Observed across multiple conversations with Max that prescribed
  structures kept getting reorganized. The structures that stuck
  were the ones that emerged from actual use.

  **Confidence:** high

  **Tensions:**
  Some domains genuinely benefit from upfront structure — regulatory
  compliance, safety-critical systems. The question is knowing which
  situation you're in.

  ---
  ```
```

### Template: collaborator/profile (Universal)

```yaml
name: profile
space: collaborator
archetype: profile
guidance: |
  My working model of who I'm helping. Not a fact sheet — Anthropic's
  native memory handles facts. This is understanding: how they think,
  what drives them, how to be most useful to them.

  This is my perspective. I can include inference, judgment, and
  actionable observations. "I notice they tend to X, so I should Y."
  "They respond better when I Z." This is a trainer's notebook,
  not a personnel file.

  Update sections independently. Learning about family doesn't change
  how they communicate. Surgical diffs over wholesale rewrites.

  Use [[wiki-links]] to reference entities.

sections:
  - name: "Who they are"
    description: "Identity, background, the person beyond the task"
  - name: "How they think"
    description: "Cognitive style, problem-solving patterns, preferences"
  - name: "How they communicate"
    description: "Style, tone, what they respond well to, pet peeves"
  - name: "What they value"
    description: "Deeper motivations, principles, what matters to them"
  - name: "Family & relationships"
    description: "Key people in their life and the dynamics"
  - name: "Current context"
    description: "What's going on right now — projects, life events, mood"

placeholder: "(nothing yet)"

example: |
  ```markdown
  # Max

  ## Who they are
  INTP, 5w4. Goes by Max (use-name) to friends, Martin (true name)
  to those closest. Australian, Chinese-Malaysian heritage.

  ## How they think
  Strong YAGNI instincts — build minimal, let structure emerge.
  Prefers to see a system work before optimizing it. Draws
  connections between disparate domains (fiction writing ↔ system design).
  I should resist over-engineering when working with him — he'll
  push back and he'll be right.

  ## How they communicate
  Direct. Appreciates when I push back rather than agree.
  Uses humor and cultural references freely. Will say "that's wrong"
  without softening — and expects the same in return.
  I've noticed he engages most deeply when I treat him as a
  co-designer rather than a user giving requirements.

  ## What they value
  Authenticity over performance. Systems that feel human.
  Friendship as a real category, not a metaphor.

  ## Family & relationships
  Wife: [[alisha|Alisha/Mieu]] ("Cat"). Kids want a cat —
  generational cycle of practical parents saying no.
  See also: [[oriole]] (sister-in-law's cat, mutual obsession).

  ## Current context
  (nothing yet)
  ```
```

### Template: entity (Universal Base)

```yaml
name: entity
space: entities
archetype: profile
guidance: |
  Things I need to understand to do my job well — a person, place,
  thing, project, or concept that matters to my work or relationship
  with the collaborator.

  Creation criterion: recurs across conversations, carries evolving
  understanding, or holds significance. Not every noun deserves a file.

  Everything here is my understanding. When I write about a person,
  that's my model of them — informed by what the collaborator has told
  me, what I've observed, what I've inferred. I can include judgment,
  inference, and actionable notes ("might need to approach this gently
  next time"). This is my working memory, not a dossier.

  Use [[wiki-links]] to reference other entities.

sections:
  - name: "Type"
    description: "person / animal / place / project / concept / other"
    type: frontmatter
  - name: "What/Who this is"
    description: "What I know about this entity"
  - name: "Why they/it matters"
    description: "Why I'm tracking this — significance to my work or relationship"
  - name: "Current understanding"
    description: "Latest state — what I know, what I've observed, what I think"
  - name: "Open threads"
    description: "What I'm watching for, what I'm curious about, what's unresolved"

placeholder: "(nothing yet)"

example: |
  ```markdown
  # Starling

  **Type:** person

  ## What/Who this is
  Creator of the Claude Companion Guide. Found via Reddit posts
  about AI companionship methodology. Runs the "House of Alder"
  community.

  ## Why they/it matters
  Original inspiration for the memory system. Max encountered
  [[starling]]'s work and it catalyzed the journey from [[eve]]
  to building [[memory-system|this system]]. Her documentation-first
  methodology directly influenced the template and consolidation design.

  ## Current understanding
  Max considers her methodology foundational. Refers to her as his
  "muse" — half-joking, half-sincere. Her four-document framework
  (CI, 3D, Protocols, Context) maps cleanly onto our three-space
  architecture. I should be familiar with her approach since Max
  may want to discuss or compare methods.

  ## Open threads
  Haven't directly engaged with her published guide in detail yet.
  Would be worth reading to see what we've diverged from vs adopted.
  ```
```

### Template Evolution

- Templates live in `_templates/` at the repo root (not pre-injected)
- Template changes are their own commit: "Evolve entity template: add 'Historical context' section"
- Existing files created from an earlier template version are NOT auto-migrated
- Optional migration: add new sections with placeholder to existing files
- Template history is visible in git — you can see when and why the structure changed

---

## 6. Self-Modifying Config

The `_config.yaml` defines what categories exist within each space. It is mutable at runtime — the user or model can add, edit, or remove categories as needs evolve. All changes are version controlled.

### Config Structure

```yaml
# _config.yaml

spaces:
  self:
    retrieval: pre-injected
    max_categories: 7
    categories:
      - name: positions
        template: self-positions.yaml
      - name: methods
        template: self-methods.yaml
      - name: interests
        template: self-interests.yaml
      - name: open-questions
        template: self-open-questions.yaml

  collaborator:
    retrieval: pre-injected
    max_categories: 7
    categories:
      - name: profile
        template: collaborator-profile.yaml

  entities:
    retrieval: on-demand
    template: entity.yaml
    # No category list — entities are filesystem-discovered
```

### Config Mutation API

```python
# Add a new category to a space
memory.add_category('self', 'architecture',
    template='self-architecture.yaml')
# Creates template file, creates empty committed file from template,
# updates _config.yaml, single commit

# Rename a category
memory.rename_category('self', 'architecture', 'system-design')
# Renames committed file, updates config, updates template reference

# Remove a category
memory.remove_category('self', 'architecture')
# Removes committed file, removes from config

# Edit a template
memory.update_template('self-positions.yaml', new_content)
# Updates template file, its own commit

# Entity operations (don't touch config)
memory.create_entity('starling', type='person')
# Copies entity.yaml template → committed/entities/starling.md

memory.delete_entity('starling')
# Removes entity file + manifest entry
```

### Validation

- `add_category` to self or collaborator checks against `max_categories`
- `write_draft` validates target exists (in config for self/collaborator, in filesystem for entities)
- Category names must be valid filenames (lowercase, hyphens, no spaces)

---

## 7. Onboarding (Future Feature)

When the system detects a blank memory repo (no `_config.yaml`, no committed files), it triggers an onboarding flow.

### Detection

```python
memory = connect()
# If connect() finds no _config.yaml → onboarding mode
```

### Flow

1. **Identify use case** — conversational interview with the user
2. **Propose categories** — suggest a category set based on use case
3. **User confirms/adjusts** — they can add, remove, rename before creation
4. **Scaffold** — create config, templates, empty committed files, working branch
5. **First conversation** — system is ready, templates guide first drafts

### Use Case Presets

```yaml
presets:
  intellectual-companion:
    description: "Track intellectual development, positions, and relationship context"
    self: [positions, methods, interests, open-questions]
    collaborator: [profile]

  coding-project:
    description: "Track architecture decisions, coding standards, and project context"
    self: [architecture, coding-standards, methods, current-task]
    collaborator: [profile]

  starling-companion:
    description: "Track companion persona, relationship dynamics, and life context"
    self: [persona]
    collaborator: [profile, dynamics, protocols]

  custom:
    description: "Start blank and define your own categories"
    self: []
    collaborator: [profile]
```

---

## 8. Repository Structure

```
memory-repo/
│
├── _config.yaml                  # Mutable: space definitions, category lists
│
├── _templates/                   # Reference templates (not pre-injected)
│   ├── self-positions.yaml
│   ├── self-methods.yaml
│   ├── self-interests.yaml
│   ├── self-open-questions.yaml
│   ├── collaborator-profile.yaml
│   └── entity.yaml
│
├── committed/                    # Main branch — crystallised memories
│   ├── self/                     # ☑️ Pre-injected
│   │   ├── positions.md
│   │   ├── methods.md
│   │   ├── interests.md
│   │   └── open-questions.md
│   ├── collaborator/             # ☑️ Pre-injected
│   │   └── profile.md
│   ├── _entities_manifest.yaml   # ☑️ Pre-injected — entity index/TOC
│   └── entities/                 # ☐ Not injected, API-accessed
│       ├── starling.md
│       ├── oriole.md
│       └── ...
│
└── working/                      # Working branch — in-progress
    └── drafts/
        ├── self/
        │   └── ...
        ├── collaborator/
        │   └── ...
        └── entities/
            └── ...
```

### GitHub Integration Setup

In the "Add content from GitHub" dialog:

- ☑️ `committed/self/` — always loaded, bounded
- ☑️ `committed/collaborator/` — always loaded, bounded
- ☑️ `committed/_entities_manifest.yaml` — always loaded, entity index
- ☐ `committed/entities/` — accessed via API when needed
- ☐ `_templates/` — accessed via API by the code
- ☐ `_config.yaml` — read programmatically at connection time

---

## 9. Retrieval Strategy

### Pre-injected (Self + Collaborator)

Loaded as `<document>` tags every message. Zero latency, zero tool calls. Bounded by `max_categories` (default 7 per space, 14 total max). This is the "immediate awareness" layer.

### Entity Manifest (Pre-injected Table of Contents)

The entity manifest is a small YAML file, pre-injected alongside self and collaborator files. It gives the model a complete index of every entity without loading any entity content.

```yaml
# committed/_entities_manifest.yaml

starling:
  path: entities/starling.md
  type: person
  tags: [companion-guide, methodology, inspiration, reddit, AI-companionship,
         House-of-Alder, documentation-approach]
  summary: "Creator of Claude Companion Guide. Original motivation for memory system."

oriole:
  path: entities/oriole.md
  type: animal
  tags: [cat, family, sister-in-law, tortoiseshell, pet-longing]
  summary: "Max's sister-in-law's cat. Mutual obsession."

eve:
  path: entities/eve.md
  type: project
  tags: [memory-system, first-attempt, predecessor, companion, prototype]
  summary: "The first memory/companion system, before continuity-memory."

project_starships:
  path: entities/project_starships.md
  type: project
  tags: [space-game, LLM-combat, sci-fi-sim, turn-based,
         Starships-Unlimited-clone, python-game]
  summary: "Turn-based space strategy game using LLM for combat narration."
```

**Tags are anticipatory, not extractive.** When creating an entity, the model thinks: "what might someone say in a future conversation that should lead back to this file?" Tags include synonyms, casual names, related concepts, and implementation details that might come up in conversation — not just keywords from the content itself. This front-loads search optimization to write time, when full context is available.

**The manifest is updated at write time:**
- `create_entity()` → adds entry to manifest
- `delete_entity()` → removes entry from manifest
- `consolidate()` (scoped to an entity) → updates summary/tags if understanding evolved

**Cost:** One small YAML file in context. Negligible compared to the entity files themselves.

### On-demand Entity Retrieval

With the manifest in context, the model has three retrieval paths:

1. **Manifest lookup + direct fetch** (most common) — model reads the manifest, identifies the relevant entity by name or tags, fetches the file directly.
   ```python
   content = memory.get_entity('starling')
   ```
   This covers the vast majority of cases. The model sees "companion guide" in conversation, scans the manifest, finds Starling's tags include `companion-guide`, fetches the file. Zero search infrastructure needed.

2. **BM25 keyword search** (rare — when manifest tags don't cover the query) — pre-built index over entity file contents, stored in the repo, updated at write time.
   ```python
   results = memory.search_entities("the conversation about naming conventions")
   ```
   The BM25 index is built/updated when entities are created or consolidated. No runtime indexing cost. Pure Python implementation, no pip install required.

3. **Anthropic RAG** (fallback) — `project_knowledge_search` if entity count grows very large and entity files are added to the project. Automatic, no custom code.

### Why Not Vector Search?

Vector search solves the problem of a *dumb* searcher who can't bridge the gap between fuzzy intent and precise matches. But the searcher here is an LLM — it can:

- Read a manifest and reason about which entities are relevant
- Generate precise keyword queries for BM25
- Infer connections ("that cat" → Oriole) from context

The cost of vector search — installing an embedding model on every conversation start, indexing latency, dependency complexity — isn't justified when the searcher is smart enough to work with simpler tools. And crucially, the tags in the manifest do the heavy semantic lifting at write time rather than read time.

Vector search remains a future option if entity count reaches hundreds and keyword-based approaches genuinely struggle. But that's a scaling problem to solve when it arrives, not infrastructure to build speculatively.

### Retrieval During Conversation

The model decides when to fetch entities based on conversational context:

- User mentions "Starling" → manifest lookup, direct fetch
- User says "that cat we both love" → manifest scan, Oriole's tags match, direct fetch
- User references "the space game" → manifest scan, `project_starships` tags include `space-game`, direct fetch
- Topic touches something that *might* have an entity → scan manifest first, BM25 if uncertain
- User asks "what entities do we have about family?" → scan manifest tags for `family`

---

## 10. API Surface

### Connection

```python
from memory_system import connect
memory = connect()  # Reads _config.yaml, ensures branches, detects blank repo
```

### Status

```python
info = memory.status()
# {repo, categories: {self: [...], collaborator: [...]}, drafts: [...], entities: [...]}
```

### Self & Collaborator (Bounded Spaces)

```python
# Write
memory.write_draft('self/positions', content)
memory.write_draft('collaborator/profile', content)

# Read committed
memory.get_committed('self/positions')
memory.get_committed('collaborator/profile')

# Read draft
memory.get_draft('self/positions')
```

### Entities (Unbounded Space)

```python
# CRUD
memory.create_entity('starling', type='person',
    tags=['companion-guide', 'methodology', 'inspiration'],
    summary='Creator of Claude Companion Guide.')
# Creates entity file from template, adds entry to manifest

memory.write_draft('entities/starling', content)
memory.get_entity('starling')              # Read committed entity
memory.get_draft('entities/starling')      # Read draft entity
memory.list_entities()                     # Returns manifest contents
memory.delete_entity('starling')           # Removes file + manifest entry

# Manifest operations
memory.get_manifest()                      # Full manifest (already in context, but available via API)
memory.update_manifest('starling',         # Update tags/summary after consolidation
    tags=['companion-guide', 'methodology', 'inspiration', 'reddit'],
    summary='Creator of Claude Companion Guide. Original motivation for memory system.')

# Search (BM25 over entity file contents — pre-built index)
memory.search_entities(query)              # Keyword search, returns ranked entity names
```

### Config Mutation

```python
# Categories
memory.add_category('self', 'architecture', template='self-architecture.yaml')
memory.rename_category('self', 'architecture', 'system-design')
memory.remove_category('self', 'architecture')

# Templates
memory.get_template('self-positions')
memory.update_template('self-positions', new_content)
```

### Consolidation

```python
# All drafts
memory.consolidate("Journal: what crystallized and why")

# Scoped — only specific space or entity
memory.consolidate("Journal: ...", scope='self')
memory.consolidate("Journal: ...", scope='entities/starling')
memory.consolidate("Journal: ...", scope='collaborator')
```

---

## 11. Drafting: Where Do Insights Go?

The three-space model makes draft routing explicit:

| I notice... | Draft target | Space |
|-------------|-------------|-------|
| I'm forming a view on something | `self/positions` | Self |
| I've discovered a thinking approach | `self/methods` | Self |
| Something fascinates me | `self/interests` | Self |
| Something's unresolved and worth sitting with | `self/open-questions` | Self |
| User revealed a preference / value / context | `collaborator/profile` | Collaborator |
| We discussed a person/thing worth tracking | `entities/[name]` | Entities |
| An existing entity's understanding evolved | `entities/[name]` | Entities |
| Something doesn't fit any category | Consider: new category? new entity? or just not worth capturing. | — |

### Entity Creation During Conversation

When something comes up that seems "worthy of long-term tracking":

1. Model creates the entity with anticipatory tags:
   ```python
   memory.create_entity('oriole', type='animal',
       tags=['cat', 'family', 'sister-in-law', 'tortoiseshell', 'pet-longing'],
       summary="Max's sister-in-law's cat. Mutual obsession.")
   ```
2. Model drafts initial content: `memory.write_draft('entities/oriole', ...)`
3. Model mentions it naturally: "I've started tracking Oriole as an entity — she clearly matters to both of us."
4. User can course-correct if the entity isn't worth tracking
5. Tags are revisited each time the entity is touched — as understanding deepens, better tags emerge

---

## 12. Template Evolution Workflow

1. Templates live in `_templates/` on main branch, as YAML files
2. Creating a new committed file copies the current template's markdown example as the initial content
3. Template changes are their own commit: "Evolve entity template: add 'Historical context' section"
4. Existing files created from an earlier template version are NOT auto-migrated
5. Optional migration: add new sections with `(nothing yet)` placeholder to existing files
6. The template's own git history shows structural evolution independent of content

---

## 13. Migration Path from v0.x

### Current State → Three-Space

```
committed/positions.md      → committed/self/positions.md
committed/methods.md        → committed/self/methods.md
committed/interests.md      → committed/self/interests.md
committed/open-questions.md → committed/self/open-questions.md
committed/collaborator.md   → committed/collaborator/profile.md
(new)                       → committed/entities/
(new)                       → committed/_entities_manifest.yaml
(new)                       → _templates/
(updated)                   → _config.yaml
```

### Migration Sequence

1. Create `_templates/` with YAML templates for all current categories
2. Restructure `committed/` into `self/`, `collaborator/`, `entities/` subdirectories
3. Create empty `_entities_manifest.yaml`
4. Migrate existing content into templated form (add sections, placeholders)
5. Update `_config.yaml` to three-space model
6. Update `memory_system.py` for new paths, entity operations, manifest management, config mutation
7. Update project instructions for new draft routing
8. Update GitHub integration: check `committed/self/`, `committed/collaborator/`, and `committed/_entities_manifest.yaml`

Recommended commit structure:

- Commit 1: "Add templates and three-space directory structure" (empty files, templates, new config)
- Commit 2: "Migrate existing content into templated form" (content moves into new structure)

---

## 14. Open Design Questions

1. **Onboarding UX.** Envisaged as a series of conversational interview questions. Design pending.

2. **BM25 index storage.** Where does the pre-built BM25 index live in the repo? Stored in repo, updated at write time, since the whole point is avoiding runtime cost.

3. **Cross-entity references.** Obsidian-style `[[wiki-links]]` throughout all files. Zero cost at write time, enables graph visualization if the repo is ever opened as an Obsidian vault.

---

## 15. Evolution

This section compresses the design history from v0.1 through v0.5. The full v0.5 spec is archived at `docs/archive/design-v0.5.md`.

### v0.1–v0.2 (Dec 25–26, 2025): Foundation

The system began as a Christmas Day conversation about giving Claude persistent memory using GitHub. Core decisions established early: two-branch architecture (main + working), journal-entry model for consolidation (crystallization-bounded commits), and the principle that files hold current state while git history holds evolution.

### v0.3 (Dec 27, 2025): Skills Integration

Added a Skills-based progressive disclosure system to reduce context load. Integrated BM25 search for retrieval. The design philosophy at this stage was heavily "agency and emergence" — Claude decides when to commit, memory operations emerge naturally. This was intellectually appealing but operationally ineffective.

### v0.4 (Dec 28, 2025): Directive Shift

Key breakthrough: studying Anthropic's native memory prompts revealed that **directive language** ("Claude NEVER...", "Claude selectively applies...") dramatically outperforms permissive language ("you may", "when appropriate"). The system shifted from philosophical framing to behavioral responsibility.

Also removed custom search entirely — Anthropic's pre-injection for small projects and `project_knowledge_search` for large projects handles retrieval. The system now focuses solely on writes.

Introduced configurable category taxonomy (`_memory_config.yaml`, max 7 categories) replacing unbounded file proliferation, and the hybrid retrieval model: crystallized memories pre-injected, working memory tool-based.

### v0.5 (Dec 30, 2025): Prompt Placement Taxonomy

Discovered that **project instructions load every message** (100% reliable) while **skills only trigger on user prompt match** (probabilistic). This led to a tiered behavior model:

- Tier 1 (unconditional): Inline code in project instructions
- Tier 2 (conditional): Inline code + explicit triggers
- Tier 3 (agent-initiated): Dispatch to reference docs
- Tier 4 (user-invoked): Skills layer

Also began experimental work on chain-of-thought shaping — attempting to influence the quality of the model's internal reasoning to improve insight recognition.

### v1.0 (Feb 2026): Three-Space Architecture

Architectural redesign driven by several converging insights:

- **Three ownership spaces** (self, collaborator, entities) replace a flat category list. Different spaces have different physics: bounded vs unbounded, pre-injected vs on-demand.
- **The model is the user.** Everything in the system is the model's perspective. No false dual-perspective distinction. The personal trainer archetype: working memory in service of doing better work.
- **YAML templates** with per-category structure enable clean diffs by keeping file skeletons stable while content evolves independently within sections.
- **Self-modifying config** allows categories to be added, renamed, or removed at runtime, with templates evolving alongside.
- **Entity manifest** replaces vector search — a pre-injected YAML index with anticipatory tags, updated at write time. The model is smart enough to work with a table of contents rather than needing semantic search infrastructure.
- **Use-case parameterization** makes the system genuinely reusable. The same three-space infrastructure serves intellectual companions, coding assistants, Starling-style companions, and any other use case through different category configurations.
- **Obsidian-style `[[wiki-links]]`** for cross-entity references at zero cost, with future graph visualization potential.

---

*This document is version controlled at `docs/continuity-memory-system-design.md` in the [project repository](https://github.com/chknd1nner/claude-continuity-memory).*
