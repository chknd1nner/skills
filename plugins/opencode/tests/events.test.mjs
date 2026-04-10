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
