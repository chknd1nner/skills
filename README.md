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

Currently, the following skills are available:

*(None yet - add skills as they are created)*

## Getting Started

For detailed information about this repository's purpose and structure, see [CLAUDE.md](./CLAUDE.md).

When creating or modifying skills, always consult the **skill-builder** skill to ensure you follow best practices and have the correct instructions.

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.
