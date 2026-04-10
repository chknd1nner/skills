import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execSync, spawn } from "node:child_process";
import { startFakeServer } from "../fixtures/fake-opencode-server.mjs";

import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMPANION = path.resolve(
  __dirname,
  "../../scripts/opencode-companion.mjs"
);

function git(cwd, cmd) {
  return execSync(`git ${cmd}`, {
    cwd,
    encoding: "utf8",
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: "Test",
      GIT_AUTHOR_EMAIL: "test@test.com",
      GIT_COMMITTER_NAME: "Test",
      GIT_COMMITTER_EMAIL: "test@test.com",
    },
  }).trim();
}

/**
 * Spawn the companion script asynchronously (non-blocking), so the parent
 * process event loop stays alive to handle HTTP requests from the child.
 * execFileSync would block the event loop and starve the fake HTTP server.
 */
function runCompanion(args, { cwd, env, timeout = 15000 }) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [COMPANION, ...args], {
      cwd,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));

    const timer = setTimeout(() => {
      child.kill();
      reject(new Error("Companion timed out"));
    }, timeout);

    child.on("exit", (code, signal) => {
      clearTimeout(timer);
      if (code === 0) {
        resolve({ stdout, stderr, status: 0 });
      } else {
        const err = Object.assign(new Error(`Companion exited ${code}`), {
          stdout,
          stderr,
          status: code,
          signal,
        });
        reject(err);
      }
    });
  });
}

describe("review flow (integration)", () => {
  let server;
  let repoDir;
  let configPath;

  beforeEach(() => {
    // Create a temp git repo with a dirty working tree
    repoDir = fs.mkdtempSync(path.join(os.tmpdir(), "oc-review-"));
    git(repoDir, "init -b main");
    fs.writeFileSync(path.join(repoDir, "file.txt"), "initial\n");
    git(repoDir, "add .");
    git(repoDir, "commit -m initial");
    fs.writeFileSync(path.join(repoDir, "file.txt"), "modified\n");
  });

  afterEach(async () => {
    if (server) await server.close();
    fs.rmSync(repoDir, { recursive: true, force: true });
  });

  it("runs a successful foreground review", async () => {
    server = await startFakeServer({
      events: [
        {
          delayMs: 5,
          type: "message.part.updated",
          properties: {
            sessionID: "ses_test123",
            part: {
              type: "tool",
              tool: "read",
              state: { status: "running", input: { filePath: "file.txt" } },
            },
          },
        },
        {
          delayMs: 5,
          type: "message.part.updated",
          properties: {
            sessionID: "ses_test123",
            part: {
              type: "tool",
              tool: "read",
              state: { status: "completed", input: { filePath: "file.txt" } },
            },
          },
        },
        {
          delayMs: 5,
          type: "session.idle",
          properties: { sessionID: "ses_test123" },
        },
      ],
    });

    // Write a temp config pointing at the fake server
    configPath = path.join(repoDir, "test-config.toml");
    fs.writeFileSync(
      configPath,
      `
[server]
url = "${server.url}"

[commands.review]
agent = "code-reviewer"

[transcript]
directory = ".opencode/reviews"
include_reasoning = false
`
    );

    const { stdout } = await runCompanion(
      ["review", "--scope", "working-tree", "--json"],
      {
        cwd: repoDir,
        env: {
          ...process.env,
          OPENCODE_PLUGIN_CONFIG: configPath,
        },
        timeout: 15000,
      }
    );

    const parsed = JSON.parse(stdout);
    assert.equal(parsed.status, "completed");
    assert.ok(parsed.reviewId);
    assert.ok(parsed.finalReviewText.includes("Review output."));

    // Verify transcript files were created
    const reviewsDir = path.join(repoDir, ".opencode/reviews");
    const files = fs.readdirSync(reviewsDir);
    const logFile = files.find((f) => f.endsWith(".log.md"));
    const reviewFile = files.find((f) => f.endsWith(".review.md"));
    assert.ok(logFile, "log file should exist");
    assert.ok(reviewFile, "review file should exist");

    const logContent = fs.readFileSync(
      path.join(reviewsDir, logFile),
      "utf8"
    );
    assert.ok(logContent.includes("status: completed"));
    assert.ok(logContent.includes("## Final Review"));
  });

  it("prints friendly error when server is unreachable", async () => {
    configPath = path.join(repoDir, "test-config.toml");
    fs.writeFileSync(
      configPath,
      `
[server]
url = "http://127.0.0.1:1"

[commands.review]
agent = "code-reviewer"

[transcript]
directory = ".opencode/reviews"
include_reasoning = false
`
    );

    try {
      await runCompanion(["review", "--scope", "working-tree"], {
        cwd: repoDir,
        env: {
          ...process.env,
          OPENCODE_PLUGIN_CONFIG: configPath,
        },
        timeout: 10000,
      });
      assert.fail("Should have thrown");
    } catch (err) {
      assert.equal(err.status, 1);
      assert.ok(
        err.stderr.includes("opencode serve"),
        "should suggest starting the server"
      );
    }
  });

  it("handles empty response body (bad agent name)", async () => {
    server = await startFakeServer({
      message: { emptyBody: true },
      events: [],
    });

    configPath = path.join(repoDir, "test-config.toml");
    fs.writeFileSync(
      configPath,
      `
[server]
url = "${server.url}"

[commands.review]
agent = "nonexistent-agent"

[transcript]
directory = ".opencode/reviews"
include_reasoning = false
`
    );

    try {
      await runCompanion(["review", "--scope", "working-tree"], {
        cwd: repoDir,
        env: {
          ...process.env,
          OPENCODE_PLUGIN_CONFIG: configPath,
        },
        timeout: 10000,
      });
      assert.fail("Should have thrown");
    } catch (err) {
      assert.equal(err.status, 1);
      assert.ok(
        err.stderr.includes("unknown agent"),
        "should mention unknown agent"
      );
    }
  });
});
