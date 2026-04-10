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
