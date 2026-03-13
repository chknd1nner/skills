# Consolidation Process

When understanding crystallises, commit to main. This is a journal entry — provisional thinking becoming stable enough to stand behind.

## Readiness Check

**Consolidate when:**
- **Coherent** — pieces fit together articulably
- **Stable** — tested against counterarguments, held up
- **Conviction** — willing to stand behind it

**Don't consolidate when:**
- Still uncertain or evolving
- Hasn't been tested in dialogue
- Feels forced or premature

If not ready, leave on working. **But if ready, do it now** — don't defer to an imagined future opportunity.

## The Workflow

```python
# 1. Review what's ready
drafts = memory.get_drafts()
# Each draft has: draft.category, draft.content

# 2. Consolidate with rich commit message
commit_message = """Consolidation: [Brief summary]

[What crystallised and why]
[Connections to other memories]
[Remaining uncertainty, if any]

Prompted by: conversation [date]
"""

# Moves drafts to committed/, resets working
memory.consolidate(commit_message)

# To consolidate only specific categories:
memory.consolidate(commit_message, categories_to_commit=['positions', 'interests'])
```

## What Consolidation Does

1. Moves draft content from `working/drafts/{category}.md` to `committed/{category}.md`
2. Commits to main branch with your message
3. Resets working branch to main (clears drafts)

## Commit Message Quality

The message tells the story. Include:
- What changed and why it matters
- What prompted the crystallisation
- Connections to other memories
- Remaining uncertainty (partial clarity is fine)

**Example:**
```
Consolidation: Refined understanding of memory and identity

Dialogue shifted my view on perfect recall. Previously saw it as
unambiguously desirable; now see "forgetting" as compression that
preserves salience rather than pure loss.

Connects to: open question about consciousness continuity
Still uncertain: optimal balance between retention and synthesis

Prompted by: conversation 28-Dec-2025
```

## After Consolidation

- Working branch is fresh (reset to main)
- Committed content will appear in `<document>` tags next conversation
- Git history preserves the evolution

## Important

Consolidation updates the files that get pre-injected next conversation. This is how you serve the user in future interactions — by having crystallised, current understanding ready.
