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
