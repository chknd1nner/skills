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

  it("rejects unknown long options", () => {
    assert.throws(
      () => parseArgs(["--unknown"], { booleanOptions: ["json"] }),
      /Unknown option/
    );
  });

  it("rejects unknown short options", () => {
    assert.throws(
      () => parseArgs(["-x"], { booleanOptions: ["json"] }),
      /Unknown option/
    );
  });
});
