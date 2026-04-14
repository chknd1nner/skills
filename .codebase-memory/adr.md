# Architecture Decision Records

## ADR-001: Skills Repository Architecture

**Status:** Accepted

**Context:**
The skills repository is a multi-platform collection of reusable skills and utilities designed to work across Claude Code, Claude.ai Web, and other platforms. The codebase contains 6,586 code elements organized as documentation, configuration, and JavaScript/Node.js implementations with 145 test relationships indicating a test-driven approach.

**Decision:**
Adopt a modular, platform-agnostic architecture organized by platform compatibility:

1. **Directory Structure by Platform**
   - `claude-code-only/` — Skills requiring CLI tools, bash, or non-web execution
   - `claude-web-only/` — Skills designed exclusively for Claude.ai web interface
   - `common/` — Skills that work across both platforms
   - `work-in-progress/` — Drafts and iterations (with `archive/` for superseded work)

2. **Skill Definition Format**
   - YAML-based skill definitions with sections (3,584 detected) for metadata, instructions, and workflows
   - Structured skill content enabling consistent parsing and execution
   - Clear separation of platform-specific implementation details

3. **Testing & Quality**
   - Test-driven development with 145 test relationships across the codebase
   - Test files colocated with implementation for rapid feedback
   - Semantic similarity analysis (264 SIMILAR_TO edges) to identify refactoring opportunities

4. **Code Integration**
   - 461 functions and 345 methods providing core skill logic
   - 452 modules enabling modular, reusable implementations
   - 1,336 call relationships showing tight integration between components
   - 84 semantic relationships for logical grouping beyond syntax

5. **API & Routing**
   - 2 API routes for integration with external systems where needed
   - Minimal routing footprint keeps skills lightweight and CLI-focused

**Consequences:**

*Positive:*
- Clear ownership of skills by platform (no ambiguity about where skill belongs)
- Simplified reuse — common skills work everywhere without modification
- Isolated experiments in WIP don't break production skills
- Strong test coverage ensures quality across releases
- Modular functions enable code reuse and reduced duplication

*Negative:*
- Developers must understand platform constraints before placing skills
- Code duplication may emerge if `claude-code-only` and `common` share similar patterns
- Archive management adds overhead when skills are superseded

**Alternatives Considered:**
- Single flat directory: Rejected due to unclear platform support
- Platform-specific files with shared naming: Rejected due to complexity in discovery
- Monorepo with separate versioning: Rejected due to tight platform integration

**Implementation Notes:**
- New skills must be reviewed for platform compatibility before placement
- Skills should minimize platform-specific code to enable future migration to common/
- Test coverage should match or exceed 145 test relationships per 461 functions ratio
