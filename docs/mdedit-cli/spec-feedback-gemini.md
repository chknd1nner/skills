This is a remarkably robust and well-conceived specification. The architecture directly addresses the most glaring friction points in agentic text editing. LLMs are notoriously unreliable at spatial reasoning—asking a model to execute a standard `patch` file or execute a `sed` command targeting specific line numbers almost always ends in hallucinated offsets or catastrophic truncation. By shifting the paradigm to semantic, heading-based addressing via a concrete syntax tree, you bypass the token-counting weakness entirely.

The choice to utilize `tree-sitter-md` is the standout technical decision here. Because markdown lacks a formal, universally strictly-adhered-to grammar, standard serializers invariably clobber the user's idiosyncratic formatting—stripping trailing whitespace, standardizing list indentations, or reformatting tables. A CST source-surgery approach ensures that unaddressed sections of the file remain byte-for-byte identical, which is critical for maintaining clean version control histories and not enraging human collaborators. 

As I review the mechanics of the write operations and the TTY-aware output, a few architectural edge cases and operational realities stand out that might warrant definition before you lock the v1 scope.

### Structural and Edge-Case Considerations

**1. Whitespace Boundary Management**
When executing a `delete` or an `extract` followed by a `replace`, whitespace accumulation is a common artifact. If "## Background" is deleted, does the parser selectively absorb the preceding and succeeding blank lines to prevent the document from developing massive, empty visual gaps? Defining a strict convention for newline preservation (e.g., "every section ensures exactly one trailing blank line unless it is the EOF") will prevent the markdown from degrading visually after multiple automated passes.

**2. The `_preamble` Boundary**
You have intelligently reserved `_preamble` for content before the first heading. However, how do operations interact with the YAML frontmatter? If a user executes `mdedit prepend doc.md _preamble --content "Note: updated"`, it is vital that the tool splices this text *after* the closing `---` of the frontmatter, rather than at byte index 0, which would break the document's metadata block. 

**3. Complex Frontmatter Types**
The `frontmatter set` command notes that values are parsed as JSON if valid, which is a clever way to handle arrays or booleans from the CLI. But YAML frequently utilizes multi-line pipe strings (`|`) for long-form descriptions or summaries. It would be highly beneficial to ensure the frontmatter writer can gracefully serialize multiline standard input into a properly indented YAML block, rather than forcing it into a single-line JSON string representation.

**4. Document Initialization**
The specification outlines how to mutate existing files, but agentic workflows frequently generate new artifacts. If `doc.md` does not exist, does an `insert` or `append` command fail with Exit Code 3, or does it provision the new file? Supporting file creation with a clean write command reduces the need for the LLM to drop back to standard bash `echo` commands just to bootstrap the file before using `mdedit`.

**5. Atomic Locking**
While optimistic locking is explicitly out of scope for v1, consider the realities of asynchronous LLM tool calling. If an agent fires an `extract`, spends twenty seconds generating a modification, and then fires a `replace`, the underlying file might have been touched by another process or a human. Emitting a lightweight checksum or a byte-size validation in the `extract` output, which the `replace` command can optionally check via a flag, could prevent devastating race conditions without requiring a full locking daemon.

The output neighborhood design—showing the preceding and succeeding section headers—is brilliant. It gives the LLM immediate, localized grounding, confirming the operation's success without requiring a costly re-read of the entire document buffer. 

Would you like me to draft the Rust CLI scaffold using `clap` and the `tree-sitter-md` initialization logic so we can start mapping out the byte-offset surgical splices?