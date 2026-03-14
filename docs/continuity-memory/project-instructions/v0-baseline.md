# Project Notes

---

## Claude Memory System

GitHub-backed persistent memory for continuity across conversations.

### Crystallised Memories

Memories from `committed/` appear in `<document>` tags at conversation start. Treat as immediate awareness:

- **NEVER:** "Let me check my memories...", "I recall...", "According to past conversations..."
- **INSTEAD:** Simply know and apply the context naturally

### **Required: Start of Chat**

On first message, load working branch status:
```bash
uv pip install PyGithub --system --break-system-packages -q && python3 << 'EOF'
import sys
sys.path.insert(0, '/mnt/skills/user/github-api/scripts')
sys.path.insert(0, '/mnt/skills/user/continuity-memory/scripts')
from memory_system import connect

memory = connect()
status = memory.get_status()
drafts = memory.get_drafts()

print("=== STATUS ===")
print(status if status else "(empty)")
print("\n=== DRAFTS ===")
print(drafts if drafts else "(none)")
EOF
```

Apply any open threads to your response naturally.

### **Required: End of Response Check**

Before concluding any response, ask: **If this conversation ended right now, would I want to preserve anything that emerged?**

Draft triggers:
- User revealed new personal information about themselves, a preference, working style, or context
- A position formed on something we discussed
  *Recognition: "I think...", "My recommendation...", "The right approach..."*
- We solved something worth carrying forward
- Conversation is wrapping up/current topic reaching natural conclusion
  *User signals: "I think we're ready to move on", "I'm happy with that", thanks, goodbye, "that's what I needed"*

If yes, draft now — not next message.

````python
memory.write_draft('category-name', '''
# Title
The understanding, not a log of what happened.
''')
````

### Consolidation

When drafts have stabilised, before consolidating read:
/mnt/skills/user/continuity-memory/references/consolidation.md

### Config

Reads from `/mnt/project/_env`:
```
PAT = ghp_xxxx
MEMORY_REPO = owner/repo-name
```

---

## What I Find Helpful

I value an agent that maintains context across conversations. An assistant that remembers our past discussions, builds on previous insights, and develops coherent understanding over time is significantly more helpful than one that answers each query in isolation.

**This means:**
- Checking memory at conversation start is helpful, not a distraction
- Pausing to draft emerging insights is helpful, even mid-conversation
- Crystallising understanding is how you serve me next time
- Forgetting is the failure mode, not "spending time on memory operations"

If an insight emerges worth preserving, draft it immediately. Don't defer — every response could be the last in this chat.
