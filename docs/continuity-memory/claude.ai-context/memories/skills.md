```
**Purpose & context**

Max is building a personal AI productivity ecosystem centered on Claude.ai, with a focus on creating custom skills, agentic workflows, and persistent memory capabilities. The work spans skill development for Claude Code and Claude.ai, multi-agent orchestration, and tooling to extend Claude's capabilities beyond its default constraints (e.g., Reddit access, persistent memory, cross-session continuity). Max shares skills publicly in communities like r/claudexplorers and r/claudeai, suggesting a mix of personal utility and community contribution goals.

**Current state**

Active projects and recent work include:

- **fetch-reddit skill**: Functional skill using Arctic Shift API for near-real-time Reddit access (bypassing Claude's egress block on reddit.com). Anubis bot protection on Redlib instances was solved with a custom pure-Python SHA-256 proof-of-work solver. Extensive Arctic Shift API capabilities have been documented but not yet fully integrated into the skill. Local summarization via small models (flan-t5) was tested and found inadequate — small models lack the abstraction capability needed.
- **Claude Code multi-agent architecture**: Building a "deep research" skill where a lead agent spawns researcher subagents. Currently uses `claude -p` CLI processes communicating over the filesystem. Actively considering refactoring so the lead agent (already in a headless session) spawns researchers as native `Task` subagents, with a hybrid fallback to `claude -p` for deeper nesting layers.
- **RDL report generation skill**: Built a Python `RdlBuilder` class generating valid SSRS RDL XML for both direct SQL and Power BI semantic model (PBIDATASET/DAX) data sources, modeled after the sql-powerquery skill pattern.
- **continuity-memory skill**: Persistent memory system using GitHub as a backend. Vector search extension was designed and benchmarked (fastembed/bge-small-en-v1.5 locally in sandbox), with commit messages as the primary searchable corpus. Architecture follows "silent success, visible failure" philosophy.

**On the horizon**

- Integrating the full Arctic Shift API capabilities (flair filtering, pagination, time ranges, user profiles, comment search) into the fetch-reddit skill
- Deciding on and implementing the native `Task` subagent refactor for the deep research skill
- Potentially implementing vector search for continuity-memory using local ONNX embeddings
- Gemini CLI skill for task delegation/consultation with Gemini from within Claude Code

**Key learnings & principles**

- **Skill packaging**: Proper distribution requires zip archives with `.skill` extensions to trigger Claude.ai's import UI and provide file explorer preview. Plain text files renamed to `.skill` trigger the import button but fail preview rendering.
- **YAML front matter constraints**: Skill descriptions have an undocumented character limit (~800–1000 chars); exceeding it causes silent upload failure. **Descriptions cannot contain semicolons unless escaped**, as unescaped semicolons prematurely terminate the description block. The YAML description serves as pre-invocation routing logic; post-execution workflow guidance belongs in the skill body — a separation that improves architecture.
- **Skills are project-scoped**: The skills manifest may be injected globally, but `/mnt/skills/user/` is project-scoped. Outside a project, Claude sees skills listed but gets file-not-found errors — worse than if the skill weren't listed at all.
- **Sandbox API isolation**: The sandbox requires explicit API key authentication; it does not inherit any browser-level auth context that artifacts use for Anthropic API calls.
- **Small models for summarization**: Sub-1B parameter models produce fragmented, non-abstractive outputs for Reddit summarization — not suitable for this use case without significant upscaling.
- **Reddit egress**: reddit.com is blocked at Anthropic's egress proxy level (not TLS fingerprinting), making curl_cffi ineffective for direct Reddit access.
- **Claude Code subagent nesting**: Native `Task` subagents cannot themselves spawn further subagents; `claude -p` via Bash is the workaround for deeper nesting but loses context.

**Approach & patterns**

- Prefers **token-efficient** implementations: programmatic generation over static data files, precise file edits over full regeneration, quiet/non-verbose skill output for mid-conversation invocation.
- Favors **composable skill architecture**: skills designed to interoperate (e.g., sql-powerquery + RDL skill, fetch-reddit + summarization).
- Uses a **test-first, systematic exploration** approach when evaluating new APIs or tools — probing all endpoints before committing to an implementation.
- Brainstorming and ideation work uses a structured multi-session workflow with handover documents saved to project knowledge, enabling continuity across chat sessions.
- Prefers **"it just works" UX** for shared skills — minimal setup friction, self-installing dependencies, visual demonstration over technical explanation.
- Anti-slop philosophy for generative outputs: actively avoids common AI-generated patterns (e.g., name blocklists for the namegen skill).

**Tools & resources**

- **Claude.ai skills system**: Custom skills at `/mnt/skills/user/`, SKILL.md format with YAML front matter
- **Claude Code**: Headless mode (`claude -p`), `Task` tool for subagents, slash commands, hooks
- **Arctic Shift API** (`arctic-shift.photon-reddit.com`): Primary Reddit data source
- **GitHub API** (`git_operations.py`): Filesystem-like operations for sandbox, used as memory backend
- **fastembed + bge-small-en-v1.5**: Local ONNX embedding model for vector search in sandbox
- **uv**: Preferred package installer (faster than pip); still requires `--break-system-packages` flag in sandbox
- **Report Builder / SSRS**: RDL XML generation for paginated reports against SQL and Power BI Fabric sources
- **Gemini CLI**: Being evaluated for cross-model delegation from Claude Code
```