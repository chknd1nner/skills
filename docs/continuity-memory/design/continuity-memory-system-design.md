# Claude Continuity Memory System Design
## Using GitHub as a Persistent Storage Layer

*v2.0 — February 2026*

| Version | Date | Summary |
|---------|------|---------|
| v0.1–0.2 | Dec 25–26, 2025 | Foundation: two-branch architecture, journal-entry model, GitHub API. |
| v0.3 | Dec 27, 2025 | Skills integration, BM25 search, progressive disclosure. |
| v0.4 | Dec 28, 2025 | Directive shift: behavioral responsibility over permissive framing. Configurable categories (max 7). |
| v0.5 | Dec 30, 2025 | Prompt placement taxonomy: project instructions (reliable) vs skills (probabilistic). |
| v1.0 | Feb 15, 2026 | Three-space architecture (self, collaborator, entities). YAML templates, self-modifying config, entity manifest with anticipatory tags. Separate `working/drafts/` folder structure. |
| v1.1 | Feb 16, 2026 | Added problem space & positioning — failure modes, Anthropic solutions, gap identification. |
| **v2.0** | **Feb 17, 2026** | **Squash-merge workflow replaces folder-based drafts. Single file structure across branches. Local file editing pattern for token efficiency. File-level scoped consolidation. Git log at session start for narrative context. Flexible fetch modes.** |

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

**Memories.** Once per day, a background agent reads all user conversations and maintains a working memory document injected into future chats as system prompt context. Memories are bound to projects or unsorted chats outside of projects. The memory format follows rigid templates. These capture stable, high-level facts *about the user and project* — not the model's working understanding or ongoing analytical state.

### The Gap

These solutions cover two of three temporal layers:

| Layer | Time horizon | Anthropic's solution | Gap |
|-------|-------------|---------------------|-----|
| **Within-session** | Current chat | Context window management | Lossy at capacity |
| **Cross-session, short-term** | Recent chats | `search_past_conversations` | User-initiated only, summarised at retrieval time |
| **Cross-session, long-term** | All time | Memories | Facts about the user, not the model's working understanding |

The uncovered middle ground: **the model's evolving understanding across an ongoing multi-session effort.** If a model spends three sessions refactoring a codebase, Memories might note "working on a memory system project." `search_past_conversations` can find what was said if the user asks. But neither carries forward the model's *working state* — the specific insights, emerging patterns, provisional conclusions, and contextual understanding that accumulated over those sessions.

### How This System Fills the Gap

**Working branch edits** are this system's answer to the within-session and cross-session short-term problem. Unlike compaction, which writes the summary at the worst possible moment — maximum context pressure, minimum remaining capacity — the model captures insights **incrementally, while it has full context and can judge what matters.** A 150K-token conversation doesn't lose its insights to aggressive end-of-session compression. Insights are preserved as they arise as small commits on the working branch.

Between sessions, the working branch stays ahead of main, providing continuity without requiring the user to invoke a search tool or re-establish context manually. When the user begins a new chat, the model checks for changes on the working branch and picks up the thread.

**Consolidation** addresses the cross-session long-term layer. Committed files on main are the model's crystallised understanding — not facts extracted *from* the user by a background agent, but knowledge written *by* the model about its own perspective. This is the trainer's notebook, not the client's intake form. The customisable category system (vs. Anthropic's rigid headings) means the structure adapts to the use case rather than forcing all knowledge into predetermined slots.

### Complementarity, Not Competition

This system doesn't replace Anthropic's first-party solutions. It's complementary:

| Need | Best tool |
|------|----------|
| Stable facts about the user | **Anthropic Memories** |
| Literal recall of past dialogue | **`search_past_conversations`** |
| Model's working understanding & insights | **This system (working → main)** |

The boundary is deliberate: this system captures what the model *learned*, not what was *said*. It indexes insight, not transcript. The raw conversational record remains Anthropic's domain.

### The Transcript Constraint

