import { execFileSync } from "node:child_process";
import { GitError } from "./errors.mjs";

function gitExec(cwd, args) {
  try {
    return execFileSync("git", args, {
      cwd,
      encoding: "utf8",
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
  } catch (err) {
    return null;
  }
}

function gitExecOrThrow(cwd, args, errorMessage) {
  const result = gitExec(cwd, args);
  if (result === null) {
    throw new GitError(errorMessage);
  }
  return result;
}

function isGitRepo(cwd) {
  return gitExec(cwd, ["rev-parse", "--is-inside-work-tree"]) === "true";
}

function isWorkingTreeDirty(cwd) {
  const status = gitExec(cwd, ["status", "--porcelain", "--untracked-files=all"]);
  return status != null && status.length > 0;
}

function countStatusItems(cwd) {
  const status = gitExec(cwd, ["status", "--porcelain", "--untracked-files=all"]) ?? "";
  if (!status) return { modified: 0, untracked: 0 };
  const lines = status.split("\n").filter(Boolean);
  let modified = 0;
  let untracked = 0;
  for (const line of lines) {
    if (line.startsWith("??")) {
      untracked++;
    } else {
      modified++;
    }
  }
  return { modified, untracked };
}

function getUpstream(cwd) {
  return gitExec(cwd, ["rev-parse", "--abbrev-ref", "HEAD@{upstream}"]);
}

function refExists(cwd, ref) {
  return gitExec(cwd, ["rev-parse", "--verify", ref]) !== null;
}

function countCommits(cwd, baseRef) {
  const result = gitExec(cwd, ["rev-list", "--count", `${baseRef}..HEAD`]);
  return result ? parseInt(result, 10) : 0;
}

function resolveDefaultBase(cwd) {
  // Try upstream first
  const upstream = getUpstream(cwd);
  if (upstream) return upstream;
  // Fall back to main/master
  if (refExists(cwd, "main")) return "main";
  if (refExists(cwd, "master")) return "master";
  return null;
}

/**
 * Resolve review target from CLI flags.
 * @param {string} cwd
 * @param {{ base?: string, scope?: string }} opts
 * @returns {{ mode: string, baseRef?: string, label: string }}
 */
export function resolveReviewTarget(cwd, { base, scope } = {}) {
  if (!isGitRepo(cwd)) {
    throw new GitError(`${cwd} is not a git repository.`, {
      suggestion: "Run /opencode:review from inside a git repo.",
    });
  }

  const effectiveScope = scope ?? "auto";
  const validScopes = ["auto", "working-tree", "branch"];
  if (!validScopes.includes(effectiveScope)) {
    throw new GitError(
      `Invalid --scope '${effectiveScope}'. Must be one of: ${validScopes.join(", ")}.`
    );
  }

  // --base implies branch mode when scope is auto
  if (base && effectiveScope === "auto") {
    return resolveBranchTarget(cwd, base);
  }

  if (effectiveScope === "working-tree") {
    if (base) {
      process.stderr.write(
        `Warning: --base is ignored when --scope is working-tree.\n`
      );
    }
    return resolveWorkingTreeTarget(cwd);
  }

  if (effectiveScope === "branch") {
    const resolvedBase = base ?? resolveDefaultBase(cwd);
    if (!resolvedBase) {
      throw new GitError(
        "No upstream branch, no 'main' or 'master' found, and no --base provided.",
        { suggestion: "Specify a base ref: /opencode:review --base <ref>" }
      );
    }
    return resolveBranchTarget(cwd, resolvedBase);
  }

  // scope === auto
  if (isWorkingTreeDirty(cwd)) {
    return resolveWorkingTreeTarget(cwd);
  }

  // Check if HEAD is ahead of upstream
  const upstream = getUpstream(cwd);
  if (upstream) {
    const ahead = countCommits(cwd, upstream);
    if (ahead > 0) {
      return resolveBranchTarget(cwd, upstream);
    }
  }

  throw new GitError(
    "Nothing to review. Working tree is clean and HEAD matches its upstream.",
    {
      suggestion:
        "Make some changes, or specify a base ref: /opencode:review --base <ref>",
    }
  );
}

function resolveWorkingTreeTarget(cwd) {
  const { modified, untracked } = countStatusItems(cwd);
  const parts = [];
  if (modified > 0) parts.push(`${modified} files modified`);
  if (untracked > 0) parts.push(`${untracked} untracked`);
  const detail = parts.length > 0 ? ` (${parts.join(", ")})` : "";
  return {
    mode: "working-tree",
    label: `working tree${detail}`,
  };
}

function resolveBranchTarget(cwd, baseRef) {
  if (!refExists(cwd, baseRef)) {
    throw new GitError(`Base ref '${baseRef}' does not exist.`, {
      suggestion: `Try: git fetch origin && /opencode:review --base ${baseRef}`,
    });
  }
  const commits = countCommits(cwd, baseRef);
  return {
    mode: "branch",
    baseRef,
    label: `HEAD\u2026${baseRef} (${commits} commit${commits === 1 ? "" : "s"})`,
  };
}
