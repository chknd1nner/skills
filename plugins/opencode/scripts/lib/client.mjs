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
