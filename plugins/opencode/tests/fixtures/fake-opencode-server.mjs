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

      // Write a keepalive comment so the SSE fetch() call returns headers
      // immediately even when no events are queued yet.
      res.write(":keepalive\n\n");

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
