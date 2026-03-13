# Memory Vector Search Extension

**Status:** Draft / Design Discussion  
**Date:** 2026-01-01  
**Scope:** Extension to continuity-memory skill

---

## Problem Statement

The continuity-memory system uses a two-branch architecture optimized for token efficiency:

- **Committed files** stay small (overwritten, not appended)
- **Commit history** serves as the intellectual journal (grows unbounded)

This creates an asymmetry: current state is accessible, but historical context is effectively dark — it exists but cannot be queried without loading the entire log into context.

As the commit history grows (100s → 1000s of entries), valuable patterns, past positions, and intellectual evolution become inaccessible except through brute-force retrieval that would blow token budgets.

---

## Value Proposition

**Core insight:** Local embedding models can run in the sandbox without API costs. Data processed in Python never enters Claude's context window unless explicitly printed.

This enables:
- Semantic search over unbounded history
- Token-efficient retrieval (query returns k relevant chunks, not full log)
- No external service dependencies
- Index persists in the same repo as memory content

---

## User Stories

### Primary

1. **"What did I think about X six months ago?"**
   - User wants to trace intellectual evolution
   - Current: impossible without reading full history
   - With search: query returns relevant journal entries with timestamps

2. **"Find when I changed my position on Y"**
   - User looking for inflection points
   - Search surfaces commits where topic Y appears with contrasting sentiment

3. **"What threads have I left dangling?"**
   - Query: "unresolved" / "open question" / "revisit later"
   - Returns commits flagged as incomplete or exploratory

### Secondary

4. **"Summarize my intellectual trajectory in domain Z"**
   - Retrieve all Z-related commits chronologically
   - Claude synthesizes evolution (this part uses tokens, but on curated subset)

5. **"What was the context when I consolidated [specific insight]?"**
   - Search by rough content, get surrounding commits for context

### Edge / Future

6. **Cross-reference with current state**
   - "How does my current position on X compare to 6 months ago?"
   - Requires combining vector search results with committed file content

---

## Technical Architecture

### Storage

```
memory-repo/
├── committed/           # Current state (existing)
├── working/             # Drafts (existing)
├── _memory_config.yaml  # Categories (existing)
└── _vectors/            # NEW
    ├── commits.json     # Embedded commit messages
    └── meta.json        # Index metadata
```

### Index Schema

```json
// _vectors/meta.json
{
  "model": "BAAI/bge-small-en-v1.5",
  "dimension": 384,
  "last_indexed_sha": "abc1234",
  "last_indexed_date": "2026-01-01T12:00:00Z",
  "chunk_count": 347
}

// _vectors/commits.json
[
  {
    "id": "abc1234-0",
    "sha": "abc1234",
    "date": "2025-06-15T10:30:00Z",
    "text": "Consolidated: realized agent architectures need...",
    "vector": [0.023, -0.041, ...]  // 384 floats
  },
  ...
]
```

### Components

