Build a table of contents for the document at {{WORKDIR}}/{{FIXTURE}}.

1. Extract all headings from the document.
2. Format them as a nested markdown list (indented by heading level).
3. Prepend the table of contents to the very top of the document
   (before any existing content, but after frontmatter if present).

The TOC should look like:
- Background
- Implementation
  - Architecture
  - Data Model
  ...
- Results
  ...

(Adjusted to match the actual headings in the document.)
