# Retrieving Memories

**v0.4 Update:** Retrieval is now handled by Anthropic's systems, not this skill.

## How Retrieval Works

| Project Size | Mechanism | Your Action |
|--------------|-----------|-------------|
| **Small (non-RAG)** | Pre-injected `<document>` tags | None — already in context |
| **Large (RAG)** | `project_knowledge_search` tool | Use Anthropic's built-in tool |

## Non-RAG Mode (Most Common)

When memory repo is connected via GitHub integration and total size is under the RAG threshold:

- All files in `committed/` appear in `<document>` tags at conversation start
- Content is already in context before you respond
- No tool call needed to access it
- Treat as immediate awareness

## RAG Mode (Large Projects)

If committed memories grow beyond the RAG threshold:

- Use `project_knowledge_search` tool (provided by Claude.ai)
- Query with natural language: "What do I understand about X?"
- Returns contextual chunks from project files

This is Anthropic's production retrieval system — no custom search implementation needed.

## Reading Specific Categories

If you need to read a specific category (e.g., before updating it):

```python
content = memory.get_committed('positions')
```

But this is rarely needed — committed content is usually already visible in `<document>` tags.

## Why No Custom Search?

Previous versions included a BM25 search index. This was removed because:

1. Pre-injection already provides crystallised memories in context
2. `project_knowledge_search` handles RAG mode retrieval
3. Bounded category system (max 7 files) keeps total size manageable
4. Eliminates index maintenance overhead