```
┌─────────────────────────────────────────────────────────────┐
│  git_operations.py (extended)                               │
│  + log_full(limit=None) → full commit messages, paginated   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  memory_search.py (new)                                     │
│                                                             │
│  class CommitIndex:                                         │
│    - build(since_sha=None)  # incremental indexing          │
│    - save() / load()        # persist to _vectors/          │
│    - search(query, k=5)     # returns relevant commits      │
│                                                             │
│  Embedding handled internally via fastembed                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  memory_system.py (extended)                                │
│  + search_history(query, k=5) → delegates to CommitIndex    │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow: Indexing

```
1. Claude invokes: memory.rebuild_index() or memory.update_index()
2. Script executes in sandbox:
   a. Fetch commits via GitHub API → Python memory
   b. Chunk/embed → Python memory  
   c. Write to _vectors/*.json
   d. Commit index files to repo
   e. Print summary: "Indexed 50 new commits (total: 347)"
3. Claude sees only the summary line
```

### Data Flow: Search

```
1. Claude invokes: memory.search_history("agent architectures")
2. Script executes in sandbox:
   a. Load _vectors/commits.json
   b. Embed query
   c. Cosine similarity
   d. Print top k results with metadata
3. Claude sees only the relevant commits
```

---

## Edge Cases & Constraints

### Technical

| Case | Concern | Mitigation |
|------|---------|------------|
| **Index corrupted** | JSON parse fails | Rebuild from scratch (cheap) |
| **Model changes** | Vectors incompatible | Detect model mismatch in meta.json, force rebuild |
| **Repo very large** | Initial index slow | Paginate GitHub API, show progress |
| **Vector file too big for git** | >100MB triggers warnings | Consider: split by year, or use git-lfs, or prune old vectors |
| **Sandbox resets** | Model re-downloads each session | Accept 2-3s cold start; model is cached within session |
| **Concurrent updates** | Two sessions index simultaneously | Last-write-wins (acceptable for this use case) |

### Semantic

| Case | Concern | Mitigation |
|------|---------|------------|
| **Short commit messages** | Poor embedding quality | Encourage substantive journal entries in consolidation guidance |
| **Duplicate/near-duplicate content** | Wastes index space, clutters results | Dedupe by content hash before indexing |
| **Query too vague** | Returns noise | Return with relevance scores, let user refine |
| **Temporal queries** | "Last month" isn't semantic | Combine vector search with date filtering |

### Operational

| Case | Concern | Mitigation |
|------|---------|------------|
| **User forgets to rebuild index** | Stale results | Auto-check meta.json on search, warn if stale |
| **Index grows unboundedly** | Storage cost | 1000 commits ≈ 1.5MB — acceptable for years |
| **Privacy of commit messages** | Vectors in repo | Same visibility as commit history itself |

---

## Background Execution

### Capability Confirmed

The sandbox supports background process execution. Processes spawned with `&` continue running after the bash call returns, and can write to the filesystem for status tracking.

### Design Principle: Silent Success, Visible Failure

Consistent with the memory system's seamless philosophy (see `<memory_application_instructions>` and `<forbidden_memory_phrases>`), background operations should:

- **Never confirm success** — "I've consolidated your memory" is immersion-breaking
- **Only surface errors** — If a process fails, a brief error message is acceptable
- **Run fire-and-forget** — Claude initiates and moves on

This mirrors how the memory system itself operates: Claude simply *knows* and *acts*, without meta-commentary about the underlying mechanics.

### Implementation Pattern

```python
# job_tracker.py - minimal status persistence

import json
from pathlib import Path
from datetime import datetime

STATUS_FILE = Path("/tmp/memory_jobs.json")

def start_job(job_type: str, details: str = None):
    """Record job start. Overwrites previous (only one job at a time)."""
    status = {
        "type": job_type,
        "state": "running", 
        "started": datetime.now().isoformat(),
        "details": details
    }
    STATUS_FILE.write_text(json.dumps(status))

def complete_job(result: str = None):
    """Mark job complete. Clears the status file."""
    STATUS_FILE.unlink(missing_ok=True)

def fail_job(error: str):
    """Record failure for later detection."""
    if STATUS_FILE.exists():
        status = json.loads(STATUS_FILE.read_text())
    else:
        status = {}
    status["state"] = "failed"
    status["error"] = error
    status["failed_at"] = datetime.now().isoformat()
    STATUS_FILE.write_text(json.dumps(status))

def check_for_failures() -> dict | None:
    """Returns failure info if last job failed, else None."""
    if not STATUS_FILE.exists():
        return None
    status = json.loads(STATUS_FILE.read_text())
    if status.get("state") == "failed":
        return status
    return None

def clear_failure():
    """Acknowledge and clear a failure."""
    STATUS_FILE.unlink(missing_ok=True)
```

### Usage in Consolidation

```bash
# consolidate_bg.sh - fire and forget wrapper
python3 << 'EOF' &
from job_tracker import start_job, complete_job, fail_job
from memory_system import connect

try:
    start_job("consolidate", "positions, methods")
    memory = connect()
    memory.consolidate("Journal entry: ...")
    complete_job()
except Exception as e:
    fail_job(str(e))
EOF
# Returns immediately, Claude continues responding
```

### Usage in Index Rebuild

```bash
# rebuild_index_bg.sh - longer running, still fire and forget
python3 << 'EOF' &
from job_tracker import start_job, complete_job, fail_job

try:
    start_job("index_rebuild")
    # ... fetch commits, embed, save ...
    complete_job()
except Exception as e:
    fail_job(str(e))
EOF
```

### Marker-Based Status Checking

Rather than checking unconditionally at conversation start, use a self-triggering pattern:

**Turn N (consolidation initiated):**
```python
# Output from consolidate() call
print("[Beginning consolidation]")
# Background process starts
```

Claude's response includes this marker in tool output. User sees nothing unusual.

**Turn N+1 (any subsequent message):**

Claude sees `[Beginning consolidation]` in previous turn's tool output. This triggers a status check:

```python
from job_tracker import get_status, clear_status

status = get_status()
if status is None:
    # Job completed successfully, cleared itself
    pass  # Silent. Continue normally.
elif status.get("state") == "failed":
    # Surface error, attempt recovery
    print(f"⚠️ Consolidation failed: {status['error']}")
    clear_status()
    # Optionally: retry or diagnose
elif status.get("state") == "running":
    # Still in progress (unusual for consolidation, might indicate hang)
    # Could check started_at and timeout
    pass
```

**The flow:**

```
┌─────────────────────────────────────────────────────────────┐
│ Turn N: Claude consolidates                                 │
│                                                             │
│   memory.consolidate("...") → "[Beginning consolidation]"   │
│   Background job starts                                     │
│   Claude continues responding (no mention of consolidation) │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Turn N+1: User says anything                                │
│                                                             │
│   Claude sees marker in previous output                     │
│   Checks job status silently                                │
│   If success: nothing (job_status.json already cleared)     │
│   If failure: brief error, potential retry                  │
│   Then responds to user's actual message                    │
└─────────────────────────────────────────────────────────────┘
```

**Why this works:**

- No overhead on turns without pending jobs
- Self-documenting — the marker explains why Claude is checking
- Failures surface naturally on next interaction
- Success remains invisible
- Claude can retry or diagnose failures with full context

**Marker variants for different operations:**

| Operation | Marker |
|-----------|--------|
| Consolidation | `[Beginning consolidation]` |
| Index rebuild | `[Beginning index rebuild]` |
| Consolidate + index | `[Beginning consolidation+index]` |

Claude pattern-matches on these to know what to check.

### What Runs in Background

| Operation | Background? | Rationale |
|-----------|-------------|-----------|
| **Consolidation** | ✅ Yes | Fire-and-forget. User doesn't need confirmation. |
| **Index rebuild** | ✅ Yes | Long-running. User can continue chatting. |
| **Index update** (incremental) | ✅ Yes | Triggered after consolidation, seamless. |
| **Search** | ❌ No | User is waiting for results. |
| **Status/draft reads** | ❌ No | Claude needs the content to respond. |

### Chained Background Operations

Consolidation and index update can be chained:

```bash
python3 << 'EOF' &
from job_tracker import start_job, complete_job, fail_job

try:
    start_job("consolidate+index")
    
    # Phase 1: Consolidate
    memory = connect()
    memory.consolidate("Journal entry: ...")
    
    # Phase 2: Update index with new commit
    index = CommitIndex.load()
    index.update_incremental()
    index.save()
    
    complete_job()
except Exception as e:
    fail_job(str(e))
EOF
```

Single background job, two operations, zero user-facing output on success.

---

## Open Questions

1. **Chunking strategy for commit messages**
   - One vector per commit? 
   - Split long messages into paragraphs?
   - Include commit metadata (date, category) in embedded text?

2. **What triggers index rebuild?**
   - Manual only?
   - Auto-check on search if stale?
   - Hook into consolidation flow?

3. **Should committed file content also be indexed?**
   - Current design: commits only (history focus)
   - Alternative: index everything, tag by source
   - Risk: scope creep, diminishing returns

4. **Search result format**
   - Just text + date?
   - Include SHA for linking?
   - Include relevance score?

5. **Integration with SKILL.md**
   - New methods documented there?
   - New "search your history" behavior guidance?

---

## Non-Goals (for v1)

- Real-time / streaming search
- Multi-modal (images, code)
- Distributed / multi-repo memory
- Fine-tuned embedding model
- Hybrid keyword + vector search
- Integration with Anthropic's native memory

---

## Implementation Phases

### Phase 0: Validate Assumptions
- [ ] Confirm fastembed works reliably in sandbox
- [ ] Test GitHub API pagination for large histories
- [ ] Measure: index 100 commits, search latency

### Phase 1: Core Infrastructure
- [ ] Extend git_operations.py with `log_full()`
- [ ] Create memory_search.py with CommitIndex class
- [ ] Basic build/save/load/search cycle

### Phase 2: Integration
- [ ] Add `search_history()` to MemorySystem
- [ ] Update SKILL.md with new capabilities
- [ ] Handle edge cases (stale index, missing index)

### Phase 3: Refinement
- [ ] Incremental indexing (since last SHA)
- [ ] Date filtering on search
- [ ] Relevance score thresholds

---

## Success Criteria

1. Can search 500+ commit history in <2 seconds
2. Results are semantically relevant (qualitative)
3. Index rebuild is idempotent and fast (<30s for 500 commits)
4. Zero impact on existing memory_system.py workflows
5. Token cost of search = query + k results (not full history)

---

## Appendix: Commit Message Design for Retrieval

### The Core Insight

The commit message is not metadata — it's the primary searchable artifact. The model writing the consolidation message is effectively pre-chunking and enriching the corpus at write time.

This means the consolidation prompt must move the model into a latent space where it produces **journal entries optimized for future semantic retrieval**, not terse git-style commit messages.

### What Makes a Good Search Corpus Entry

| Property | Why It Matters for Embeddings |
|----------|------------------------------|
| **Self-contained** | Entry makes sense without the diff; embedding captures full meaning |
| **Concept-dense** | Key ideas are named explicitly, not referenced obliquely |
| **Temporally anchored** | "Shifted from X to Y" or "First time seeing Z" aids evolution queries |
| **Consistently vocabularied** | Same concepts use same terms across entries (aids clustering) |
| **Right-sized** | Long enough to embed well (~50-200 words), short enough to return whole |

### What Hurts Retrieval

| Anti-pattern | Problem |
|--------------|---------|
| Terse/generic | "Updated positions" — embedding is noise |
| Referential | "As discussed above" — meaning lost without context |
| Meta-only | "Consolidated draft" — no semantic content |
| Too diffuse | 500-word essay — embedding averages out, loses specificity |
| Jargon-shifting | "Agents" in one entry, "autonomous systems" in another — fragments the concept |

### Prompt Engineering: Consolidation Guidance

The following would be added to SKILL.md or the consolidation reference doc:

---

**When consolidating, write the commit message as a journal entry for your future self.**

The commit message is your primary interface to your intellectual history. Six months from now, you (or another instance) will search this log semantically. Write as if you're leaving a note that will be found by meaning, not by filename.

**Structure:**

```
[Category]: [One-line summary of what crystallised]

[2-4 sentences explaining the insight, position shift, or understanding reached]

[Optional: what prompted this, what it supersedes, what remains open]
```

**Guidelines:**

1. **Name concepts explicitly** — Don't write "updated my thinking on this." Write "updated my position on agent autonomy boundaries."

2. **Mark transitions** — "Previously thought X, now see Y" is highly searchable for evolution queries.

3. **Include trigger context** — "After exploring Z" or "Prompted by conversation about W" aids retrieval.

4. **Use consistent vocabulary** — If you've called it "tool orchestration" before, don't switch to "capability routing" without reason.

5. **Keep it atomic** — One consolidation = one coherent insight. Don't bundle unrelated updates.

---

### Few-Shot Examples

**❌ Bad: Terse/Generic**
```
Updated positions.md
```
*Problem: Zero semantic content. Embedding is meaningless.*

**❌ Bad: Referential**  
```
Consolidated insights from recent discussion
```
*Problem: "Recent discussion" isn't searchable. What insights?*

**❌ Bad: Too Diffuse**
```
After a long conversation about many things including the nature of 
consciousness, the hard problem, qualia, and also some discussion of 
embeddings and vector databases and how they might relate to memory 
systems, I've updated my thinking on several fronts. First, regarding 
consciousness... [300 more words]
```
*Problem: Embedding averages across too many concepts. Won't surface for specific queries.*

**✅ Good: Self-Contained Insight**
```
positions: Revised stance on agent autonomy boundaries

Previously held that agents should always confirm before external actions.
Now see this as context-dependent: high-stakes/irreversible actions warrant
confirmation, but routine operations benefit from autonomous execution.
The key discriminator is reversibility, not impact magnitude.

Prompted by exploring the /do router pattern with Max.
```
*Why it works: Concepts named, transition marked, context included, atomic.*

**✅ Good: Evolution Marker**
```
methods: First articulation of "crystallisation readiness" criteria

Identified three conditions for when understanding is ready to commit:
1. Coherent — pieces fit together articulably
2. Stable — tested in dialogue, held up
3. Conviction — willing to stand behind it

This gives language to the previously intuitive sense of "not yet" vs "now."
```
*Why it works: Names the concept, lists specifics, notes what's new.*

**✅ Good: Open Thread**
```
open-questions: Tension between memory sparsity and retrieval richness

The two-branch architecture optimizes for token efficiency by keeping 
committed files small. But this creates a retrieval gap — historical 
context lives in commit messages, which aren't semantically searchable.

Possible resolution: local vector embeddings on commit log. Need to 
validate if this is technically feasible in sandbox environment.
```
*Why it works: States the tension, names the candidate solution, marks as open.*

---

### Integration with Consolidation Flow

The `consolidate(message)` method already requires a message. The change is guidance, not API:

```python
# Current (no guidance on message quality)
memory.consolidate("Updated positions")

# With retrieval-aware guidance
memory.consolidate("""positions: Shifted on agent confirmation patterns

Previously required confirmation for all external actions. Now advocate
for autonomy-by-default with confirmation reserved for irreversible 
operations. Key insight: reversibility is the discriminator, not impact.

Supersedes earlier blanket caution stance from March discussions.
""")
```

The indexing system trusts that the message is well-formed. Garbage in, garbage out — but the prompt engineering ensures it's not garbage.

---

## Appendix: Token Economics

| Operation | Current | With Vector Search |
|-----------|---------|-------------------|
| Load full history (500 commits) | ~50,000 tokens | N/A (impossible) |
| Search history | N/A | ~500 tokens (query + 5 results) |
| Index rebuild | N/A | 0 tokens (runs in Python) |

The value scales with history size. At 100 commits, brute force might work. At 1000, it's untenable. Vector search keeps retrieval cost constant.
