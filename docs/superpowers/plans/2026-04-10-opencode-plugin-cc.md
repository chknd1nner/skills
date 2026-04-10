# Opencode Plugin for Claude Code — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Claude Code plugin at `plugins/opencode/` that dispatches code reviews to a user-managed Opencode server via `/opencode:review`.

**Architecture:** Single companion script (`opencode-companion.mjs`) with subcommand dispatch, mirroring the Codex plugin shape. Seven library modules under `scripts/lib/` handle config, HTTP, SSE, rendering, transcripts, args, and git. Two SKILL.md files expose `/opencode:review` and `/opencode:setup` as user-invokable slash commands.

**Tech Stack:** Node.js 20+ (ESM, no build step), `smol-toml` (only runtime dependency), `node:test` (built-in test runner)

**Spec:** `docs/superpowers/specs/2026-04-09-opencode-plugin-cc-design.md`

---

### Task 1: Project scaffold + error classes

**Files:**
- Create: `plugins/opencode/.claude-plugin/plugin.json`
- Create: `plugins/opencode/package.json`
- Create: `plugins/opencode/scripts/lib/errors.mjs`
- Create: `plugins/opencode/tests/errors.test.mjs`

This task creates the directory tree, installs the single runtime dependency, and defines the error class hierarchy that every other module imports.

- [ ] **Step 1: Create directory structure**

```bash
cd /Users/martinkuek/Documents/Projects/skills
mkdir -p plugins/opencode/.claude-plugin
mkdir -p plugins/opencode/skills/review
mkdir -p plugins/opencode/skills/setup
mkdir -p plugins/opencode/scripts/lib
mkdir -p plugins/opencode/prompts
mkdir -p plugins/opencode/tests/fixtures
mkdir -p plugins/opencode/tests/integration
```

- [ ] **Step 2: Create plugin manifest**

Create `plugins/opencode/.claude-plugin/plugin.json`:

```json
{
  "name": "opencode",
  "version": "0.1.0",
  "description": "Dispatch code reviews and tasks to a running Opencode server.",
  "author": {
    "name": "Martin Kuek"
  },
  "license": "MIT"
}
```

- [ ] **Step 3: Create package.json**

Create `plugins/opencode/package.json`:

```json
{
  "name": "opencode-plugin-cc",
  "version": "0.1.0",
  "type": "module",
  "description": "Claude Code plugin for dispatching reviews to Opencode server",
  "license": "MIT",
  "engines": {
    "node": ">=20.0.0"
  },
  "scripts": {
    "test": "node --test tests/**/*.test.mjs tests/integration/**/*.test.mjs"
  },
  "dependencies": {
    "smol-toml": "^1.3.1"
  }
}
```

- [ ] **Step 4: Install dependencies**

Run: `cd plugins/opencode && npm install`

- [ ] **Step 5: Write failing test for error classes**

Create `plugins/opencode/tests/errors.test.mjs`:

```javascript
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  OpencodePluginError,
  ConfigError,
  CliArgumentError,
  GitError,
  OpencodeUnreachableError,
  OpencodeApiError,
  OpencodeResponseError,
} from "../scripts/lib/errors.mjs";

describe("error classes", () => {
  it("OpencodePluginError has default exitCode 1", () => {
    const err = new OpencodePluginError("test");
    assert.equal(err.message, "test");
    assert.equal(err.exitCode, 1);
    assert.equal(err.suggestion, undefined);
    assert.ok(err instanceof Error);
  });

  it("OpencodePluginError accepts suggestion", () => {
    const err = new OpencodePluginError("msg", { suggestion: "try X" });
    assert.equal(err.suggestion, "try X");
  });

  it("ConfigError has exitCode 2", () => {
    const err = new ConfigError("bad config");
    assert.equal(err.exitCode, 2);
    assert.ok(err instanceof OpencodePluginError);
  });

  it("CliArgumentError has exitCode 2", () => {
    const err = new CliArgumentError("bad arg");
    assert.equal(err.exitCode, 2);
    assert.ok(err instanceof OpencodePluginError);
  });

  it("GitError has exitCode 1", () => {
    const err = new GitError("not a repo");
    assert.equal(err.exitCode, 1);
    assert.ok(err instanceof OpencodePluginError);
  });

  it("OpencodeUnreachableError has exitCode 1", () => {
    const err = new OpencodeUnreachableError("can't connect", {
      suggestion: "run opencode serve",
    });
    assert.equal(err.exitCode, 1);
    assert.equal(err.suggestion, "run opencode serve");
    assert.ok(err instanceof OpencodePluginError);
  });

  it("OpencodeApiError has exitCode 1", () => {
    const err = new OpencodeApiError("500");
    assert.equal(err.exitCode, 1);
    assert.ok(err instanceof OpencodePluginError);
  });

  it("OpencodeResponseError has exitCode 1", () => {
    const err = new OpencodeResponseError("empty body");
    assert.equal(err.exitCode, 1);
    assert.ok(err instanceof OpencodePluginError);
  });
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd plugins/opencode && node --test tests/errors.test.mjs`
Expected: FAIL — `Cannot find module '../scripts/lib/errors.mjs'`

- [ ] **Step 7: Implement error classes**

Create `plugins/opencode/scripts/lib/errors.mjs`:

```javascript
export class OpencodePluginError extends Error {
  constructor(message, { exitCode = 1, suggestion } = {}) {
    super(message);
    this.name = this.constructor.name;
    this.exitCode = exitCode;
    this.suggestion = suggestion;
  }
}

export class ConfigError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 2, ...opts });
  }
}

export class CliArgumentError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 2, ...opts });
  }
}

export class GitError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 1, ...opts });
  }
}

export class OpencodeUnreachableError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 1, ...opts });
  }
}

export class OpencodeApiError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 1, ...opts });
  }
}

export class OpencodeResponseError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 1, ...opts });
  }
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd plugins/opencode && node --test tests/errors.test.mjs`
Expected: All 7 tests PASS

- [ ] **Step 9: Commit**

```bash
cd /Users/martinkuek/Documents/Projects/skills
git add plugins/opencode
git commit -m "feat(opencode): scaffold plugin directory and error class hierarchy"
```

---

### Task 2: lib/args.mjs — CLI argument parser

**Files:**
- Create: `plugins/opencode/scripts/lib/args.mjs`
- Create: `plugins/opencode/tests/args.test.mjs`

Pure utility, no dependencies beyond errors.mjs. Parses argv against a schema of value options, boolean options, and aliases.

- [ ] **Step 1: Write failing test**

Create `plugins/opencode/tests/args.test.mjs`:

```javascript
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseArgs } from "../scripts/lib/args.mjs";

describe("parseArgs", () => {
  it("parses value options", () => {
    const { options } = parseArgs(["--base", "origin/main"], {
      valueOptions: ["base"],
    });
    assert.equal(options.base, "origin/main");
  });

  it("parses boolean options", () => {
    const { options } = parseArgs(["--json"], {
      booleanOptions: ["json"],
    });
    assert.equal(options.json, true);
  });

  it("absent booleans are false", () => {
    const { options } = parseArgs([], { booleanOptions: ["json"] });
    assert.equal(options.json, false);
  });

  it("collects positionals", () => {
    const { positionals } = parseArgs(["hello", "world"], {});
    assert.deepEqual(positionals, ["hello", "world"]);
  });

  it("resolves aliases", () => {
    const { options } = parseArgs(["-m", "gpt-5"], {
      valueOptions: ["model"],
      aliasMap: { m: "model" },
    });
    assert.equal(options.model, "gpt-5");
  });

  it("handles -- end-of-options", () => {
    const { options, positionals } = parseArgs(
      ["--json", "--", "--base", "foo"],
      { booleanOptions: ["json"], valueOptions: ["base"] }
    );
    assert.equal(options.json, true);
    assert.equal(options.base, undefined);
    assert.deepEqual(positionals, ["--base", "foo"]);
  });

  it("mixes options and positionals", () => {
    const { options, positionals } = parseArgs(
      ["--scope", "branch", "extra"],
      { valueOptions: ["scope"] }
    );
    assert.equal(options.scope, "branch");
    assert.deepEqual(positionals, ["extra"]);
  });

  it("handles value option missing its value at end of argv", () => {
    assert.throws(
      () => parseArgs(["--base"], { valueOptions: ["base"] }),
      /requires a value/
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/opencode && node --test tests/args.test.mjs`
Expected: FAIL — `Cannot find module`

- [ ] **Step 3: Implement args.mjs**

Create `plugins/opencode/scripts/lib/args.mjs`:

```javascript
import { CliArgumentError } from "./errors.mjs";

/**
 * Parse argv against a schema.
 * @param {string[]} argv
 * @param {{ valueOptions?: string[], booleanOptions?: string[], aliasMap?: Record<string,string> }} schema
 * @returns {{ options: Record<string, string|boolean>, positionals: string[] }}
 */
export function parseArgs(argv, schema = {}) {
  const valueSet = new Set(schema.valueOptions ?? []);
  const boolSet = new Set(schema.booleanOptions ?? []);
  const aliases = schema.aliasMap ?? {};

  const options = {};
  const positionals = [];
  let endOfOptions = false;

  // Initialize booleans to false
  for (const key of boolSet) {
    options[key] = false;
  }

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];

    if (endOfOptions) {
      positionals.push(arg);
      continue;
    }

    if (arg === "--") {
      endOfOptions = true;
      continue;
    }

    // Long option: --name or --name value
    if (arg.startsWith("--")) {
      const name = arg.slice(2);
      if (boolSet.has(name)) {
        options[name] = true;
      } else if (valueSet.has(name)) {
        if (i + 1 >= argv.length) {
          throw new CliArgumentError(`Option '--${name}' requires a value.`);
        }
        options[name] = argv[++i];
      } else {
        positionals.push(arg);
      }
      continue;
    }

    // Short option: -x (single char, resolved via alias)
    if (arg.startsWith("-") && arg.length === 2) {
      const short = arg[1];
      const resolved = aliases[short];
      if (resolved && boolSet.has(resolved)) {
        options[resolved] = true;
      } else if (resolved && valueSet.has(resolved)) {
        if (i + 1 >= argv.length) {
          throw new CliArgumentError(
            `Option '-${short}' (--${resolved}) requires a value.`
          );
        }
        options[resolved] = argv[++i];
      } else {
        positionals.push(arg);
      }
      continue;
    }

    positionals.push(arg);
  }

  return { options, positionals };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/opencode && node --test tests/args.test.mjs`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/opencode/scripts/lib/args.mjs plugins/opencode/tests/args.test.mjs
