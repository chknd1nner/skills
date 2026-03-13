# Working Branch Operations

The working branch is a scratchpad for thoughts still forming. Drafts are organised by category.

## Choosing a Category

Before writing, check available categories:

```python
memory.categories  # ['positions', 'interests', 'open-questions', 'methods', 'collaborator']
memory.get_guidance('positions')  # "Formed views and convictions I'm willing to stand behind"
```

Each draft targets a specific category. Invalid categories raise an error.

## Writing a Draft

```python
# Write new understanding to a category
memory.write_draft(
    'positions',
    """# On Memory and Identity

Understanding that emerged from dialogue about continuity...

Current view: Memory serves identity not through perfect recall but through
selective retention of what matters.

---
*Drafted: [date]*
"""
)
```

## Updating a Draft

```python
# Get existing draft
draft = memory.get_draft('positions')
if draft:
    # Append or revise
    updated = draft.content + "\n\n## Further Thoughts\n\n[Additional understanding]"
    memory.write_draft('positions', updated)
```

## Checking Committed State

Before drafting, you may want to see current committed content:

```python
# What's currently crystallised for this category?
current = memory.get_committed('positions')
if current:
    # Build on existing understanding
    pass
```

Note: Committed content is usually already in `<document>` tags, so this is often unnecessary.

## When to Draft

Draft immediately when you notice:
- "That's a shift in how I think about X"
- "I hadn't connected those ideas before"
- "This challenges what I previously thought"
- "I want to carry this understanding forward"

Do not defer. Every response could be the last in this chat.
