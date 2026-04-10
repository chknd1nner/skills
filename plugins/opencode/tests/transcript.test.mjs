import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { EventEmitter } from "node:events";
import { TranscriptWriter } from "../scripts/lib/transcript.mjs";

describe("TranscriptWriter", () => {
  let tmpDir;
  const reviewId = "2026-04-09T14-32-15-487Z-a3f1";

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "oc-transcript-"));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  function makeWriter(config = {}) {
    return new TranscriptWriter({
      reviewId,
      workspaceRoot: tmpDir,
      config: {
        transcript: {
          directory: ".opencode/reviews",
          include_reasoning: false,
          ...config,
        },
      },
    });
  }

  function logPath() {
    return path.join(tmpDir, ".opencode/reviews", `${reviewId}.log.md`);
  }

  function reviewPath() {
    return path.join(tmpDir, ".opencode/reviews", `${reviewId}.review.md`);
  }

  it("creates log file with frontmatter on start()", async () => {
    const writer = makeWriter();
    const events = new EventEmitter();
    writer.attach(events);
    await writer.start({
      metadata: {
        id: reviewId,
        command: "/opencode:review",
        agent: "code-reviewer",
        sessionId: "ses_1",
        workspace: tmpDir,
        target: "working tree",
        startedAt: "2026-04-09T14:32:15Z",
        status: "running",
      },
    });
    assert.ok(fs.existsSync(logPath()), "log file should exist");
    assert.ok(!fs.existsSync(reviewPath()), "review file should NOT exist yet");
    const content = fs.readFileSync(logPath(), "utf8");
    assert.ok(content.startsWith("---\n"), "should have frontmatter");
    assert.ok(content.includes("status: running"), "should have running status");
    assert.ok(content.includes("# Opencode Review"), "should have header");
  });

  it("appends tool call markers on events", async () => {
    const writer = makeWriter();
    const events = new EventEmitter();
    writer.attach(events);
    await writer.start({
      metadata: {
        id: reviewId, command: "/opencode:review", agent: "x",
        sessionId: "s", workspace: tmpDir, target: "t",
        startedAt: "2026-04-09T14:32:15Z", status: "running",
      },
    });
    events.emit("tool-start", { tool: "read", input: "src/main.ts" });
    events.emit("phase", { label: "thinking" });
    // Give fs.appendFile a moment
    await new Promise((r) => setTimeout(r, 50));
    const content = fs.readFileSync(logPath(), "utf8");
    assert.ok(content.includes("● Read(`src/main.ts`)"), "should have tool marker");
    assert.ok(content.includes("_Thinking\u2026_"), "should have thinking marker");
  });

  it("finish() creates review file on success", async () => {
    const writer = makeWriter();
    const events = new EventEmitter();
    writer.attach(events);
    await writer.start({
      metadata: {
        id: reviewId, command: "/opencode:review", agent: "x",
        sessionId: "s", workspace: tmpDir, target: "t",
        startedAt: "2026-04-09T14:32:15Z", status: "running",
      },
    });
    await writer.finish({
      finalReviewText: "# Code Review\n\nLooks good.",
      status: "completed",
      duration: "1m 30s",
      toolCount: 5,
      completedAt: "2026-04-09T14:33:45Z",
    });
    assert.ok(fs.existsSync(reviewPath()), "review file should exist");
    const review = fs.readFileSync(reviewPath(), "utf8");
    assert.ok(review.includes("# Code Review"), "should have review text");
    assert.ok(review.includes("status: completed"), "should have completed status");
    const log = fs.readFileSync(logPath(), "utf8");
    assert.ok(log.includes("status: completed"), "log frontmatter should be updated");
    assert.ok(log.includes("## Final Review"), "log should have final review section");
    assert.ok(log.includes("Looks good."), "log should have review text");
  });

  it("finish() does NOT create review file on error", async () => {
    const writer = makeWriter();
    const events = new EventEmitter();
    writer.attach(events);
    await writer.start({
      metadata: {
        id: reviewId, command: "/opencode:review", agent: "x",
        sessionId: "s", workspace: tmpDir, target: "t",
        startedAt: "2026-04-09T14:32:15Z", status: "running",
      },
    });
    await writer.finish({
      finalReviewText: "",
      status: "error",
      duration: "0m 30s",
      toolCount: 2,
      completedAt: "2026-04-09T14:32:45Z",
      errorMessage: "Connection dropped",
    });
    assert.ok(!fs.existsSync(reviewPath()), "review file should NOT exist");
    const log = fs.readFileSync(logPath(), "utf8");
    assert.ok(log.includes("status: error"), "log should have error status");
    assert.ok(log.includes("## Error"), "log should have error section");
    assert.ok(log.includes("Connection dropped"), "log should have error message");
  });

  it("includes reasoning when include_reasoning is true", async () => {
    const writer = makeWriter({ include_reasoning: true });
    const events = new EventEmitter();
    writer.attach(events);
    await writer.start({
      metadata: {
        id: reviewId, command: "/opencode:review", agent: "x",
        sessionId: "s", workspace: tmpDir, target: "t",
        startedAt: "2026-04-09T14:32:15Z", status: "running",
      },
    });
    events.emit("reasoning", { text: "I need to check the auth module." });
    await new Promise((r) => setTimeout(r, 50));
    const content = fs.readFileSync(logPath(), "utf8");
    assert.ok(content.includes("> I need to check the auth module."), "should include reasoning");
  });
});
