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
