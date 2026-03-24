# mdedit Token Efficiency Benchmark — Design Spec

Quantify the token cost advantage of mdedit over traditional editing tools (Edit, Write, Bash) for LLM-driven markdown operations — both reads and edits.

## Hypothesis

mdedit reduces total session token consumption compared to standard Claude Code tools, with the advantage scaling as document size and task complexity increase. Secondary hypothesis: mdedit produces lower variance in token cost because it removes tool-selection ambiguity.

## Methodology

### Approach: hybrid isolated + integration

Two complementary measurement strategies:

**Isolated operations** test a single atomic editing task per run. Each task is run against three fixture files of increasing size. This produces clean per-operation token data and scaling curves.

**Integration workflows** test realistic multi-step tasks that compound multiple operations. These capture the ecological cost of a real editing session — including verification reads, context buildup, and tool selection overhead.

### Conditions

Each task is run under two conditions:

**Condition A (mdedit):** Agent has access to mdedit via Bash, plus standard Read/Edit/Write tools. System prompt includes a self-contained mdedit command reference (mdedit is not in training data).

**Condition B (baseline):** Agent has access to Read, Edit, Write, and Bash only. No mdedit binary on PATH. System prompt gives the same editing task with no tool guidance — the agent uses whatever approach it naturally selects.

Both conditions use identical task prompts (minus the mdedit reference) and the same model.

**On the guidance asymmetry:** Condition A includes a tool reference that Condition B lacks. This is intentional — the command reference is part of the mdedit "package" and reflects realistic deployment (an LLM cannot use mdedit without being told it exists). The benchmark measures the total cost of adopting mdedit, including the prompt overhead of the reference. The relevant question is not "is mdedit faster when the agent already knows both tools equally well?" but "does adding mdedit + its reference to a workflow save tokens compared to the default toolset?"

### Model selection

**Primary model: Haiku.** Cost-efficient for a benchmark with many runs, and consistent with the existing mdedit test harness.

**Failure protocol:** Any task that fails on Haiku — under either condition — is re-run on Sonnet. Both conditions are retried for the same failed task, so we can distinguish between model-tier failures (both conditions fail on Haiku, both succeed on Sonnet) and tool/prompt failures (one condition fails regardless of model). This produces secondary data about minimum model tier for mdedit adoption.

### Repetitions and variance

Each condition × task × file size combination is run **5 times**. Results report min, median, and max token counts. Median is the summary statistic (not mean) — this is robust to outliers and to prompt caching effects, where sequential runs may benefit from cached prefixes. Variance itself is a finding — if baseline runs show high variance (due to unpredictable tool selection), that supports the case for mdedit's deterministic workflow.

---

## Fixture Files

Three purpose-built markdown files with controlled structure and content. Stored in `tests/mdedit/benchmarks/fixtures/`.

All three fixtures share a consistent set of heading names (e.g., all have "Background", "Implementation", "Results" sections). This allows prompts to reference section names without per-fixture templating. The files differ in section content length, nesting depth, and total document size — not in structural naming.

### small.md (~50 lines, 5–6 sections)

A simple project README. Sections are 5–10 lines each. Single heading level. At this size, the Edit tool is expected to be competitive — this establishes the baseline where mdedit's advantage is minimal.

### medium.md (~200 lines, 15–20 sections, 2 levels of nesting)

A design document or specification. Mix of short sections (10 lines) and medium sections (30 lines). Parent/child heading relationships enable nested addressing tests.

### large.md (~500+ lines, 30+ sections, 3 levels of nesting)

A comprehensive reference document. Some sections exceed 50 lines. This is where section replacement should show the clearest divergence — the Edit tool must quote entire section content while mdedit addresses by name.

---

## Task Matrix

### Isolated Operations

Six operations covering the editing spectrum. Each is run against all three fixture files (18 combinations, minus large-section replace on small.md = 17).

| # | Operation | What it tests | Expected mdedit advantage |
|---|-----------|---------------|---------------------------|
| 1 | Replace small section (~5 lines) | Basic content substitution | Minimal — Edit tool is competitive at this size |
| 2 | Replace large section (40+ lines) | Content substitution at scale | Significant — Edit must quote all old content; mdedit addresses by name |
| 3 | Insert new section | Structural addition between existing sections | Moderate — Edit must identify exact insertion point with surrounding context |
| 4 | Delete a section | Structural removal | Significant — Edit must match full section content to remove it |
| 5 | Rename a heading | Heading text change | Minimal — simple string replacement either way |
| 6 | Multi-section update (3 sections in one prompt) | Batched editing efficiency | Moderate to significant — tests whether baseline agent does redundant reads between edits |

**Note:** Operation 2 (large section replace) is only applicable to medium.md and large.md, as small.md has no sections of sufficient size.

### Integration Workflows

Three realistic tasks that compound multiple operations. Each is run against all three fixture files (9 combinations).

#### Workflow 1: Targeted read

**Prompt:** "Read me the [specific section name] section of this document."

**Hypothesis:** The mdedit agent uses `mdedit extract "Section Name"` and receives just those lines. The baseline agent must Read the entire file and locate the section in context. Token gap widens directly with file size.

**What it tests:** Read-side efficiency. The cost of bringing a single section into context.

#### Workflow 2: Build table of contents

