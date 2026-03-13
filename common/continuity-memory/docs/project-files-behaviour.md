## Project file storage and manipulation

- Project files added directly by the user are stored in `/mnt/project/`
- Copy files to `/mnt/home/` to modify them
- Individual project files are listed between `<project_files>` tags at the top of the context just after the system prompt like this:
```
<project_files>
  Project files are available in the /mnt/project/ directory:
  <file_path>/mnt/project/test-file.md</file_path>
  - Use the view tool to read these files
  - These files are read-only
  - Changes to these files will not be saved back to the project
</project_files>
```

### Non-RAG mode (small projects)

- When total project file size is below Anthropic's retrieval threshold, file contents appear inline within `<document>` tags before the user message:
```
<documents>
  <document index="1" media_type="text/plain">
    <source>test-file.md</source>
    
    <document_content>This is a test project knowledge file...</document_content>
  </document>
</documents>
``` 
- Files also exist as materialised copies in `/mnt/project/`
- **Prefer reading from inline `<document>` tags** — there is no benefit to using `view` or bash to read from `/mnt/project/` unless you have copied and modified a file in `/mnt/home/` and need to re-read your updated version
- **Exception:** Files supplied via first-party integrations (e.g. GitHub, Google Docs connectors) are not materialised in `/mnt/project/` — the `project_knowledge_search` tool is the only way to access their contents

### RAG mode (large projects)

- When total project file size exceeds Anthropic's retrieval threshold, file contents do **not** appear inline
- Use `project_knowledge_search` tool with natural language queries to retrieve BM25-ranked contextual chunks
- Alternatively, read full file contents from `/mnt/project/` using the `view` tool or bash commands
- **Exception:** Files supplied via first-party integrations (e.g. GitHub, Google Docs) do **not** appear in `/mnt/project/` — the `project_knowledge_search` tool is the only way to access their contents