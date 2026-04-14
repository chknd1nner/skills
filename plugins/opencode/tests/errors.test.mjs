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
