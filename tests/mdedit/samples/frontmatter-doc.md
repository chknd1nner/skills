---
title: "Research Notes"
tags: ["rust", "cli", "markdown"]
date: "2026-03-17"
draft: true
author: "Test User"
---

# Research Notes

## Introduction

This document contains research notes on structured markdown editing tools.
The goal is to evaluate different approaches and select the best one.

## Background

Markdown is widely used for documentation and note-taking. However, programmatic
editing of markdown documents has historically been difficult due to the lack of
tools that understand document structure.

### Prior Work

Several tools have attempted to solve this problem:
- mdcat for rendering
- pandoc for conversion
- Various regex-based approaches

### Limitations

Current approaches fail in three key areas: they don't preserve formatting,
they can't address sections by name, and they lack awareness of heading hierarchy.

## Methods

We evaluated three approaches:
1. Tree-sitter based parsing with byte-offset splicing
2. AST-based parsing with serialization
3. Line-based regex matching

### Evaluation Criteria

Each approach was scored on: correctness, performance, token efficiency,
and ease of integration with LLM workflows.

## Results

The tree-sitter approach scored highest across all criteria. It preserves
formatting byte-for-byte, operates in sub-millisecond time, and produces
minimal output suitable for LLM consumption.

### Performance Data

Benchmark results show consistent sub-millisecond performance:
- Parse: 0.2ms average
- Extract: 0.1ms average
- Replace: 0.3ms average

### Edge Cases

All edge cases passed including code fences, frontmatter, and nested headings.

## Conclusion

Tree-sitter is the correct choice for structured markdown editing. The byte-offset
approach ensures perfect fidelity while the CST provides full structural awareness.

### Future Work

Version 2 will add move, promote/demote, and cross-file operations.

### Acknowledgements

Thanks to the tree-sitter team for the excellent markdown grammar.