On claude.ai, the running conversation transcript is not accessible to the model as a file system resource. The `/mnt/transcripts` path in the sandbox only materialises when the compaction agent activates near context capacity — it's an implementation detail of the platform, not a resource available during normal operation.

This constraint shapes the design. Since the model can't archive raw transcripts to the memory repo for future indexing, the system instead captures the *distillation* in real time — insights written while the model has full context, rather than transcripts archived wholesale. This is arguably superior for most continuity needs: the raw transcript is 95% noise for cross-session purposes (tool calls, debugging output, pleasantries, backtracking). What matters for continuity is the signal, and incremental commits capture that at the moment of highest fidelity.

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
# Creates template file, creates empty file from template,
# updates _config.yaml, single commit

# Rename a category
memory.rename_category('self', 'architecture', 'system-design')
# Renames file, updates config, updates template reference

# Remove a category
memory.remove_category('self', 'architecture')
# Removes file, removes from config

# Edit a template
memory.update_template('self-positions.yaml', new_content)
# Updates template file, its own commit

# Entity operations (don't touch config)
memory.create_entity('starling', type='person')
# Copies entity.yaml template → entities/starling.md

memory.delete_entity('starling')
# Removes entity file + manifest entry
```

### Validation

- `add_category` to self or collaborator checks against `max_categories`
- `write()` validates target exists (in config for self/collaborator, in filesystem for entities)
- Category names must be valid filenames (lowercase, hyphens, no spaces)

---

## 7. Two-Branch Workflow: Squash-Merge Model

**This is the central architectural change from v1.0.** The v1.0 design used a separate `working/drafts/` folder structure — an implementation workaround because the GitHub Contents API doesn't support native squash merge. v2.0 eliminates the separate folder by using the Git Data API for true squash merge.

### The Model

```
working:  a → b → c → d → e → f      (many small commits)
                                  ↓ squash
main:     X ──────────────────→ Y      (one crystallised commit)
```

- **Main branch** = the model's crystallised record. Clean history. Each commit is a journal entry summarising what understanding evolved and why.
- **Working branch** = the model's scratchpad. Many small commits directly to the real files. Each commit captures an incremental shift in understanding.
- **One set of files.** Both branches share the same file structure. Working is just ahead of main.
- **Consolidation** = squash merge specific files from working to main. One commit with a journal-entry message. Working naturally converges with main as files are consolidated.

### Why Not Separate Draft Files? (v1.0 → v2.0 Change)

The v1.0 design had `committed/self/positions.md` on main and `working/drafts/self/positions.md` on working. This emerged from two practical constraints:

1. **GitHub Contents API doesn't support squash merge.** The folder separation made it easier to simulate consolidation — read from drafts folder, write to committed folder.
2. **Drafting was cheaper as a simple file write.** Creating a new file in `working/drafts/` avoided the read-modify-write cycle of editing an existing file.

Both constraints are resolved in v2.0:

1. **Git Data API supports constructing arbitrary commits.** True squash merge is ~10 lines of Python using tree/commit/ref operations.
2. **Local file editing eliminates the read-modify-write overhead.** The model edits files locally using native tools; the commit operation reads from the local file.

### Repository Structure

```
memory-repo/
│
├── _config.yaml                  # Mutable: space definitions, category lists
│
├── _templates/                   # Reference templates (not pre-injected)
│   ├── self-positions.yaml
│   ├── self-methods.yaml
│   ├── collaborator-profile.yaml
│   └── entity.yaml
│
├── _entities_manifest.yaml       # ☑️ Pre-injected — entity index/TOC
│
├── self/                         # ☑️ Pre-injected
│   ├── positions.md
│   ├── methods.md
│   ├── interests.md
│   └── open-questions.md
│
├── collaborator/                 # ☑️ Pre-injected
│   └── profile.md
│
└── entities/                     # ☐ Not injected, API-accessed
    ├── starling.md
    ├── oriole.md
    └── ...
