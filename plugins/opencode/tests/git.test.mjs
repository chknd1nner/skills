import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execSync } from "node:child_process";
import { resolveReviewTarget } from "../scripts/lib/git.mjs";
import { GitError } from "../scripts/lib/errors.mjs";

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

function makeRepo() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "oc-git-"));
  git(dir, "init -b main");
  fs.writeFileSync(path.join(dir, "file.txt"), "initial\n");
  git(dir, "add .");
  git(dir, "commit -m initial");
  return dir;
}

describe("resolveReviewTarget", () => {
  let repoDir;

  beforeEach(() => {
    repoDir = makeRepo();
  });

  afterEach(() => {
    fs.rmSync(repoDir, { recursive: true, force: true });
  });

  it("detects dirty working tree with scope auto", () => {
    fs.writeFileSync(path.join(repoDir, "new.txt"), "change\n");
    const target = resolveReviewTarget(repoDir, {});
    assert.equal(target.mode, "working-tree");
    assert.match(target.label, /working tree/);
  });

  it("throws when working tree is clean and no upstream (scope auto)", () => {
    assert.throws(
      () => resolveReviewTarget(repoDir, {}),
      GitError
    );
  });

  it("forces working-tree mode with scope flag", () => {
    fs.writeFileSync(path.join(repoDir, "new.txt"), "change\n");
    const target = resolveReviewTarget(repoDir, { scope: "working-tree" });
    assert.equal(target.mode, "working-tree");
  });

  it("uses --base to force branch mode", () => {
    // Create a second commit so we have something to diff
    fs.writeFileSync(path.join(repoDir, "file.txt"), "changed\n");
    git(repoDir, "add .");
    git(repoDir, "commit -m second");
    const firstCommit = git(repoDir, "rev-parse HEAD~1");
    const target = resolveReviewTarget(repoDir, { base: firstCommit });
    assert.equal(target.mode, "branch");
    assert.equal(target.baseRef, firstCommit);
  });

  it("throws GitError for invalid base ref", () => {
    assert.throws(
      () =>
        resolveReviewTarget(repoDir, {
          base: "nonexistent-ref",
          scope: "branch",
        }),
      GitError
    );
  });

  it("throws GitError when not in a git repo", () => {
    const noGit = fs.mkdtempSync(path.join(os.tmpdir(), "oc-nogit-"));
    try {
      assert.throws(
        () => resolveReviewTarget(noGit, {}),
        GitError
      );
    } finally {
      fs.rmSync(noGit, { recursive: true, force: true });
    }
  });

  it("branch mode falls back to main when no upstream", () => {
    fs.writeFileSync(path.join(repoDir, "file.txt"), "changed\n");
    git(repoDir, "add .");
    git(repoDir, "commit -m second");
    // No upstream set, but we have main as default branch
    // scope=branch should use HEAD~1 or the initial commit
    const target = resolveReviewTarget(repoDir, {
      scope: "branch",
      base: "HEAD~1",
    });
    assert.equal(target.mode, "branch");
  });
});
