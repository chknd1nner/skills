import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { buildReviewPrompt } from "../scripts/lib/prompts.mjs";

describe("buildReviewPrompt", () => {
  it("builds a working-tree prompt", () => {
    const target = { mode: "working-tree", label: "working tree (3 files modified)" };
    const result = buildReviewPrompt(target, "/Users/test/myproject");
    assert.ok(result.includes("/Users/test/myproject"));
    assert.ok(result.includes("working-tree"));
    assert.ok(result.includes("git status --short"));
    assert.ok(!result.includes("BASE_REF"));
    assert.ok(result.includes("working tree (3 files modified)"));
  });

  it("builds a branch prompt with base ref", () => {
    const target = {
      mode: "branch",
      baseRef: "origin/main",
      label: "HEAD…origin/main (5 commits)",
    };
    const result = buildReviewPrompt(target, "/tmp/repo");
    assert.ok(result.includes("/tmp/repo"));
    assert.ok(result.includes("branch"));
    assert.ok(result.includes("origin/main"));
    assert.ok(result.includes("git log --oneline origin/main..HEAD"));
    assert.ok(!result.includes("git status --short"));
  });

  it("includes the review output format instructions", () => {
    const target = { mode: "working-tree", label: "working tree" };
    const result = buildReviewPrompt(target, "/tmp");
    assert.ok(result.includes("## Output format"));
    assert.ok(result.includes("## Constraints"));
  });
});
