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
