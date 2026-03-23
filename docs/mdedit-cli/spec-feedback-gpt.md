This is already a strong spec. It has the right instinct for an LLM-facing CLI: low token cost, deterministic behavior, and outputs that answer the only two questions the model really cares about after a write: “did it land?” and “where exactly did it land?”

The main thing I would tighten now is the contract surface. A few places still leave room for implementation drift.

First, define counting rules precisely. “Words,” “lines,” and “content lines” need an exact algorithm. Right now it is not fully clear whether headings count as content, whether code fences count as words, whether blank lines count toward section size, how tables are counted, and whether frontmatter is included in document totals. Those details matter because they affect every summary line and every exit-path decision.

Second, make the section model more explicit around nesting edge cases. Your addressing rules are good, but I would specify how duplicate headings are handled across different branches, whether `_preamble` is valid in `replace`/`append`/`prepend`, and whether “child sections included” means all descendants recursively or only immediate children. I suspect you mean recursive inclusion, but the spec should say so plainly.

Third, there is one place where the behavior needs a harder rule: when input content contains headings. Right now you warn about “heading levels higher than parent section,” but that is a structural hazard, not just a cosmetic one. You should decide whether mdedit will always preserve nested headings inside replacement content as real structure, or whether write commands only treat incoming content as raw text for the target section body. Either choice is fine; ambiguity is not.

Fourth, the output contract for write commands is close, but I would normalize it more. Every mutating command should probably emit the same four facts in the same order: action, target, before/after metrics, and neighborhood proof. That would make the tool much easier for an LLM to parse reliably. Right now `replace`, `append`, `prepend`, `insert`, `delete`, `rename`, and frontmatter edits are similar, but not identical enough.

Fifth, the exit codes are good, but I would separate “validation found warnings” from “hard validation failure” more clearly. At the moment exit code `5` covers any `⚠` issue in `validate`, while `ℹ` is informational. That is fine, but then the spec should say exactly which findings map to warning vs info. Duplicate heading text is currently shown as `ℹ`, which suggests it is not a failure even though it can cause ambiguous matching later. That may be intentional, but I would call it out explicitly.

The strongest part of the spec is your decision to avoid serialization round-trips and operate by byte splicing. That is the right architecture for this tool. It also makes your tree-sitter choice feel justified rather than decorative. The claim about incremental reparsing is especially useful for future multi-edit support, even if v1 does not expose that directly.

A couple of implementation-facing details are worth pinning down before coding:

* whether frontmatter is part of `_preamble` or excluded from it;
* whether search matches are case-sensitive;
* whether `frontmatter set` parses scalars as JSON only when valid JSON exists, or also accepts YAML-ish bare scalars;
* whether `--to-file` suppresses all stdout except the confirmation line;
* whether write ops in pipe mode always send the neighborhood proof to stderr or only when stdout is not a TTY.

If you want this spec to feel “implementation ready,” I would next turn it into a stricter behavior matrix: command × input mode × TTY mode × success/failure output × exit code. That would flush out the remaining contradictions fast.