git commit -m "feat(opencode): add CLI argument parser"
```

---

### Task 3: lib/config.mjs — TOML loading + schema validation

**Files:**
- Create: `plugins/opencode/scripts/lib/config.mjs`
- Create: `plugins/opencode/tests/config.test.mjs`

Loads user-global TOML config, validates schema, merges with hardcoded defaults and CLI overrides. Uses `smol-toml` for parsing.

- [ ] **Step 1: Write failing test**

Create `plugins/opencode/tests/config.test.mjs`:

```javascript
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import {
  loadConfig,
  ensureDefaultConfig,
  DEFAULTS,
} from "../scripts/lib/config.mjs";
import { ConfigError } from "../scripts/lib/errors.mjs";

describe("config", () => {
  let tmpDir;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "oc-config-"));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("returns defaults when config file is missing", () => {
    const config = loadConfig({
      configPath: path.join(tmpDir, "nonexistent.toml"),
    });
    assert.equal(config.server.url, DEFAULTS.server.url);
    assert.equal(config.commands.review.agent, DEFAULTS.commands.review.agent);
    assert.equal(config.transcript.include_reasoning, false);
  });

  it("parses a valid TOML config", () => {
    const toml = `
[server]
url = "http://localhost:9999"

[commands.review]
agent = "my-reviewer"
provider = "anthropic"
model = "claude-sonnet-4.6"

[transcript]
directory = ".reviews"
include_reasoning = true
`;
    const cfgPath = path.join(tmpDir, "config.toml");
    fs.writeFileSync(cfgPath, toml);
    const config = loadConfig({ configPath: cfgPath });
    assert.equal(config.server.url, "http://localhost:9999");
    assert.equal(config.commands.review.agent, "my-reviewer");
    assert.equal(config.commands.review.provider, "anthropic");
    assert.equal(config.commands.review.model, "claude-sonnet-4.6");
    assert.equal(config.transcript.directory, ".reviews");
    assert.equal(config.transcript.include_reasoning, true);
  });

  it("CLI overrides take precedence", () => {
    const toml = `
[server]
url = "http://localhost:4096"

[commands.review]
agent = "code-reviewer"

[transcript]
directory = ".opencode/reviews"
include_reasoning = false
`;
    const cfgPath = path.join(tmpDir, "config.toml");
    fs.writeFileSync(cfgPath, toml);
    const config = loadConfig({
      configPath: cfgPath,
      overrides: { commands: { review: { agent: "custom-agent" } } },
    });
    assert.equal(config.commands.review.agent, "custom-agent");
    assert.equal(config.server.url, "http://localhost:4096");
  });

  it("throws ConfigError for invalid URL", () => {
    const toml = `
[server]
url = "not-a-url"
[commands.review]
agent = "x"
[transcript]
directory = ".reviews"
include_reasoning = false
`;
    const cfgPath = path.join(tmpDir, "config.toml");
    fs.writeFileSync(cfgPath, toml);
    assert.throws(() => loadConfig({ configPath: cfgPath }), ConfigError);
  });

  it("throws ConfigError when provider set without model", () => {
    const toml = `
[server]
url = "http://localhost:4096"
[commands.review]
agent = "x"
provider = "poe"
[transcript]
directory = ".reviews"
include_reasoning = false
`;
    const cfgPath = path.join(tmpDir, "config.toml");
    fs.writeFileSync(cfgPath, toml);
    assert.throws(
      () => loadConfig({ configPath: cfgPath }),
      /provider.*model.*both or neither/i
    );
  });

  it("throws ConfigError for absolute transcript directory", () => {
    const toml = `
[server]
url = "http://localhost:4096"
[commands.review]
agent = "x"
[transcript]
directory = "/absolute/path"
include_reasoning = false
`;
    const cfgPath = path.join(tmpDir, "config.toml");
    fs.writeFileSync(cfgPath, toml);
    assert.throws(
      () => loadConfig({ configPath: cfgPath }),
      /relative path/i
    );
  });

  it("ensureDefaultConfig creates file if missing", () => {
    const cfgPath = path.join(tmpDir, "sub", "config.toml");
    const result = ensureDefaultConfig(cfgPath);
    assert.equal(result.created, true);
    assert.ok(fs.existsSync(cfgPath));
    // Should be parseable
    const config = loadConfig({ configPath: cfgPath });
    assert.equal(config.server.url, DEFAULTS.server.url);
  });

  it("ensureDefaultConfig is no-op if file exists", () => {
    const cfgPath = path.join(tmpDir, "config.toml");
    fs.writeFileSync(cfgPath, "[server]\nurl = \"http://localhost:1234\"\n");
    const result = ensureDefaultConfig(cfgPath);
    assert.equal(result.created, false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/opencode && node --test tests/config.test.mjs`
Expected: FAIL — `Cannot find module`

- [ ] **Step 3: Implement config.mjs**

Create `plugins/opencode/scripts/lib/config.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { parse as parseTOML } from "smol-toml";
import { ConfigError } from "./errors.mjs";

export const DEFAULTS = {
  server: {
    url: "http://localhost:4096",
    password: null,
  },
  commands: {
    review: {
      agent: "code-reviewer",
      provider: null,
      model: null,
    },
  },
  transcript: {
    directory: ".opencode/reviews",
    include_reasoning: false,
  },
};

const DEFAULT_CONFIG_PATH = path.join(
  os.homedir(),
  ".config",
  "opencode-plugin",
  "config.toml"
);

const DEFAULT_TEMPLATE = `# Opencode Plugin Configuration
# Start your opencode server separately: opencode serve

[server]
url = "http://localhost:4096"
# password = "your-password-here"

[commands.review]
agent    = "code-reviewer"
# provider = "poe"
# model    = "openai/gpt-5.4"

[transcript]
directory         = ".opencode/reviews"
include_reasoning = false
`;

function deepMerge(target, source) {
  const result = { ...target };
  for (const key of Object.keys(source)) {
    if (source[key] === undefined || source[key] === null) continue;
    if (
      typeof source[key] === "object" &&
      !Array.isArray(source[key]) &&
      typeof target[key] === "object" &&
      !Array.isArray(target[key])
    ) {
      result[key] = deepMerge(target[key] ?? {}, source[key]);
    } else {
      result[key] = source[key];
    }
  }
  return result;
}

function validate(config) {
  // server.url must be a valid URL
  try {
    new URL(config.server.url);
  } catch {
    throw new ConfigError(
      `config: 'server.url' is not a valid URL: '${config.server.url}'.`
    );
  }

  // commands.review.agent must be non-empty
  if (!config.commands?.review?.agent) {
    throw new ConfigError(
      "config: 'commands.review.agent' is required. Set it under [commands.review]."
    );
  }

  // provider and model are a pair
  const rev = config.commands.review;
  const hasProvider = rev.provider != null && rev.provider !== "";
  const hasModel = rev.model != null && rev.model !== "";
  if (hasProvider !== hasModel) {
    throw new ConfigError(
      "config: 'commands.review.provider' and 'commands.review.model' must be set both or neither."
    );
  }

  // transcript.directory must be relative
  const dir = config.transcript?.directory;
  if (dir && (path.isAbsolute(dir) || dir.includes(".."))) {
    throw new ConfigError(
      `config: 'transcript.directory' must be a relative path, got '${dir}'.`
    );
  }

  // transcript.include_reasoning must be boolean
  if (typeof config.transcript?.include_reasoning !== "boolean") {
    throw new ConfigError(
      "config: 'transcript.include_reasoning' must be a boolean."
    );
  }

  return config;
}

/**
 * Load and validate the TOML config, merge with defaults and overrides.
 * @param {{ configPath?: string, overrides?: object }} opts
 * @returns {object} Fully resolved config
 */
export function loadConfig({ configPath, overrides } = {}) {
  const cfgPath =
    configPath ??
    process.env.OPENCODE_PLUGIN_CONFIG ??
    DEFAULT_CONFIG_PATH;

  let fileConfig = {};
  try {
    const raw = fs.readFileSync(cfgPath, "utf8");
    fileConfig = parseTOML(raw);
  } catch (err) {
    if (err.code === "ENOENT") {
      // File missing — use defaults only
    } else if (err.line != null) {
      throw new ConfigError(
        `Failed to parse ${cfgPath} at line ${err.line}: ${err.message}`
      );
    } else {
      throw new ConfigError(`Failed to read ${cfgPath}: ${err.message}`);
    }
  }

  // Three-layer merge: defaults ← TOML file ← CLI overrides
  let merged = deepMerge(DEFAULTS, fileConfig);
  if (overrides) {
    merged = deepMerge(merged, overrides);
  }

  return validate(merged);
}

/**
 * Create the default config file if it doesn't exist.
 * @param {string} [cfgPath]
 * @returns {{ created: boolean, path: string }}
 */
export function ensureDefaultConfig(cfgPath) {
  const target = cfgPath ?? DEFAULT_CONFIG_PATH;
  if (fs.existsSync(target)) {
    return { created: false, path: target };
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, DEFAULT_TEMPLATE, "utf8");
  return { created: true, path: target };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/opencode && node --test tests/config.test.mjs`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/opencode/scripts/lib/config.mjs plugins/opencode/tests/config.test.mjs
git commit -m "feat(opencode): add TOML config loading with schema validation"
```

---

### Task 4: lib/git.mjs — review target resolution

**Files:**
- Create: `plugins/opencode/scripts/lib/git.mjs`
- Create: `plugins/opencode/tests/git.test.mjs`

Resolves `--base` and `--scope` flags into a ReviewTarget object. Uses real git repos in tmpdir for testing.

- [ ] **Step 1: Write failing test**

Create `plugins/opencode/tests/git.test.mjs`:

```javascript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/opencode && node --test tests/git.test.mjs`
Expected: FAIL — `Cannot find module`

- [ ] **Step 3: Implement git.mjs**

Create `plugins/opencode/scripts/lib/git.mjs`:

```javascript
import { execSync } from "node:child_process";
import { GitError } from "./errors.mjs";

function gitExec(cwd, cmd) {
  try {
    return execSync(`git ${cmd}`, {
      cwd,
      encoding: "utf8",
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
  } catch (err) {
    return null;
  }
}

function gitExecOrThrow(cwd, cmd, errorMessage) {
  const result = gitExec(cwd, cmd);
  if (result === null) {
    throw new GitError(errorMessage);
  }
  return result;
}

function isGitRepo(cwd) {
  return gitExec(cwd, "rev-parse --is-inside-work-tree") === "true";
}

function isWorkingTreeDirty(cwd) {
  const status = gitExec(cwd, "status --porcelain --untracked-files=all");
  return status != null && status.length > 0;
}

function countStatusItems(cwd) {
  const status = gitExec(cwd, "status --porcelain --untracked-files=all") ?? "";
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
  return gitExec(cwd, "rev-parse --abbrev-ref HEAD@{upstream}");
}

function refExists(cwd, ref) {
  return gitExec(cwd, `rev-parse --verify ${ref}`) !== null;
}

function countCommits(cwd, baseRef) {
  const result = gitExec(cwd, `rev-list --count ${baseRef}..HEAD`);
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

  // --base implies branch mode when scope is auto
  if (base && effectiveScope === "auto") {
    return resolveBranchTarget(cwd, base);
  }

  if (effectiveScope === "working-tree") {
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/opencode && node --test tests/git.test.mjs`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/opencode/scripts/lib/git.mjs plugins/opencode/tests/git.test.mjs
git commit -m "feat(opencode): add git target resolution for --base and --scope"
```

---

### Task 5: Fake Opencode server test fixture

**Files:**
- Create: `plugins/opencode/tests/fixtures/fake-opencode-server.mjs`

In-process HTTP server with configurable handlers. Needed by Task 6 (client tests) and Task 13 (integration tests).

- [ ] **Step 1: Implement the fake server**

Create `plugins/opencode/tests/fixtures/fake-opencode-server.mjs`:

```javascript
import http from "node:http";

/**
 * Start a fake Opencode server for testing.
 *
 * @param {object} opts
 * @param {object} [opts.health]          Response for GET /global/health
 * @param {object} [opts.session]         Response for POST /session
 * @param {object} [opts.message]         Config for POST /session/:id/message
 * @param {object[]} [opts.events]        SSE events to emit for GET /global/event
 * @param {number} [opts.authStatus]      If set, return this status for missing/bad auth
 * @param {string} [opts.password]        Expected bearer token
 * @returns {Promise<{ url: string, port: number, requests: object[], close: () => Promise<void> }>}
 */
export async function startFakeServer(opts = {}) {
  const requests = [];

  const health = opts.health ?? { healthy: true, version: "fake" };
  const session = opts.session ?? { id: "ses_test123" };
  const message = opts.message ?? {
    delayMs: 10,
    response: {
      info: { finish: "stop" },
      parts: [{ type: "text", text: "Review output." }],
    },
  };
  const events = opts.events ?? [];
  const password = opts.password ?? null;

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://localhost`);
    const method = req.method;
    const pathname = url.pathname;

    // Collect body for POST
    let body = "";
    if (method === "POST") {
      for await (const chunk of req) body += chunk;
    }

    requests.push({ method, pathname, query: url.search, body, headers: { ...req.headers } });

    // Auth check
    if (password) {
      const authHeader = req.headers.authorization;
      if (authHeader !== `Bearer ${password}`) {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Unauthorized" }));
        return;
      }
    }

    // Route: GET /global/health
    if (method === "GET" && pathname === "/global/health") {
      if (opts.healthStatus) {
        res.writeHead(opts.healthStatus);
        res.end();
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(health));
      return;
    }

    // Route: POST /session
    if (method === "POST" && pathname === "/session") {
      if (opts.sessionStatus) {
        res.writeHead(opts.sessionStatus);
        res.end(opts.sessionBody ?? "");
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(session));
      return;
    }

    // Route: POST /session/:id/message
    if (method === "POST" && pathname.match(/^\/session\/[^/]+\/message$/)) {
      if (message.status) {
        res.writeHead(message.status);
        res.end(message.body ?? "");
        return;
      }
      if (message.emptyBody) {
        res.writeHead(200, { "Content-Length": "0" });
        res.end();
        return;
      }
      await new Promise((r) => setTimeout(r, message.delayMs ?? 10));
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(message.response));
      return;
    }

    // Route: GET /global/event (SSE)
    if (method === "GET" && pathname === "/global/event") {
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      });

      for (const event of events) {
        await new Promise((r) => setTimeout(r, event.delayMs ?? 10));
        const payload = {
          payload: {
            type: event.type,
            properties: event.properties ?? {},
          },
        };
        res.write(`data: ${JSON.stringify(payload)}\n\n`);
      }

      // Keep the connection open until client disconnects
      req.on("close", () => {
        res.end();
      });
      return;
    }

    res.writeHead(404);
    res.end("Not found");
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;

  return {
    url: `http://127.0.0.1:${port}`,
    port,
    requests,
    close: () =>
      new Promise((resolve) => {
        server.closeAllConnections();
        server.close(resolve);
      }),
  };
}
```

- [ ] **Step 2: Quick smoke test**

Run a quick inline test to verify the fixture works:

```bash
cd plugins/opencode && node -e "
import { startFakeServer } from './tests/fixtures/fake-opencode-server.mjs';
const s = await startFakeServer();
const r = await fetch(s.url + '/global/health');
const j = await r.json();
console.log('health:', j.healthy === true ? 'OK' : 'FAIL');
await s.close();
console.log('closed OK');
"
```

Expected: `health: OK` and `closed OK`

- [ ] **Step 3: Commit**

```bash
git add plugins/opencode/tests/fixtures/fake-opencode-server.mjs
git commit -m "test(opencode): add fake Opencode server fixture for integration tests"
```

---

### Task 6: lib/client.mjs — HTTP client

**Files:**
- Create: `plugins/opencode/scripts/lib/client.mjs`
- Create: `plugins/opencode/tests/integration/client.test.mjs`

Thin wrapper over `fetch` for `healthCheck`, `createSession`, `sendMessage`. Tests run against the fake server fixture from Task 5.

- [ ] **Step 1: Write failing test**

Create `plugins/opencode/tests/integration/client.test.mjs`:

```javascript
import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import { startFakeServer } from "../fixtures/fake-opencode-server.mjs";
import {
  healthCheck,
  createSession,
  sendMessage,
} from "../../scripts/lib/client.mjs";
import {
  OpencodeUnreachableError,
  OpencodeApiError,
  OpencodeResponseError,
} from "../../scripts/lib/errors.mjs";

describe("client", () => {
  let server;

  afterEach(async () => {
    if (server) await server.close();
  });

  describe("healthCheck", () => {
    it("returns healthy status", async () => {
      server = await startFakeServer();
      const config = { server: { url: server.url } };
      const result = await healthCheck(config);
      assert.equal(result.healthy, true);
    });

    it("returns unhealthy on 500", async () => {
      server = await startFakeServer({ healthStatus: 500 });
      const config = { server: { url: server.url } };
      const result = await healthCheck(config);
      assert.equal(result.healthy, false);
    });

    it("returns unhealthy on connection refused", async () => {
      const config = { server: { url: "http://127.0.0.1:1" } };
      const result = await healthCheck(config);
      assert.equal(result.healthy, false);
    });
  });

  describe("createSession", () => {
    it("returns session id", async () => {
      server = await startFakeServer();
      const config = { server: { url: server.url } };
      const result = await createSession(config, {
        directory: "/tmp/test-project",
      });
      assert.equal(result.id, "ses_test123");
      // Verify directory query param was sent
      assert.ok(
        server.requests.some(
          (r) =>
            r.pathname === "/session" &&
            r.query.includes("directory=%2Ftmp%2Ftest-project")
        )
      );
    });

    it("forwards bearer token", async () => {
      server = await startFakeServer({ password: "secret123" });
      const config = { server: { url: server.url, password: "secret123" } };
      const result = await createSession(config, { directory: "/tmp" });
      assert.equal(result.id, "ses_test123");
    });

    it("throws OpencodeApiError on 401", async () => {
      server = await startFakeServer({ password: "secret" });
      const config = { server: { url: server.url, password: "wrong" } };
      await assert.rejects(
        () => createSession(config, { directory: "/tmp" }),
        OpencodeApiError
      );
    });
  });

  describe("sendMessage", () => {
    it("returns response on success", async () => {
      server = await startFakeServer();
      const config = { server: { url: server.url } };
      const result = await sendMessage(config, "ses_test123", {
        directory: "/tmp",
        prompt: "Review this",
        agent: "code-reviewer",
      });
      assert.equal(result.info.finish, "stop");
      assert.equal(result.parts[0].text, "Review output.");
    });

    it("sends model as object when provided", async () => {
      server = await startFakeServer();
      const config = { server: { url: server.url } };
      await sendMessage(config, "ses_test123", {
        directory: "/tmp",
        prompt: "Review",
        agent: "code-reviewer",
        model: { providerID: "poe", modelID: "openai/gpt-5.4" },
      });
      const msgReq = server.requests.find((r) =>
        r.pathname.includes("/message")
      );
      const body = JSON.parse(msgReq.body);
      assert.deepEqual(body.model, {
        providerID: "poe",
        modelID: "openai/gpt-5.4",
      });
    });

    it("throws OpencodeResponseError on empty body", async () => {
      server = await startFakeServer({
        message: { emptyBody: true },
      });
      const config = { server: { url: server.url } };
      await assert.rejects(
        () =>
          sendMessage(config, "ses_test123", {
            directory: "/tmp",
            prompt: "test",
            agent: "bad-agent",
          }),
        OpencodeResponseError
      );
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/opencode && node --test tests/integration/client.test.mjs`
Expected: FAIL — `Cannot find module`

- [ ] **Step 3: Implement client.mjs**

Create `plugins/opencode/scripts/lib/client.mjs`:

```javascript
import {
  OpencodeUnreachableError,
  OpencodeApiError,
  OpencodeResponseError,
} from "./errors.mjs";

function buildHeaders(config) {
  const headers = { "Content-Type": "application/json" };
  if (config.server.password) {
    headers["Authorization"] = `Bearer ${config.server.password}`;
  }
  return headers;
}

function withDirectory(baseUrl, directory) {
  const url = new URL(baseUrl);
  if (directory) {
    url.searchParams.set("directory", directory);
  }
  return url.toString();
}

/**
 * Check if the Opencode server is healthy.
 * Never throws — returns { healthy: false } on any failure.
 */
export async function healthCheck(config) {
  try {
    const url = `${config.server.url}/global/health`;
    const res = await fetch(url, {
      headers: buildHeaders(config),
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return { healthy: false };
    const body = await res.json();
    return { healthy: body.healthy === true, version: body.version };
  } catch {
    return { healthy: false };
  }
}

/**
 * Create a new session scoped to a directory.
 */
export async function createSession(config, { directory }) {
  const url = withDirectory(`${config.server.url}/session`, directory);
  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: buildHeaders(config),
      body: JSON.stringify({}),
    });
  } catch (err) {
    throw new OpencodeUnreachableError(
      `Can't reach Opencode at ${config.server.url}.`,
      {
        suggestion: `Start the server in another terminal:\n  opencode serve`,
      }
    );
  }

  if (res.status === 401) {
    throw new OpencodeApiError(
      `Opencode returned 401 Unauthorized.`,
      {
        suggestion: `Set [server].password in ~/.config/opencode-plugin/config.toml.`,
      }
    );
  }

  if (!res.ok) {
    throw new OpencodeApiError(
      `Opencode failed to create a session: HTTP ${res.status}.`,
      { suggestion: "Check 'opencode serve' logs." }
    );
  }

  return await res.json();
}

/**
 * Send a message to a session (blocking POST).
 */
export async function sendMessage(
  config,
  sessionId,
  { directory, prompt, agent, model, signal }
) {
  const url = withDirectory(
    `${config.server.url}/session/${sessionId}/message`,
    directory
  );

  const body = {
    agent,
    parts: [{ type: "text", text: prompt }],
  };
  if (model) {
    body.model = model;
  }

  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: buildHeaders(config),
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new OpencodeApiError(
      `Connection to Opencode dropped: ${err.message}`,
      {
        suggestion: "Check your network and 'opencode serve' status.",
      }
    );
  }

  if (res.status === 401) {
    throw new OpencodeApiError(`Opencode returned 401 Unauthorized.`, {
      suggestion: `Set [server].password in ~/.config/opencode-plugin/config.toml.`,
    });
  }

  if (!res.ok) {
    throw new OpencodeApiError(
      `Opencode returned HTTP ${res.status} for message.`,
      { suggestion: "Check 'opencode serve' logs." }
    );
  }

  // Empty body = likely unknown agent name
  const text = await res.text();
  if (!text || text.length === 0) {
    throw new OpencodeResponseError(
      `Opencode returned an empty response (likely an unknown agent name '${agent}').`,
      {
        suggestion:
          "Check that the agent exists in your Opencode config.",
      }
    );
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new OpencodeResponseError(
      `Opencode returned invalid JSON: ${text.slice(0, 200)}`,
      {
        suggestion: "Check 'opencode serve' logs.",
      }
    );
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/opencode && node --test tests/integration/client.test.mjs`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/opencode/scripts/lib/client.mjs plugins/opencode/tests/integration/client.test.mjs
git commit -m "feat(opencode): add HTTP client for Opencode server API"
```

---

### Task 7: lib/events.mjs — SSE subscriber + event interpreter

**Files:**
- Create: `plugins/opencode/scripts/lib/events.mjs`
- Create: `plugins/opencode/tests/events.test.mjs`

The most complex module. Subscribes to SSE, parses chunk-to-line, interprets Opencode events into semantic events. Test with canned SSE data — no network needed for unit tests.

- [ ] **Step 1: Write failing test**

Create `plugins/opencode/tests/events.test.mjs`:

```javascript
import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import { EventStream, parseSSEMessage, interpretEvent } from "../scripts/lib/events.mjs";
import { startFakeServer } from "./fixtures/fake-opencode-server.mjs";

describe("parseSSEMessage", () => {
  it("extracts data from single-line SSE", () => {
    const result = parseSSEMessage('data: {"hello":"world"}');
    assert.deepEqual(result, { hello: "world" });
  });

  it("concatenates multi-line data fields", () => {
    const result = parseSSEMessage('data: {"a":\ndata: "b"}');
    assert.deepEqual(result, { a: "b" });
  });

  it("returns null for non-data messages", () => {
    assert.equal(parseSSEMessage("event: ping"), null);
    assert.equal(parseSSEMessage(": comment"), null);
  });

  it("returns null for malformed JSON", () => {
    assert.equal(parseSSEMessage("data: {broken"), null);
  });
});

describe("interpretEvent", () => {
  it("interprets tool running as tool-start + phase", () => {
    const events = [];
    interpretEvent(
      {
        payload: {
          type: "message.part.updated",
          properties: {
            sessionID: "ses_1",
            part: {
              type: "tool",
              tool: "read",
              state: {
                status: "running",
                input: { filePath: "src/main.ts" },
              },
            },
          },
        },
      },
      "ses_1",
      { include_reasoning: false },
      (name, data) => events.push({ name, data })
    );
    assert.equal(events.length, 2);
    assert.equal(events[0].name, "tool-start");
    assert.equal(events[0].data.tool, "read");
    assert.equal(events[1].name, "phase");
    assert.equal(events[1].data.label, "reading");
  });

  it("interprets tool completed as tool-end", () => {
    const events = [];
    let toolCount = 3;
    interpretEvent(
      {
        payload: {
          type: "message.part.updated",
          properties: {
            sessionID: "ses_1",
            part: {
              type: "tool",
              tool: "bash",
              state: { status: "completed", input: { command: "ls" } },
            },
          },
        },
      },
      "ses_1",
      { include_reasoning: false },
      (name, data) => events.push({ name, data }),
      () => ++toolCount
    );
    assert.equal(events[0].name, "tool-end");
    assert.equal(toolCount, 4);
  });

  it("filters out events for other sessions", () => {
    const events = [];
    interpretEvent(
      {
        payload: {
          type: "session.idle",
          properties: { sessionID: "other_session" },
        },
      },
      "ses_1",
      {},
      (name, data) => events.push({ name, data })
    );
    assert.equal(events.length, 0);
  });

  it("emits done on session.idle", () => {
    const events = [];
    interpretEvent(
      {
        payload: {
          type: "session.idle",
          properties: { sessionID: "ses_1" },
        },
      },
      "ses_1",
      {},
      (name, data) => events.push({ name, data })
    );
    assert.equal(events[0].name, "done");
  });

  it("emits phase thinking + optional reasoning text", () => {
    const events = [];
    interpretEvent(
      {
        payload: {
          type: "message.part.updated",
          properties: {
            sessionID: "ses_1",
            part: { type: "reasoning", text: "Let me think..." },
          },
        },
      },
      "ses_1",
      { include_reasoning: true },
      (name, data) => events.push({ name, data })
    );
    assert.equal(events[0].name, "phase");
    assert.equal(events[0].data.label, "thinking");
    assert.equal(events[1].name, "reasoning");
    assert.equal(events[1].data.text, "Let me think...");
  });

  it("suppresses reasoning text when include_reasoning is false", () => {
    const events = [];
    interpretEvent(
      {
        payload: {
          type: "message.part.updated",
          properties: {
            sessionID: "ses_1",
            part: { type: "reasoning", text: "secret" },
          },
        },
      },
      "ses_1",
      { include_reasoning: false },
      (name, data) => events.push({ name, data })
    );
    assert.equal(events.length, 1);
    assert.equal(events[0].name, "phase");
  });

  it("emits text-delta and writing phase on first text", () => {
    const events = [];
    const state = { sawFirstText: false };
    interpretEvent(
      {
        payload: {
          type: "message.part.updated",
          properties: {
            sessionID: "ses_1",
            part: { type: "text", text: "Hello" },
            delta: "Hello",
          },
        },
      },
      "ses_1",
      {},
      (name, data) => events.push({ name, data }),
      null,
      state
    );
    assert.equal(events[0].name, "phase");
    assert.equal(events[0].data.label, "writing");
    assert.equal(events[1].name, "text-delta");
    assert.equal(events[1].data.text, "Hello");
  });

  it("derives phase labels from tool names", () => {
    const toolPhases = [
      ["read", "reading"],
      ["bash", "running"],
      ["grep", "searching"],
      ["write", "working"],
    ];
    for (const [tool, expected] of toolPhases) {
      const events = [];
      interpretEvent(
        {
          payload: {
            type: "message.part.updated",
            properties: {
              sessionID: "s",
              part: { type: "tool", tool, state: { status: "running", input: {} } },
            },
          },
        },
        "s",
        {},
        (name, data) => events.push({ name, data })
      );
      const phase = events.find((e) => e.name === "phase");
      assert.equal(phase.data.label, expected, `tool '${tool}' should map to '${expected}'`);
    }
  });
});

describe("EventStream integration", () => {
  let server;

  afterEach(async () => {
    if (server) await server.close();
  });

  it("emits events from a real SSE stream", async () => {
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
              state: { status: "running", input: { filePath: "a.ts" } },
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
              state: { status: "completed", input: { filePath: "a.ts" } },
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

    const config = {
      server: { url: server.url },
      transcript: { include_reasoning: false },
    };
    const stream = new EventStream(config, "ses_test123");
    const collected = [];
    stream.on("tool-start", (d) => collected.push({ name: "tool-start", ...d }));
    stream.on("tool-end", (d) => collected.push({ name: "tool-end", ...d }));
    stream.on("done", () => collected.push({ name: "done" }));

    await stream.start();
    await stream.waitForDone({ timeoutMs: 3000 });
    await stream.stop();

    assert.ok(collected.some((e) => e.name === "tool-start"));
    assert.ok(collected.some((e) => e.name === "tool-end"));
    assert.ok(collected.some((e) => e.name === "done"));
    assert.equal(stream.toolCount, 1);
    assert.equal(stream.isDone, true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/opencode && node --test tests/events.test.mjs`
Expected: FAIL — `Cannot find module`

- [ ] **Step 3: Implement events.mjs**

Create `plugins/opencode/scripts/lib/events.mjs`:

```javascript
import { EventEmitter } from "node:events";
import { OpencodeApiError } from "./errors.mjs";

const TOOL_PHASE_MAP = {
  read: "reading",
  bash: "running",
  grep: "searching",
};

/**
 * Parse a single SSE message (the text between blank-line delimiters).
 * Returns parsed JSON or null.
 */
export function parseSSEMessage(raw) {
  const lines = raw.split("\n");
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  try {
    return JSON.parse(dataLines.join(""));
  } catch {
    return null;
  }
}

/**
 * Interpret a single parsed SSE event and call `emit` for each semantic event.
 * Exported for unit testing without a live stream.
 */
export function interpretEvent(
  event,
  sessionId,
  transcriptConfig,
  emit,
  incrementToolCount,
  textState
) {
  const payload = event?.payload;
  if (!payload) return;

  const props = payload.properties ?? {};
  if (props.sessionID && props.sessionID !== sessionId) return;

  const type = payload.type;

  if (type === "session.idle") {
    emit("done", {});
    return;
  }

  if (type === "session.error") {
    emit("error", { error: props.error ?? "Unknown server error" });
    return;
  }

  if (type === "message.part.updated") {
    const part = props.part;
    if (!part) return;

    if (part.type === "tool") {
      const state = part.state ?? {};
      const tool = part.tool ?? "unknown";
      const input = state.input ?? {};
      const primaryArg =
        input.filePath ?? input.command ?? input.pattern ?? "";

      if (state.status === "running" || state.status === "pending") {
        emit("tool-start", { tool, input: primaryArg, callId: props.callID });
        const label = TOOL_PHASE_MAP[tool] ?? "working";
        emit("phase", { label, detail: primaryArg });
      } else if (state.status === "completed") {
        if (incrementToolCount) incrementToolCount();
        emit("tool-end", { tool, callId: props.callID });
      }
      return;
    }

    if (part.type === "reasoning") {
      emit("phase", { label: "thinking" });
      if (transcriptConfig?.include_reasoning && part.text) {
        emit("reasoning", { text: part.text });
      }
      return;
    }

    if (part.type === "text") {
      const delta = props.delta ?? part.text ?? "";
      if (delta) {
        if (textState && !textState.sawFirstText) {
          textState.sawFirstText = true;
          emit("phase", { label: "writing" });
        }
        emit("text-delta", { text: delta });
      }
      return;
    }
  }
}

export class EventStream extends EventEmitter {
  #config;
  #sessionId;
  #abortController;
  #toolCount = 0;
  #isDone = false;
  #donePromise;
  #doneResolve;
  #readerPromise;

  constructor(config, sessionId) {
    super();
    this.#config = config;
    this.#sessionId = sessionId;
    this.#abortController = new AbortController();
    this.#donePromise = new Promise((resolve) => {
      this.#doneResolve = resolve;
    });
  }

  get toolCount() {
    return this.#toolCount;
  }

  get isDone() {
    return this.#isDone;
  }

  async start() {
    const url = `${this.#config.server.url}/global/event`;
    const headers = {};
    if (this.#config.server.password) {
      headers["Authorization"] = `Bearer ${this.#config.server.password}`;
    }

    let response;
    try {
      response = await fetch(url, {
        headers,
        signal: this.#abortController.signal,
      });
    } catch (err) {
      if (err.name === "AbortError") return;
      throw new OpencodeApiError(
        `Failed to connect to SSE stream at ${url}: ${err.message}`
      );
    }

    if (!response.ok) {
      throw new OpencodeApiError(
        `SSE stream returned HTTP ${response.status}`
      );
    }

    // Detach the reader into a background task
    this.#readerPromise = this.#readStream(response).catch(() => {});
  }

  async stop() {
    this.#abortController.abort();
    if (this.#readerPromise) {
      await this.#readerPromise;
    }
  }

  async waitForDone({ timeoutMs = 2000 } = {}) {
    if (this.#isDone) return;
    await Promise.race([
      this.#donePromise,
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("waitForDone timeout")), timeoutMs)
      ),
    ]);
  }

  async #readStream(response) {
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    const textState = { sawFirstText: false };

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += value;

        let sepIdx;
        while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
          const rawMessage = buffer.slice(0, sepIdx);
          buffer = buffer.slice(sepIdx + 2);
          this.#dispatch(rawMessage, textState);
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        this.emit("error", { error: err.message });
      }
    } finally {
      // Flush remaining buffer
      if (buffer.trim()) {
        this.#dispatch(buffer, textState);
      }
      reader.releaseLock();
    }
  }

  #dispatch(rawMessage, textState) {
    const parsed = parseSSEMessage(rawMessage);
    if (!parsed) return;

    interpretEvent(
      parsed,
      this.#sessionId,
      this.#config.transcript,
      (name, data) => {
        if (name === "done") {
          this.#isDone = true;
          this.#doneResolve();
        }
        this.emit(name, data);
      },
      () => this.#toolCount++,
      textState
    );
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/opencode && node --test tests/events.test.mjs`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/opencode/scripts/lib/events.mjs plugins/opencode/tests/events.test.mjs
git commit -m "feat(opencode): add SSE subscriber and event interpreter"
```

---

### Task 8: lib/render.mjs — live status footer

**Files:**
- Create: `plugins/opencode/scripts/lib/render.mjs`
- Create: `plugins/opencode/tests/render.test.mjs`

Maintains a one-line status footer on stderr with spinner, activity label, tool counter, and elapsed timer. Tests use a writable buffer stream to capture output.

- [ ] **Step 1: Write failing test**

Create `plugins/opencode/tests/render.test.mjs`:

```javascript
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { Writable } from "node:stream";
import { EventEmitter } from "node:events";
import { StatusRenderer, formatElapsed } from "../scripts/lib/render.mjs";

describe("formatElapsed", () => {
  it("formats seconds under a minute", () => {
    assert.equal(formatElapsed(5000), "0:05");
    assert.equal(formatElapsed(45000), "0:45");
  });

  it("formats minutes and seconds", () => {
    assert.equal(formatElapsed(125000), "2:05");
    assert.equal(formatElapsed(600000), "10:00");
  });

  it("formats hours", () => {
    assert.equal(formatElapsed(3661000), "1h01m");
    assert.equal(formatElapsed(7200000), "2h00m");
  });
});

describe("StatusRenderer", () => {
  function makeBufferStream() {
    const chunks = [];
    const stream = new Writable({
      write(chunk, _enc, cb) {
        chunks.push(chunk.toString());
        cb();
      },
    });
    stream.isTTY = true;
    return { stream, chunks };
  }

  it("renders footer on tick after phase event", () => {
    const { stream, chunks } = makeBufferStream();
    const events = new EventEmitter();
    const renderer = new StatusRenderer({ stream, tickMs: 50 });
    renderer.attach(events);
    renderer.start();

    events.emit("phase", { label: "reading", detail: "src/main.ts" });
    events.emit("tool-end", { toolCount: 1 });

    // Wait for a tick
    return new Promise((resolve) => {
      setTimeout(() => {
        renderer.stop();
        const output = chunks.join("");
        assert.ok(output.includes("Opencode reviewing"), "should contain review label");
        assert.ok(output.includes("Reading"), "should contain activity label");
        resolve();
      }, 100);
    });
  });

  it("renders plain lines in non-TTY mode", () => {
    const { stream, chunks } = makeBufferStream();
    stream.isTTY = false;
    const events = new EventEmitter();
    const renderer = new StatusRenderer({ stream, tickMs: 50 });
    renderer.attach(events);
    renderer.start();

    events.emit("phase", { label: "thinking" });

    return new Promise((resolve) => {
      setTimeout(() => {
        renderer.stop();
        const output = chunks.join("");
        // Non-TTY should NOT contain ANSI escape codes
        assert.ok(!output.includes("\x1b[2K"), "should not contain ANSI clear");
        resolve();
      }, 100);
    });
  });

  it("stop clears the footer in TTY mode", () => {
    const { stream, chunks } = makeBufferStream();
    const events = new EventEmitter();
    const renderer = new StatusRenderer({ stream, tickMs: 50 });
    renderer.attach(events);
    renderer.start();
    renderer.stop();
    const output = chunks.join("");
    // Should end with a clear sequence
    assert.ok(output.endsWith("\r\x1b[2K") || output === "", "should clear on stop");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/opencode && node --test tests/render.test.mjs`
Expected: FAIL — `Cannot find module`

- [ ] **Step 3: Implement render.mjs**

Create `plugins/opencode/scripts/lib/render.mjs`:

```javascript
const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

export function formatElapsed(ms) {
  const totalSec = Math.floor(ms / 1000);
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;

  if (hours > 0) {
    return `${hours}h${String(minutes).padStart(2, "0")}m`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function capitalize(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

export class StatusRenderer {
  #stream;
  #tickMs;
  #interval = null;
  #spinnerIdx = 0;
  #startTime = null;
  #activity = "Starting up\u2026";
  #toolCount = 0;
  #isTTY;
  #lastPhaseLabel = null;

  constructor({ stream = process.stderr, tickMs = 250 } = {}) {
    this.#stream = stream;
    this.#tickMs = tickMs;
    this.#isTTY = stream.isTTY === true;
  }

  attach(eventStream) {
    eventStream.on("phase", ({ label, detail }) => {
      this.#lastPhaseLabel = label;
      const desc = capitalize(label);
      this.#activity = detail ? `${desc} ${detail}` : `${desc}\u2026`;
      if (!this.#isTTY) {
        this.#emitLogLine();
      }
    });

    eventStream.on("tool-end", () => {
      this.#toolCount++;
    });
  }

  start() {
    this.#startTime = Date.now();
    this.#interval = setInterval(() => this.#tick(), this.#tickMs);
  }

  stop() {
    if (this.#interval) {
      clearInterval(this.#interval);
      this.#interval = null;
    }
    if (this.#isTTY) {
      this.#stream.write("\r\x1b[2K");
    }
  }

  #tick() {
    if (!this.#isTTY) return;
    this.#spinnerIdx = (this.#spinnerIdx + 1) % SPINNER_FRAMES.length;
    const spinner = SPINNER_FRAMES[this.#spinnerIdx];
    const elapsed = formatElapsed(Date.now() - this.#startTime);
    const line = `${spinner} Opencode reviewing \u00b7 ${this.#activity} \u00b7 Tool calls: ${this.#toolCount} \u00b7 ${elapsed}`;
    this.#stream.write(`\r\x1b[2K${line}`);
  }

  #emitLogLine() {
    const elapsed = this.#startTime ? formatElapsed(Date.now() - this.#startTime) : "0:00";
    this.#stream.write(`[${elapsed}] ${this.#activity} (tool calls: ${this.#toolCount})\n`);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/opencode && node --test tests/render.test.mjs`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/opencode/scripts/lib/render.mjs plugins/opencode/tests/render.test.mjs
git commit -m "feat(opencode): add live status footer renderer with TTY/non-TTY modes"
```

---

### Task 9: lib/transcript.mjs — log + review file writers

**Files:**
- Create: `plugins/opencode/scripts/lib/transcript.mjs`
- Create: `plugins/opencode/tests/transcript.test.mjs`

Writes `{id}.log.md` incrementally and `{id}.review.md` on successful finish. Atomic frontmatter rewrite at `finish()`.

- [ ] **Step 1: Write failing test**

Create `plugins/opencode/tests/transcript.test.mjs`:

```javascript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/opencode && node --test tests/transcript.test.mjs`
Expected: FAIL — `Cannot find module`

- [ ] **Step 3: Implement transcript.mjs**

Create `plugins/opencode/scripts/lib/transcript.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";

function capitalize(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

function buildFrontmatter(meta) {
  const lines = ["---"];
  for (const [key, value] of Object.entries(meta)) {
    if (value === null || value === undefined) {
      lines.push(`${key}: null`);
    } else if (typeof value === "number") {
      lines.push(`${key}: ${value}`);
    } else {
      lines.push(`${key}: ${value}`);
    }
  }
  lines.push("---\n");
  return lines.join("\n");
}

function rewriteFrontmatter(filePath, updates) {
  const content = fs.readFileSync(filePath, "utf8");
  const endIdx = content.indexOf("---\n", 4);
  if (endIdx === -1) return;
  const frontmatter = content.slice(4, endIdx);
  let newFM = frontmatter;
  for (const [key, value] of Object.entries(updates)) {
    const regex = new RegExp(`^${key}:.*$`, "m");
    const replacement =
      value === null ? `${key}: null` : `${key}: ${value}`;
    if (regex.test(newFM)) {
      newFM = newFM.replace(regex, replacement);
    } else {
      newFM += `${replacement}\n`;
    }
  }
  const rest = content.slice(endIdx);
  const updated = `---\n${newFM}${rest}`;
  const tmpPath = filePath + ".tmp";
  fs.writeFileSync(tmpPath, updated, "utf8");
  fs.renameSync(tmpPath, filePath);
}

export class TranscriptWriter {
  #reviewId;
  #workspaceRoot;
  #config;
  #logPath;
  #reviewFilePath;
  #metadata;

  constructor({ reviewId, workspaceRoot, config }) {
    this.#reviewId = reviewId;
    this.#workspaceRoot = workspaceRoot;
    this.#config = config;
    const dir = path.join(workspaceRoot, config.transcript.directory);
    this.#logPath = path.join(dir, `${reviewId}.log.md`);
    this.#reviewFilePath = path.join(dir, `${reviewId}.review.md`);
  }

  attach(eventStream) {
    eventStream.on("tool-start", ({ tool, input }) => {
      const line = `\n● ${capitalize(tool)}(\`${input}\`)\n  \u23BF (output hidden)\n`;
      this.#append(line);
    });

    eventStream.on("phase", ({ label }) => {
      if (label === "thinking") {
        this.#append("\n_Thinking\u2026_\n");
      } else if (label === "writing") {
        this.#append("\n_Writing report\u2026_\n\n");
      }
    });

    eventStream.on("text-delta", ({ text }) => {
      this.#append(text);
    });

    if (this.#config.transcript.include_reasoning) {
      eventStream.on("reasoning", ({ text }) => {
        this.#append(`\n> ${text.replace(/\n/g, "\n> ")}\n`);
      });
    }
  }

  async start({ metadata }) {
    this.#metadata = metadata;
    const dir = path.dirname(this.#logPath);
    fs.mkdirSync(dir, { recursive: true });

    const fm = buildFrontmatter({
      id: metadata.id,
      command: metadata.command,
      agent: metadata.agent,
      provider: metadata.provider ?? null,
      model: metadata.model ?? null,
      session_id: metadata.sessionId,
      workspace: metadata.workspace,
      target: metadata.target,
      status: "running",
      started_at: metadata.startedAt,
      completed_at: null,
      duration: null,
      tool_calls: 0,
    });

    const header = `\n# Opencode Review \u2014 ${metadata.startedAt.split("T")[0]}\n\n`;
    fs.writeFileSync(this.#logPath, fm + header, "utf8");
  }

  async finish({ finalReviewText, status, duration, toolCount, completedAt, errorMessage }) {
    // Append final review section to log
    if (finalReviewText) {
      this.#append(`\n\n## Final Review\n\n${finalReviewText}\n`);
    }

    // Append error section if non-completed
    if (status !== "completed" && errorMessage) {
      this.#append(`\n\n## Error\n\n${errorMessage}\n`);
    }

    // Rewrite frontmatter in log file
    rewriteFrontmatter(this.#logPath, {
      status,
      completed_at: completedAt,
      duration,
      tool_calls: toolCount,
    });

    // Only create review file on success
    if (status === "completed" && finalReviewText) {
      const fm = buildFrontmatter({
        id: this.#reviewId,
        command: this.#metadata.command,
        agent: this.#metadata.agent,
        provider: this.#metadata.provider ?? null,
        model: this.#metadata.model ?? null,
        status: "completed",
        duration,
      });
      fs.writeFileSync(
        this.#reviewFilePath,
        fm + `\n${finalReviewText}\n`,
        "utf8"
      );
    }
  }

  #append(text) {
    try {
      fs.appendFileSync(this.#logPath, text, "utf8");
    } catch {
      // Silently ignore write failures (e.g. if the log was deleted mid-review)
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/opencode && node --test tests/transcript.test.mjs`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/opencode/scripts/lib/transcript.mjs plugins/opencode/tests/transcript.test.mjs
git commit -m "feat(opencode): add transcript writer with incremental log and atomic frontmatter"
```

---

### Task 10: Prompt template + builder

**Files:**
- Create: `plugins/opencode/prompts/review.md`
- Create: `plugins/opencode/scripts/lib/prompts.mjs`
- Create: `plugins/opencode/tests/prompts.test.mjs`

The review prompt template and the interpolation helper.

- [ ] **Step 1: Write failing test**

Create `plugins/opencode/tests/prompts.test.mjs`:

```javascript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/opencode && node --test tests/prompts.test.mjs`
Expected: FAIL — `Cannot find module`

- [ ] **Step 3: Create the prompt template**

Create `plugins/opencode/prompts/review.md` — the full template from §5.7.1 of the spec:

```markdown
You are performing a code review on a project at `{{WORKSPACE}}`.

## Review target

**Mode:** {{TARGET_MODE}}
{{WORKING_TREE_SECTION}}
{{BRANCH_SECTION}}

**Review label:** {{TARGET_LABEL}}

## What to do

1. Use your Bash, Read, and Grep tools to inspect the code under review.
2. For each issue you find, look at the surrounding code via additional Read calls so your review reflects the broader context, not just the changed lines.
3. Group findings by severity: **Critical** (bugs, security, data loss), **High** (correctness, performance, design flaws), **Medium** (maintainability, testability), **Low** (style, naming, documentation).
4. For each finding, cite the file and line number using the form `path/to/file.ts:42`.
5. Be specific about the *fix*. Don't say "consider X" — say what to change and why.

## Output format

Return your review as Markdown with these sections, in order:

```
# Code Review

## Summary
<2-3 sentence high-level assessment>

## Findings

### Critical
- **`path/to/file.ts:42`** — <one-line title>
  <Multi-paragraph explanation of the issue and the fix>

### High
...

### Medium
...

### Low
...

## What's good
<Brief positive observations — what the change does well>

## Recommendation
<Approve / Approve with changes / Request changes — and why>
```

## Constraints

- Review only the target scope above. Do not make broader recommendations about the codebase.
- Do not modify any files. This is a read-only review.
- If a finding requires running code or tests to verify, note that explicitly rather than guessing.
- If the target scope is empty (no actual changes), say so and stop — do not invent issues.
```

- [ ] **Step 4: Implement prompts.mjs**

Create `plugins/opencode/scripts/lib/prompts.mjs`:

```javascript
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TEMPLATE_DIR = path.resolve(__dirname, "../../prompts");

const WORKING_TREE_SECTION = `**Scope:** All uncommitted changes — staged, unstaged, and untracked files.

To enumerate the changes, run from \`{{WORKSPACE}}\`:
- \`git status --short --untracked-files=all\`
- \`git diff --cached\`  (staged changes)
- \`git diff\`           (unstaged changes)
- For untracked files, read each one directly with your Read tool.`;

const BRANCH_SECTION = `**Scope:** Commits between \`{{BASE_REF}}\` and \`HEAD\`.

To enumerate the changes, run from \`{{WORKSPACE}}\`:
- \`git log --oneline {{BASE_REF}}..HEAD\`
- \`git diff {{BASE_REF}}...HEAD --stat\`
- \`git diff {{BASE_REF}}...HEAD\`  (full diff if you need it; use --name-only first to scope)`;

/**
 * Build the review prompt by interpolating the template.
 * @param {{ mode: string, baseRef?: string, label: string }} target
 * @param {string} cwd
 * @returns {string}
 */
export function buildReviewPrompt(target, cwd) {
  let template = fs.readFileSync(
    path.join(TEMPLATE_DIR, "review.md"),
    "utf8"
  );

  // Conditional sections
  if (target.mode === "working-tree") {
    template = template.replace(
      "{{WORKING_TREE_SECTION}}",
      WORKING_TREE_SECTION
    );
    template = template.replace("{{BRANCH_SECTION}}", "");
  } else {
    template = template.replace("{{WORKING_TREE_SECTION}}", "");
    template = template.replace("{{BRANCH_SECTION}}", BRANCH_SECTION);
  }

  // Simple variable interpolation
  template = template.replaceAll("{{WORKSPACE}}", cwd);
  template = template.replaceAll("{{TARGET_MODE}}", target.mode);
  template = template.replaceAll("{{TARGET_LABEL}}", target.label);
  if (target.baseRef) {
    template = template.replaceAll("{{BASE_REF}}", target.baseRef);
  }

  // Clean up any remaining empty lines from removed sections
  template = template.replace(/\n{3,}/g, "\n\n");

  return template;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd plugins/opencode && node --test tests/prompts.test.mjs`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add plugins/opencode/prompts/review.md plugins/opencode/scripts/lib/prompts.mjs plugins/opencode/tests/prompts.test.mjs
git commit -m "feat(opencode): add review prompt template and interpolation builder"
```

---

### Task 11: opencode-companion.mjs — dispatcher + handlers

**Files:**
- Create: `plugins/opencode/scripts/opencode-companion.mjs`

The main entry point. Contains `main()`, `handleSetup()`, `handleReview()`, `executeReviewRun()`, `makeReviewId()`, and `formatDuration()`. This is composition code — it ties all the lib modules together. No separate unit tests here; the integration test in Task 13 covers the composed behavior.

- [ ] **Step 1: Implement the dispatcher and handlers**

Create `plugins/opencode/scripts/opencode-companion.mjs`:

```javascript
#!/usr/bin/env node

import crypto from "node:crypto";
import process from "node:process";

import { parseArgs } from "./lib/args.mjs";
import { loadConfig, ensureDefaultConfig } from "./lib/config.mjs";
import { healthCheck, createSession, sendMessage } from "./lib/client.mjs";
import { resolveReviewTarget } from "./lib/git.mjs";
import { EventStream } from "./lib/events.mjs";
import { StatusRenderer } from "./lib/render.mjs";
import { TranscriptWriter } from "./lib/transcript.mjs";
import { buildReviewPrompt } from "./lib/prompts.mjs";
import {
  OpencodePluginError,
  OpencodeUnreachableError,
  OpencodeApiError,
  OpencodeResponseError,
} from "./lib/errors.mjs";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeReviewId() {
  const now = new Date();
  const ts = now.toISOString().replace(/:/g, "-").replace(/\.\d+Z$/, "");
  const ms = String(now.getMilliseconds()).padStart(3, "0");
  const rand = crypto.randomBytes(2).toString("hex");
  return `${ts}-${ms}Z-${rand}`;
}

function formatDuration(ms) {
  const totalSec = Math.floor(ms / 1000);
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  }
  return `${seconds}s`;
}

function printUsage() {
  console.log(
    [
      "Usage:",
      "  opencode-companion.mjs setup",
      "  opencode-companion.mjs review [--base <ref>] [--scope auto|working-tree|branch] [--model <spec>] [--agent <name>] [--json]",
    ].join("\n")
  );
}

// ---------------------------------------------------------------------------
// handleSetup
// ---------------------------------------------------------------------------

async function handleSetup(argv) {
  const { options } = parseArgs(argv, { booleanOptions: ["json"] });

  // Ensure config file exists
  const { created, path: cfgPath } = ensureDefaultConfig();

  // Load config (validates it)
  let config;
  let configValid = true;
  let configError = null;
  try {
    config = loadConfig();
  } catch (err) {
    configValid = false;
    configError = err.message;
    config = null;
  }

  // Health check
  let serverHealthy = false;
  let serverVersion = null;
  if (config) {
    const health = await healthCheck(config);
    serverHealthy = health.healthy;
    serverVersion = health.version ?? null;
  }

  const report = {
    configFile: {
      path: cfgPath,
      created,
      valid: configValid,
      error: configError,
    },
    server: {
      url: config?.server?.url ?? "(unknown — config invalid)",
      healthy: serverHealthy,
      version: serverVersion,
    },
  };

  if (options.json) {
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    return;
  }

  // Human-readable output
  const lines = [];
  lines.push("Opencode Plugin Setup");
  lines.push("=====================\n");

  // Config file
  if (created) {
    lines.push(`Config:  Created default at ${cfgPath}`);
  } else if (configValid) {
    lines.push(`Config:  ${cfgPath} (valid)`);
  } else {
    lines.push(`Config:  ${cfgPath} (INVALID: ${configError})`);
  }

  // Server
  if (serverHealthy) {
    const ver = serverVersion ? ` (v${serverVersion})` : "";
    lines.push(`Server:  ${config.server.url} (healthy${ver})`);
  } else if (config) {
    lines.push(`Server:  ${config.server.url} (NOT REACHABLE)`);
    lines.push(`\n  Start it in another terminal:`);
    lines.push(`    opencode serve\n`);
  } else {
    lines.push(`Server:  Cannot check — fix config errors first.`);
  }

  // Next steps
  if (!serverHealthy && configValid) {
    lines.push("Next: start your Opencode server, then run /opencode:review.");
  } else if (serverHealthy) {
    lines.push("Ready! Run /opencode:review to start a code review.");
  }

  process.stdout.write(lines.join("\n") + "\n");
}

// ---------------------------------------------------------------------------
// executeReviewRun — the review core (extracted for future background mode)
// ---------------------------------------------------------------------------

async function executeReviewRun({
  config,
  reviewId,
  cwd,
  target,
  jsonMode,
  command,
}) {
  // Health check — fail fast
  const health = await healthCheck(config).catch(() => ({ healthy: false }));
  if (!health.healthy) {
    throw new OpencodeUnreachableError(
      `Can't reach Opencode at ${config.server.url}.`,
      {
        suggestion: [
          "Start the server in another terminal:",
          "  opencode serve",
          "",
          "Then re-run the command.",
          "",
          `If your server runs on a different URL, set [server].url in`,
          `~/.config/opencode-plugin/config.toml.`,
        ].join("\n"),
      }
    );
  }

  // Create session scoped to project directory
  const { id: sessionId } = await createSession(config, { directory: cwd });

  // Build prompt
  const prompt = buildReviewPrompt(target, cwd);

  // Wire up event stream + consumers
  const stream = new EventStream(config, sessionId);
  const renderer = jsonMode ? null : new StatusRenderer();
  const transcript = new TranscriptWriter({
    reviewId,
    workspaceRoot: cwd,
    config,
  });

  transcript.attach(stream);
  renderer?.attach(stream);

  // Write transcript header immediately (status: running)
  const startedAt = new Date();
  await transcript.start({
    metadata: {
      id: reviewId,
      command: `/opencode:review ${command.join(" ")}`,
      agent: config.commands.review.agent,
      provider: config.commands.review.provider,
      model: config.commands.review.model,
      sessionId,
      workspace: cwd,
      target: target.label,
      startedAt: startedAt.toISOString(),
      status: "running",
    },
  });

  // SSE stream MUST be connected before sending the prompt
  await stream.start();
  renderer?.start();

  // SIGINT handler for graceful cancellation
  const abortController = new AbortController();
  let cancelledByUser = false;
  const sigintHandler = () => {
    if (cancelledByUser) {
      process.exit(130);
    }
    cancelledByUser = true;
    process.stderr.write(
      "\nCancelling\u2026 (press Ctrl-C again to force-quit)\n"
    );
    abortController.abort();
  };
  process.on("SIGINT", sigintHandler);

  // Blocking POST
  let response = null;
  let runError = null;
  try {
    response = await sendMessage(config, sessionId, {
      directory: cwd,
      prompt,
      agent: config.commands.review.agent,
      model:
        config.commands.review.provider && config.commands.review.model
          ? {
              providerID: config.commands.review.provider,
              modelID: config.commands.review.model,
            }
          : undefined,
      signal: abortController.signal,
    });
    if (response.info?.finish !== "stop") {
      throw new OpencodeResponseError(
        `Opencode review ended unexpectedly (finish: '${response.info?.finish}').`,
        {
          suggestion: `Transcript: ${config.transcript.directory}/${reviewId}.log.md`,
        }
      );
    }
  } catch (err) {
    runError = err;
  } finally {
    process.off("SIGINT", sigintHandler);

    // Drain SSE stream
    try {
      await stream.waitForDone({ timeoutMs: 2000 });
    } catch {
      /* timeout is fine */
    }

    renderer?.stop();
    await stream.stop();

    // Map error to terminal status
    const resultStatus = (() => {
      if (cancelledByUser) return "cancelled";
      if (!runError) return "completed";
      if (runError instanceof OpencodeUnreachableError) return "error";
      if (runError instanceof OpencodeApiError) return "error";
      if (runError instanceof OpencodeResponseError) return "error";
      return "interrupted";
    })();

    const finalReviewText = response
      ? response.parts
          .filter((p) => p.type === "text" && p.text)
          .map((p) => p.text)
          .join("\n\n")
      : "";

    const completedAt = new Date();
    await transcript.finish({
      finalReviewText,
      status: resultStatus,
      duration: formatDuration(completedAt - startedAt),
      toolCount: stream.toolCount,
      completedAt: completedAt.toISOString(),
      errorMessage: runError?.message,
    });

    if (runError) throw runError;
  }

  // Build result
  const finalReviewText = response.parts
    .filter((p) => p.type === "text" && p.text)
    .map((p) => p.text)
    .join("\n\n");

  return {
    reviewId,
    sessionId,
    target,
    finalReviewText,
    logPath: `${config.transcript.directory}/${reviewId}.log.md`,
    reviewPath: `${config.transcript.directory}/${reviewId}.review.md`,
    status: "completed",
    durationMs: new Date() - startedAt,
    toolCount: stream.toolCount,
  };
}

// ---------------------------------------------------------------------------
// handleReview — thin CLI glue
// ---------------------------------------------------------------------------

async function handleReview(argv) {
  const { options } = parseArgs(argv, {
    valueOptions: ["base", "scope", "model", "agent"],
    booleanOptions: ["json"],
    aliasMap: { m: "model" },
  });

  const config = loadConfig({
    overrides: {
      commands: {
        review: {
          ...(options.model && { model: options.model }),
          ...(options.agent && { agent: options.agent }),
        },
      },
    },
  });

  const cwd = process.cwd();
  const target = resolveReviewTarget(cwd, {
    base: options.base,
    scope: options.scope,
  });
  const reviewId = makeReviewId();

  const result = await executeReviewRun({
    config,
    reviewId,
    cwd,
    target,
    jsonMode: options.json,
    command: argv,
  });

  if (options.json) {
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  } else {
    process.stdout.write(result.finalReviewText);
    process.stdout.write(`\n\n\u2014 saved to ${result.reviewPath}\n`);
  }
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

async function main() {
  const [subcommand, ...argv] = process.argv.slice(2);
  switch (subcommand) {
    case "review":
      return handleReview(argv);
    case "setup":
      return handleSetup(argv);
    case "help":
    case "--help":
    case undefined:
      printUsage();
      return;
    default:
      printUsage();
      process.exitCode = 2;
  }
}

main().catch((err) => {
  if (err instanceof OpencodePluginError) {
    process.stderr.write(`Error: ${err.message}\n`);
    if (err.suggestion) {
      process.stderr.write(`\n${err.suggestion}\n`);
    }
    process.exitCode = err.exitCode;
  } else {
    process.stderr.write(`Unexpected error: ${err.message}\n${err.stack}\n`);
    process.stderr.write(`\nThis looks like a bug. Please report it.\n`);
    process.exitCode = 1;
  }
});
```

- [ ] **Step 2: Verify the script runs without error**

Run: `cd plugins/opencode && node scripts/opencode-companion.mjs help`
Expected: Usage text printed, exit 0

- [ ] **Step 3: Commit**

```bash
git add plugins/opencode/scripts/opencode-companion.mjs
git commit -m "feat(opencode): add companion script with dispatcher, handleSetup, handleReview"
```

---

### Task 12: SKILL.md files + plugin wiring

**Files:**
- Create: `plugins/opencode/skills/review/SKILL.md`
- Create: `plugins/opencode/skills/setup/SKILL.md`

These are the user-facing slash command definitions that Claude Code reads.

- [ ] **Step 1: Create review skill**

Create `plugins/opencode/skills/review/SKILL.md`:

````markdown
---
description: Run a code review via your running Opencode server
argument-hint: '[--base <ref>] [--scope auto|working-tree|branch] [--model <spec>] [--json]'
disable-model-invocation: true
allowed-tools: Bash(node:*)
---

Run an Opencode code review through the companion script.

Raw slash-command arguments:
`$ARGUMENTS`

Core constraint:
- This command is review-only. Do not fix issues, apply patches, or suggest
  that you are about to make changes.
- Your only job is to run the review and return the companion script's
  output verbatim to the user.

Execution:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/opencode-companion.mjs" review "$ARGUMENTS"
```

Return the command's stdout verbatim. Do not paraphrase or summarise.
````

- [ ] **Step 2: Create setup skill**

Create `plugins/opencode/skills/setup/SKILL.md`:

````markdown
---
description: Verify Opencode plugin setup and create the config file if missing
disable-model-invocation: true
allowed-tools: Bash(node:*)
---

Run the Opencode plugin setup helper.

Execution:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/opencode-companion.mjs" setup
```

Return the command's stdout verbatim.
````

- [ ] **Step 3: Commit**

```bash
git add plugins/opencode/skills
git commit -m "feat(opencode): add SKILL.md files for /opencode:review and /opencode:setup"
```

---

### Task 13: Integration test — full review flow

**Files:**
- Create: `plugins/opencode/tests/integration/review-flow.test.mjs`

End-to-end test of `executeReviewRun` against the fake Opencode server. Verifies transcript files, result object, and failure handling.

Note: we cannot directly import `executeReviewRun` since it's not exported from `opencode-companion.mjs`. Instead, we'll test the companion script as a child process (matching how Claude Code invokes it), and separately test the composition via a small wrapper. For a cleaner approach, extract `executeReviewRun` into a separate module or export it. For v1, test via child process execution with a temp git repo.

- [ ] **Step 1: Write the integration test**

Create `plugins/opencode/tests/integration/review-flow.test.mjs`:

```javascript
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execSync, execFileSync } from "node:child_process";
import { startFakeServer } from "../fixtures/fake-opencode-server.mjs";

const COMPANION = path.resolve(
  import.meta.dirname,
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

    const result = execFileSync(
      process.execPath,
      [COMPANION, "review", "--scope", "working-tree", "--json"],
      {
        cwd: repoDir,
        encoding: "utf8",
        env: {
          ...process.env,
          OPENCODE_PLUGIN_CONFIG: configPath,
        },
        timeout: 15000,
      }
    );

    const parsed = JSON.parse(result);
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
      execFileSync(
        process.execPath,
        [COMPANION, "review", "--scope", "working-tree"],
        {
          cwd: repoDir,
          encoding: "utf8",
          env: {
            ...process.env,
            OPENCODE_PLUGIN_CONFIG: configPath,
          },
          timeout: 10000,
        }
      );
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
      execFileSync(
        process.execPath,
        [COMPANION, "review", "--scope", "working-tree"],
        {
          cwd: repoDir,
          encoding: "utf8",
          env: {
            ...process.env,
            OPENCODE_PLUGIN_CONFIG: configPath,
          },
          timeout: 10000,
        }
      );
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
```

- [ ] **Step 2: Run integration tests**

Run: `cd plugins/opencode && node --test tests/integration/review-flow.test.mjs`
Expected: All 3 tests PASS

- [ ] **Step 3: Run all tests**

Run: `cd plugins/opencode && npm test`
Expected: All tests across all files PASS

- [ ] **Step 4: Commit**

```bash
git add plugins/opencode/tests/integration/review-flow.test.mjs
git commit -m "test(opencode): add end-to-end integration test for review flow"
```

---

### Task 14: README + LICENSE + final verification

**Files:**
- Create: `plugins/opencode/README.md`
- Create: `plugins/opencode/LICENSE`

- [ ] **Step 1: Create README**

Create `plugins/opencode/README.md`:

```markdown
# Opencode Plugin for Claude Code

Dispatch code reviews to a running [Opencode](https://github.com/anomalyco/opencode) server from Claude Code.

## Quick start

1. Install Opencode and start the server:

   ```bash
   opencode serve
   ```

2. Load the plugin in Claude Code:

   ```bash
   claude --plugin-dir ./plugins/opencode
   ```

3. Run a review:

   ```
   /opencode:review
   ```

## Commands

### `/opencode:review`

Run a code review on your current git changes.

```
/opencode:review                          # Auto-detect scope
/opencode:review --scope working-tree     # Review uncommitted changes
/opencode:review --scope branch           # Review branch vs upstream
/opencode:review --base origin/main       # Review against a specific base
/opencode:review --json                   # Machine-readable output
```

### `/opencode:setup`

Verify the plugin is configured correctly and the server is reachable.

## Configuration

Config file: `~/.config/opencode-plugin/config.toml`

Created automatically on first run. Edit to customize:

```toml
[server]
url = "http://localhost:4096"
# password = "your-bearer-token"

[commands.review]
agent    = "code-reviewer"
provider = "poe"
model    = "openai/gpt-5.4"

[transcript]
directory         = ".opencode/reviews"
include_reasoning = false
```

## Transcripts

Each review produces two files under `.opencode/reviews/`:

- **`{id}.log.md`** — chat-transcript-style activity log (tool calls, thinking phases, timing)
- **`{id}.review.md`** — the clean final review text

You can `tail -f .opencode/reviews/{id}.log.md` in another terminal to watch the review live.

## Requirements

- Node.js 20+
- A running Opencode server (`opencode serve`)
- Claude Code
```

- [ ] **Step 2: Create LICENSE**

Create `plugins/opencode/LICENSE`:

```
MIT License

Copyright (c) 2026 Martin Kuek

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Add .opencode to .gitignore**

Append to the project's `.gitignore` (or create `plugins/opencode/.gitignore`):

```gitignore
# Opencode plugin runtime artifacts
.opencode/
node_modules/
```

Create `plugins/opencode/.gitignore` with the above content.

- [ ] **Step 4: Final test run**

Run: `cd plugins/opencode && npm test`
Expected: All tests PASS

- [ ] **Step 5: Final commit**

```bash
git add plugins/opencode/README.md plugins/opencode/LICENSE plugins/opencode/.gitignore
git commit -m "docs(opencode): add README, LICENSE, and gitignore"
```

- [ ] **Step 6: Verify plugin loads in Claude Code**

Run: `claude --plugin-dir ./plugins/opencode --debug 2>&1 | head -30`
Expected: Debug output shows the opencode plugin loading, `opencode:review` and `opencode:setup` skills registered.

---

## Post-implementation checklist

After all 14 tasks are complete:

- [ ] Run `cd plugins/opencode && npm test` — all tests pass
- [ ] Run `claude --plugin-dir ./plugins/opencode` and type `/opencode:setup` — should report config status and server reachability
- [ ] Start `opencode serve` in another terminal, then run `/opencode:review` in a git repo with dirty working tree — should produce a review with live progress footer and transcript files
- [ ] Check `.opencode/reviews/` contains both `.log.md` and `.review.md` files with correct frontmatter