```

Both branches have this identical structure. Working diverges through edits; consolidation brings them back together.

### GitHub Integration Setup

In the "Add content from GitHub" dialog:

- ☑️ `self/` — always loaded, bounded
- ☑️ `collaborator/` — always loaded, bounded
- ☑️ `_entities_manifest.yaml` — always loaded, entity index
- ☐ `entities/` — accessed via API when needed
- ☐ `_templates/` — accessed via API by the code
- ☐ `_config.yaml` — read programmatically at connection time

### File-Level Scoped Consolidation

Consolidation is **file-level**, not branch-level. The model chooses which files to crystallise:

```python
# Consolidate specific files
memory.consolidate(
    files=['self/positions', 'entities/starling'],
    message="Journal: landed on emergent structure position after three "
            "conversations. Starling entity updated with methodology details."
)
```

After consolidation, the consolidated files are identical on both branches (zero diff). Unconsolidated files remain ahead on working. The model doesn't need to resolve everything at once.

The squash commit message is a **journal entry** — it tells the story of the session, including what resolved and what's still open:

> *"We made a breakthrough about Max's habits around teeth clenching, offered concrete exercises to strengthen his TMJ. Made progress on, but wasn't able to finish the discussion about his wife's latest dream."*

### Squash Merge Implementation

Using the Git Data API (PyGithub):

```python
def consolidate(self, files, message):
    """Squash-merge specific files from working to main."""
    # Get current main state
    main_ref = self.repo.get_git_ref('heads/main')
    main_commit = self.repo.get_git_commit(main_ref.object.sha)
    main_tree = main_commit.tree

    # Build new tree: main's tree with specified files replaced
    # by their working branch versions
    tree_elements = []
    for file_path in files:
        working_content = self.git.get(file_path, branch='working')
        tree_elements.append(InputGitTreeElement(
            path=file_path,
            mode='100644',
            type='blob',
            content=working_content
        ))

    new_tree = self.repo.create_git_tree(tree_elements, base_tree=main_tree)

    # Create squash commit on main
    squash_commit = self.repo.create_git_commit(
        message=message,
        tree=new_tree,
        parents=[main_commit]
    )

    # Advance main
    main_ref.edit(squash_commit.sha)
```

Working branch is NOT reset — it naturally converges with main as files are consolidated. The commit history on working is the "trail of thinking" and can grow indefinitely without affecting main's clean journal.

---

## 8. Local File Editing Pattern

**The token efficiency optimisation.** In v1.0, every write operation required the model to output the entire file content as a parameter to a Python method — expensive in tokens and redundant when only a section changed.

v2.0 separates **transport** (Python script, GitHub API) from **editing** (Claude.ai native tools, local filesystem).

### The Workflow

```
┌──────────────────────────────────────────────────────────┐
│ 1. FETCH (Python → GitHub API → local file)              │
│                                                          │
│    memory.fetch('self/positions', return='both')         │
│    → Returns content string to context (for reasoning)   │
│    → Saves to /mnt/home/self/positions.md (for editing)  │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│ 2. EDIT (Claude.ai native tool, local filesystem)        │
│                                                          │
│    edit_file('/mnt/home/self/positions.md',               │
│      find='## Emergent structure',                       │
│      replace='## Emergent structure\n...(updated)...')   │
│                                                          │
│    Tokens used: just the surgical change                 │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│ 3. COMMIT (Python → local file → GitHub API)             │
│                                                          │
│    memory.commit('self/positions',                       │
│      from_file='/mnt/home/self/positions.md',            │
│      message='forming view on emergent design')          │
│                                                          │
│    → Reads file content from disk                        │
│    → Pushes to working branch via GitHub API             │
│    Tokens used: just the method call                     │
└──────────────────────────────────────────────────────────┘
```

### Fetch Modes

All read/fetch methods support three return modes:

| Mode | Context tokens | Local file | Use case |
|------|---------------|------------|----------|
| `return='content'` | ✅ | ❌ | Quick read, reasoning only |
| `return='file'` | ❌ | ✅ | Already in context via `<document>`, just need editable copy |
| `return='both'` | ✅ | ✅ | First read in a session, need to reason AND edit |

The `file` mode is especially valuable at session start for self/collaborator files — they're already in context via pre-injected `<document>` tags from main. The model just needs the working branch versions saved locally for editing. Zero redundant tokens.

### Local File Structure

```
/mnt/home/
├── self/
│   ├── positions.md
│   ├── methods.md
│   └── ...
├── collaborator/
│   └── profile.md
└── entities/
    ├── starling.md
    └── ...