**Prompt:** "Build a table of contents for this document by extracting the headers, then prepend it as a nested list at the top of the document."

**Hypothesis:** The mdedit agent uses `mdedit outline` (handful of tokens) then `mdedit prepend _preamble` to write the TOC. The baseline agent must Read the entire file to discover the heading structure, then either Edit with enough surrounding context or Write the entire file back with the TOC prepended.

**What it tests:** Compound read-write efficiency. The accumulated cost of a multi-step workflow where mdedit's targeted operations avoid full-file processing.

#### Workflow 3: Edit and verify

**Prompt:** "Replace the content of the [section name] section with [new text]. Then confirm back to me what that section now contains."

**Hypothesis:** The mdedit agent does `mdedit replace` — the tool output already contains neighbourhood context proving the edit landed. Done in one tool call. The baseline agent does an Edit, then Reads the file again to confirm the section looks right before reporting back.

**What it tests:** Self-verifying output. mdedit's design principle that the LLM never needs a follow-up read to confirm an operation succeeded.

---

## Measurement

### Primary metric

**Total session tokens (input + output)** for the complete task. Captured from `claude -p --output-format json` usage stats. This includes all tool output consumed as context (e.g., mdedit's neighbourhood verification output counts as input tokens on the next turn). This is correct and desirable — the benchmark measures total cost of the workflow, including the cost of self-verifying output.

### Secondary metrics

| Metric | Purpose |
|--------|---------|
| Number of tool calls | How many steps the agent took |
| Tool call breakdown | Which tools were used and how many times each (did it Read 3 times? Fall back to Write?) |
| Wall clock time (per-run) | Execution speed of a single `claude -p` invocation. Not comparable across parallel runs due to API rate limit contention — interpret directionally only |
| Correctness | Did the task actually complete correctly? Token savings are meaningless if the edit was wrong |

### Correctness validation

Every run is validated for correctness before its token count is included in results:

**Isolated operations:** Semantic diff against expected output. The edit content must be correct and no unintended changes to other sections are permitted. Whitespace normalisation (trailing whitespace, blank line count at section boundaries) is applied before comparison — the baseline agent may produce trivially different whitespace via Edit/Write, which should not count as a failure.

**Expected outputs** are hand-authored for each operation × fixture combination and verified manually before the benchmark runs. They are not auto-generated from mdedit (that would make the comparison circular).

**Workflows:** Check structural properties rather than exact content. For example: "Does the TOC exist at the top of the file?" or "Does the section contain the expected new text?" or "Was the correct section content returned?"

Failed runs are flagged and reported separately — they tell their own story about reliability.

---

## Test Harness Architecture

Builds on the existing pattern from `tests/mdedit/run_tests.py`.

### Directory structure

```
tests/mdedit/benchmarks/
├── fixtures/
│   ├── small.md
│   ├── medium.md
│   └── large.md
├── prompts/
│   ├── system-mdedit.md          # system prompt with mdedit command reference
│   ├── system-baseline.md        # system prompt, no mdedit
│   ├── isolated/                 # one prompt file per operation
│   │   ├── replace-small.md
│   │   ├── replace-large.md
│   │   ├── insert-section.md
│   │   ├── delete-section.md
│   │   ├── rename-heading.md
│   │   └── multi-section-update.md
│   └── workflows/                # one prompt file per workflow
│       ├── targeted-read.md
│       ├── build-toc.md
│       └── edit-and-verify.md
├── expected/                     # expected outputs for isolated ops
│   ├── small/
│   ├── medium/
│   └── large/
├── results/                      # timestamped run results
├── run_benchmarks.py             # orchestrator
└── analyze.py                    # reads results, produces summary tables
```

### Runner behaviour

1. For each task × condition × file size × repetition:
   a. Copy the fixture file to a temporary directory (writes must not corrupt the original)
   b. Spawn `claude -p --output-format json` with the appropriate system prompt and task prompt
   c. Capture the full JSON output including token usage
   d. Validate correctness (diff or structural check)
   e. Write a structured result entry (JSON) to the results directory

2. **Parallelism:** Independent tasks (different file sizes, different operations) run in parallel. Same task × same file size across repetitions can also be parallelised. Keeps total wall clock time reasonable across ~270 runs.

3. **Isolation:** Each run gets a fresh temp directory with a clean copy of the fixture. No state leaks between runs.

### Analysis script

`analyze.py` reads all result entries and produces:

- Per-task summary table: mdedit min/median/max tokens vs baseline min/median/max tokens, delta, percentage savings
- Tool usage frequency table: how often each tool was used per condition
- Variance comparison: coefficient of variation for mdedit vs baseline
- Failure report: which tasks failed, on which condition, and whether Sonnet retry succeeded
- Headline summary: overall median token savings across all tasks, broken down by file size tier

---

## Expected Run Profile

| Dimension | Count |
|-----------|-------|
| Isolated operations | 17 (6 ops × 3 sizes, minus 1) |
| Integration workflows | 9 (3 workflows × 3 sizes) |
| Total task variants | 26 |
| Conditions | 2 (mdedit, baseline) |
| Repetitions | 5 |
| **Total runs** | **260** |
| Model | Haiku (Sonnet for failure retries only) |

At Haiku pricing, this should be affordable for a comprehensive benchmark.
