# Codebase Memory — Code Discovery Protocol

For code exploration in this repository, use codebase-memory-mcp tools BEFORE 
Grep/Glob/Read. The graph returns precise structural results in ~500 tokens 
vs ~80K for grep.

## Quick Decision Matrix

| Question | Tool |
|----------|------|
| Who calls X? | `trace_path(direction="inbound")` |
| What does X call? | `trace_path(direction="outbound")` |
| Find by name pattern | `search_graph(name_pattern="...")` |
| Dead code | `search_graph(max_degree=0, exclude_entry_points=true)` |
| Read source | `get_code_snippet(qualified_name)` |
| Text/config search | `search_code` or Grep (fallback) |

If the project is not indexed, run `index_repository` first.

For detailed workflows, Cypher examples, and tool reference, see:
{{REFERENCES_PATH}}