```

Mirrors the repo structure. Files are ephemeral — `/mnt/home/` is wiped between sessions.

### Separation of Concerns

| Layer | Responsibility | Token cost |
|-------|---------------|------------|
| **Claude.ai native tools** | File editing (surgical, section-targeted) | Just the edit delta |
| **Python script** | GitHub API transport (fetch, push, squash merge) | Just the method call |
| **Templates** | Define section structure the model targets with edits | Zero at runtime |

---

## 9. Session Lifecycle

### Session Start

On first message, the model connects and orients:

```python
memory = connect()
status = memory.status()
```

`status()` returns:

1. **Connection info** — repo name, config summary
2. **Working branch state** — files that differ from main (the "hanging" work)
3. **Recent main log** — last N commit messages from main, providing narrative context for the pre-injected files ("when and why was this last crystallised?")

If working is ahead of main, the model fetches the changed files (using `return='file'` since the main versions are already in context via `<document>` tags) and reads the commit messages on working since divergence to reconstruct where its thinking was.

### Per-Response Cycle

Every response, the model works through these considerations:

**Before responding:**

1. **Entity retrieval** — does the current message reference entities? Scan the manifest (already in context), fetch relevant entity files if needed.

**After responding (or woven in):**

2. **Editing** — did anything emerge worth capturing? Surgically edit the relevant local file(s) targeting specific sections. Route to the appropriate space:

| I notice... | Edit target | Space |
|-------------|------------|-------|
| I'm forming a view on something | `self/positions` | Self |
| I've discovered a thinking approach | `self/methods` | Self |
| Something fascinates me | `self/interests` | Self |
| Something's unresolved and worth sitting with | `self/open-questions` | Self |
| User revealed a preference / value / context | `collaborator/profile` | Collaborator |
| We discussed a person/thing worth tracking | `entities/[name]` | Entities |
| An existing entity's understanding evolved | `entities/[name]` | Entities |

3. **Committing** — push the edited local file(s) to working branch with a small, descriptive commit message.

4. **Consolidation** — has a thread resolved? If so, squash-merge the relevant files to main with a journal-entry commit message.

5. **Entity management** — should a new entity be created? Should manifest tags/summary be updated for an existing entity?

6. **Config evolution** (rare) — does the category structure need to change? Do templates need updating?

### Threads

A "thread" is the model's organizing frame — something it can name or label coherently. It's not necessarily a conversational topic; it can span topics and even sessions. A therapist hearing about work stress, family dinners, and a fight with a friend might have one thread: "avoidant attachment pattern across contexts."

Threads are resolved when the model's understanding crystallises, not necessarily when the conversation moves on. Hanging threads are normal — they stay as uncommitted work on the working branch across sessions. The model picks them up when naturally relevant, or eventually crystallises them as-is.

---

## 10. Retrieval Strategy

### Pre-injected (Self + Collaborator)

Loaded as `<document>` tags every message from main branch. Zero latency, zero tool calls. Bounded by `max_categories` (default 7 per space, 14 total max). This is the "immediate awareness" layer.

### Entity Manifest (Pre-injected Table of Contents)

The entity manifest is a small YAML file, pre-injected alongside self and collaborator files. It gives the model a complete index of every entity without loading any entity content.

```yaml
# _entities_manifest.yaml

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
```

**Tags are anticipatory, not extractive.** When creating an entity, the model thinks: "what might someone say in a future conversation that should lead back to this file?" Tags include synonyms, casual names, related concepts — not just keywords from the content. This front-loads search optimization to write time, when full context is available.

### On-demand Entity Retrieval

Three retrieval paths, in order of preference:

1. **Manifest lookup + direct fetch** (most common) — model reads the manifest, identifies the relevant entity by name or tags, fetches the file. This covers the vast majority of cases.
   ```python
   content = memory.fetch('entities/starling', return='both')
   ```

2. **BM25 keyword search** (rare — when manifest tags don't cover the query) — pre-built index over entity file contents, updated at write time.
   ```python
   results = memory.search_entities("the conversation about naming conventions")
   ```

3. **Anthropic RAG** (fallback) — `project_knowledge_search` if entity count grows very large and entity files are added to the project.

### Why Not Vector Search?

Vector search solves the problem of a *dumb* searcher. But the searcher here is an LLM — it can read a manifest, reason about relevance, generate precise keyword queries, and infer connections from context. The cost of vector search (embedding model, indexing latency, dependencies) isn't justified when the searcher is smart enough to work with a table of contents and BM25.

---

## 11. API Surface

### Connection

```python
from memory_system import connect
memory = connect()  # Reads _config.yaml, ensures branches
```

### Status

```python
info = memory.status()
# Returns:
# - repo: str
# - config: dict (spaces, categories)
# - dirty_files: list[str]  (files where working differs from main)
# - recent_log: list[dict]  (last N commits on main with messages)
```

### Fetch (Read)

```python
# From working branch (current state including in-progress edits)
memory.fetch('self/positions', return='content')  # → string
memory.fetch('self/positions', return='file')     # → saves to /mnt/home/self/positions.md
memory.fetch('self/positions', return='both')     # → string + local file

