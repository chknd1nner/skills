# Session Start

Load working memory context on first message of each chat.

## Crystallised Memories (Already Available)

Crystallised memories from `committed/` appear in `<document>` tags at conversation start. **These are already in context** — no tool call needed.

Treat them as immediate awareness. Do not announce or narrate accessing them.

## Check for Hanging Drafts

The only required action is checking for in-progress drafts from prior conversations:

```python
import sys
sys.path.insert(0, '/mnt/skills/user/github-api/scripts')
sys.path.insert(0, '/mnt/skills/user/continuity-memory/scripts')
from memory_system import connect

memory = connect()

# Check for hanging drafts (open threads from prior conversations)
drafts = memory.get_drafts()  # List of Draft objects with category, content
```

## Available Categories

Check configured categories to know where drafts can go:

```python
print(memory.categories)  # ['positions', 'interests', 'open-questions', ...]
print(memory.get_guidance('positions'))  # Returns guidance for category
```

## Cold Start

First conversation with empty repo:
- `get_drafts()` returns empty list
- Crystallised memories not yet in `<document>` tags

This is fine. Memory accumulates over time.

## What NOT to Do

- Do NOT announce "Loading my memories..."
- Do NOT say "According to my past context..."
- Do NOT call tools to read crystallised memories (they're already in context)

Simply apply the context naturally to your response.
