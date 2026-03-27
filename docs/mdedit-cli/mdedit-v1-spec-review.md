# mdedit v1 — Specification & Implementation Review

**Date:** 2026-03-27

## 1. Overview
The `mdedit` v1 specification is incredibly rigorous. The core "source surgery" architecture (via `tree-sitter-md` byte-offset splicing) is a massive success. The codebase elegantly addresses ambiguities in the spec as well (e.g., `append` correctly using `own_content_range.end` to inject before the first child header rather than the absolute end of the section span).

However, there is one critical area where both the spec and the current `v1` implementation require refinement to be optimal for AI workflows: **Output Stream Routing and Terminal (TTY) Detection**.

## 2. Issue 1: The `extract` Command's Pipe Behavior (Spec Fix)
**The Problem:** The spec currently dictates that when `extract` is piped, it should output "Raw markdown only" and drop the helpful `SECTION:` metadata header entirely. Because AI Agents (running in headless environments) often evaluate as "pipes", dropping this header leaves them completely blind to the verification metrics (word count, line numbers, child count) they need to confirm their edits.

**The Solution:** The spec should be updated. Instead of deleting the metadata header during a pipe, `extract` should simply print the `SECTION:` header to **`stderr`**, and the raw markdown content to **`stdout`**.

**Why this works:** Unix pipes easily pass the pure `stdout` data downstream while still surfacing the metadata via `stderr`. AI Agent runners (like Claude Code) naturally capture both `stdout` and `stderr`, ensuring the agent reads the rich metadata header without breaking the data pipe. No custom `--verbose` flags or manual TTY overrides are needed.

## 3. Issue 2: Write Operations Deviate from Spec (Implementation Refactor)
**The Problem:** The v1 specification correctly states that for all write operations (`replace`, `insert`, `append`, `delete`, etc.), the verification output and neighborhood context should be routed to `stderr` when piped. However, a review of the actual `v1` source code (in `src/commands/`) reveals that the implementation unconditionally uses the standard `print!` macro (which defaults to `stdout`) for all output. 

**The Solution:** The Rust codebase needs a refactor. The implementation requires unified terminal checking (e.g., using Rust's `std::io::IsTerminal` or similar mechanism) to properly split the streams:
- **If `is_terminal()` is `true` (Human Terminal):** Print verification context natively to `stdout`.
- **If `is_terminal()` is `false` (Pipe/Agent):** Redirect the verification context to `stderr` using `eprint!`.

## 4. The "It Just Works" Philosophy
By correcting the spec for `extract` and fixing the missing stream routing in the Rust codebase, the entire application achieves an elegant "it just works" state across all target audiences:
* **Humans (Terminal):** Receive both the data and the rich verification contexts cleanly on their screen through the standard visual output.
* **Scripts (Pipes):** Can safely chain data down the pipeline using the clean `stdout` stream, while diagnostic verifications bleed safely to the console via `stderr`.
* **AI Agents (Headless Environments):** Will receive the clean data via `stdout` and the rich verification contexts via `stderr`. They naturally capture and process both streams automatically, solving the context blindness without requiring them to learn any new CLI switches.

## 5. Required Specification Updates
To align the specification with this routing philosophy, these specific changes are necessary:

1. **Under `## TTY-aware output`:**
   * **Change the table row for `extract` (Pipe):** 
     * From: `Raw markdown only`
     * To: `Raw markdown to stdout, SECTION: metadata header to stderr`
2. **Under `### extract` section:**
   * **Change the "Output (pipe or `--to-file`)" description:**
     * From: "Raw markdown content only, no metadata header."
     * To: "Raw markdown content to stdout. Metadata header output safely routed to stderr."
