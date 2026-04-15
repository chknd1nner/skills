#!/bin/bash
# CBM code-discovery gate — bundled with skills launcher.
# Nudges Claude toward codebase-memory-mcp for code discovery.
# First Grep/Glob/Read/Search per session -> block with nudge, marker created.
# Subsequent calls in the same session -> allow through.
GATE=/tmp/cbm-code-discovery-gate-$PPID
find /tmp -name 'cbm-code-discovery-gate-*' -mtime +1 -delete 2>/dev/null
if [ -f "$GATE" ]; then
    exit 0
fi
touch "$GATE"
echo 'BLOCKED: For code discovery, use codebase-memory-mcp tools first: search_graph(name_pattern) to find functions/classes, trace_path() for call chains, get_code_snippet(qualified_name) to read source. If not indexed, call index_repository first. Fall back to Grep/Glob/Read/Search for text/config content only. To proceed with Grep/Search, retry.' >&2
exit 2
