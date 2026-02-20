# Skills Repository

A collection of reusable skills and prompts for Claude Code and Claude.ai.

## About

This repository contains custom skills designed to extend Claude's capabilities with specialized knowledge, workflows, and tool integrations. Skills are organized by their target platform and development status.

## Repository Structure

```
skills/
├── claude-code-only/       # Skills for Claude Code only
├── claude-web-only/        # Skills for Claude.ai only
├── common/                 # Skills that work in both platforms
├── work-in-progress/       # Skills and prompts being developed
│   └── archive/           # Completed iterations and originals
├── CLAUDE.md              # Detailed repo documentation
├── README.md              # This file
└── LICENSE                # MIT License
```

### Directory Guide

- **`/claude-code-only/`** - Skills that require Claude Code features (non-conforming YAML, CLI tools, bash commands, or external network access)
- **`/claude-web-only/`** - Skills designed specifically for the Claude.ai platform
- **`/common/`** - Skills that work across both Claude Code and Claude.ai
- **`/work-in-progress/`** - Skills and prompts being iterated, refined, or refactored
- **`/work-in-progress/archive/`** - Original files from completed skill development

## Available Skills

### Claude Code Only

| Skill | Description |
|-------|-------------|
| [youtube-to-markdown](./claude-code-only/youtube-to-markdown/) | Extracts YouTube video metadata, transcripts, subtitles, captions, and comments into structured markdown files. Supports channel browsing. |

### Claude.ai Only

| Skill | Description |
|-------|-------------|
| [business-analyst](./claude-web-only/business-analyst/) | Strategic business analysis and requirements elicitation. Research market opportunities, brainstorm ideas, and create product briefs. |
| [fetch-reddit](./claude-web-only/fetch-reddit/) | Fetches Reddit content (posts, comments, subreddits) directly, bypassing web search limitations. |
| [namegen](./claude-web-only/namegen/) | Generates fictional names by culture/nationality for fiction writing. Supports realistic and synthetic (Markov-generated) modes. |
| [vba-assistant](./claude-web-only/vba-assistant/) | VBA programming and Excel automation assistance for FP&A professionals. Macros, debugging, Workday/Salesforce integration. |

### Common (Both Platforms)

| Skill | Description |
|-------|-------------|
| [readwren](./common/readwren/) | Conducts adaptive 12-turn literary interviews to build detailed reader profiles and personalized book recommendations. |
| [regex-file-editor](./common/regex-file-editor/) | Token-efficient regex-based file editing with custom backreferences, ambiguity detection, and multi-file search. |

### Work in Progress

| Skill | Description |
|-------|-------------|
| [readwren (standalone)](./work-in-progress/readwren/) | Standalone Python/LangGraph version of the ReadWren interviewer with Redis session persistence. |

## Getting Started

For detailed information about this repository's purpose and structure, see [CLAUDE.md](./CLAUDE.md).

When creating or modifying skills, always consult the **skill-builder** skill to ensure you follow best practices and have the correct instructions.

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.