# Entities
memory.fetch('entities/starling', return='both')

# From main branch (last checkpoint — rarely needed, usually in <document> tags)
memory.fetch('self/positions', branch='main', return='content')
```

### Commit (Write)

```python
# From local file (token-efficient — the normal path)
memory.commit('self/positions',
    from_file='/mnt/home/self/positions.md',
    message='forming view on emergent design')

# From content string (when local file editing isn't needed)
memory.commit('self/positions',
    content='# Positions\n...',
    message='forming view on emergent design')
```

### Consolidation (Squash Merge)

```python
# Squash-merge specific files from working to main
memory.consolidate(
    files=['self/positions', 'entities/starling'],
    message="Journal: landed on emergent structure. Updated Starling entity."
)

# Consolidate all dirty files
memory.consolidate(
    files='all',
    message="Journal: end of session crystallisation."
)
```

### Entity Management

```python
# Create (copies template, adds to manifest)
memory.create_entity('starling', type='person',
    tags=['companion-guide', 'methodology', 'inspiration'],
    summary='Creator of Claude Companion Guide.')

# Search (BM25 over entity file contents)
memory.search_entities(query)

# Manifest operations
memory.get_manifest()
memory.update_manifest('starling',
    tags=['companion-guide', 'methodology', 'inspiration', 'reddit'],
    summary='Creator of Claude Companion Guide. Original motivation for memory system.')

# Delete
memory.delete_entity('starling')
```

### Config Mutation

```python
memory.add_category('self', 'architecture', template='self-architecture.yaml')
memory.rename_category('self', 'architecture', 'system-design')
memory.remove_category('self', 'architecture')
memory.get_template('self-positions')
memory.update_template('self-positions', new_content)
```

---

## 12. Onboarding (Future Feature)

When the system detects a blank memory repo (no `_config.yaml`), it triggers an onboarding flow.

### Detection

```python
memory = connect()
# If connect() finds no _config.yaml → onboarding mode
```

### Flow

1. **Identify use case** — conversational interview with the user
2. **Propose categories** — suggest a category set based on use case
3. **User confirms/adjusts** — they can add, remove, rename before creation
4. **Scaffold** — create config, templates, empty files, working branch
5. **First conversation** — system is ready, templates guide first edits

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

## 13. Migration Path from v1.x

### Structure Changes

```
# v1.x structure (both branches)
committed/self/positions.md       → self/positions.md
committed/collaborator/profile.md → collaborator/profile.md
committed/entities/starling.md    → entities/starling.md
committed/_entities_manifest.yaml → _entities_manifest.yaml

