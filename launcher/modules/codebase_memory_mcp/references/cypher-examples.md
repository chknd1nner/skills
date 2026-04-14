# Cypher Examples (for query_graph)

```cypher
# Find HTTP call edges
MATCH (a)-[r:HTTP_CALLS]->(b) 
RETURN a.name, b.name, r.url_path, r.confidence 
LIMIT 20

# Find functions matching pattern
MATCH (f:Function) WHERE f.name =~ '.*Handler.*' 
RETURN f.name, f.file_path

# Find what main calls
MATCH (a)-[r:CALLS]->(b) WHERE a.name = 'main' 
RETURN b.name

# Find cross-service dependencies
MATCH (a)-[r:HTTP_CALLS|ASYNC_CALLS]->(b) 
WHERE a.project <> b.project 
RETURN a.name, type(r), b.name

# Find functions with high complexity
MATCH (f:Function) 
WHERE f.cyclomatic_complexity > 10 
RETURN f.name, f.file_path, f.cyclomatic_complexity 
ORDER BY f.cyclomatic_complexity DESC
```