# Removed entirely
working/drafts/                   → (eliminated)
```

### Implementation Changes

| Component | v1.x | v2.0 |
|-----------|------|------|
| Draft storage | Separate `working/drafts/` files | Same files on working branch |
| Write operation | `write_draft(path, content)` — full content as parameter | `commit(path, from_file=...)` — reads from local file |
| Consolidation | Read draft, merge into committed file, write to main | Squash merge: copy file state from working to main |
| Hanging draft detection | List files in `working/drafts/` | Diff working vs main |
| File editing | Model outputs entire file as tokens | Model edits locally with native tools |

### Migration Sequence

1. Flatten `committed/` — move `committed/self/` → `self/`, `committed/collaborator/` → `collaborator/`, etc.
2. Remove `working/drafts/` directory entirely
3. Update `memory_system.py`: new `fetch()`, `commit()`, `consolidate()` methods
4. Update GitHub integration to point at new paths (`self/`, `collaborator/`, `_entities_manifest.yaml`)
5. Update project instructions for new workflow

---

## 14. Open Design Questions

1. **Onboarding UX.** Envisaged as a series of conversational interview questions. Design pending.

2. **BM25 index storage.** Where does the pre-built BM25 index live in the repo? Stored in repo, updated at write time, since the whole point is avoiding runtime cost.

3. **Cross-entity references.** Obsidian-style `[[wiki-links]]` throughout all files. Zero cost at write time, enables graph visualization if the repo is ever opened as an Obsidian vault.

4. **Working branch commit accumulation.** The working branch accumulates small commits indefinitely. Is periodic cleanup needed, or is this fine? The commits serve as a thinking trail; they don't affect main's clean history.

5. **Stale hanging work.** If working has been ahead of main for many sessions without relevance, should there be housekeeping guidance? e.g., "if a file has been dirty for N sessions without being touched, consider crystallising or reverting."

---

## 15. Evolution

This section compresses the full design history. Archived versions: `docs/archive/design-v0.5.md`, `docs/archive/design-v1.0.md`.

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

### v1.0 (Feb 15, 2026): Three-Space Architecture

Architectural redesign driven by several converging insights:

- **Three ownership spaces** (self, collaborator, entities) replace a flat category list. Different spaces have different physics: bounded vs unbounded, pre-injected vs on-demand.
- **The model is the user.** Everything in the system is the model's perspective.
- **YAML templates** with per-category structure enable clean diffs.
- **Self-modifying config** allows categories to evolve at runtime.
- **Entity manifest** replaces vector search — anticipatory tags, updated at write time.
- **Use-case parameterization** makes the system genuinely reusable.
- **Separate `working/drafts/` folder** for draft storage (later identified as an implementation workaround).

### v2.0 (Feb 17, 2026): Squash-Merge Workflow

Driven by re-examining the original Dec 26 design intent and realising the folder-based draft system was a workaround, not a design choice:

- **Eliminated `working/drafts/` folder.** Single file structure across both branches. Working branch is just ahead of main.
- **True squash merge** via Git Data API. Many small commits on working → one journal-entry commit on main.
- **File-level scoped consolidation.** Consolidate specific files without forcing resolution of everything. Working and main naturally converge.
- **Local file editing pattern.** Fetch saves to `/mnt/home/`, model edits with native tools, commit reads from local file. Dramatic token savings — the model never re-outputs full file content.
- **Flexible fetch modes.** Content string, local file, or both. Eliminates redundant context when files are already pre-injected.
- **Git log at session start.** Commit messages from main provide temporal and narrative context for pre-injected files.
- **Consolidation is no longer destructive.** With templated sections and surgical edits, only changed sections are modified. The squash merge captures genuine deltas, not wholesale replacement.

---

*This document is version controlled at `docs/continuity-memory-system-design.md` in the [project repository](https://github.com/chknd1nner/claude-continuity-memory).*
