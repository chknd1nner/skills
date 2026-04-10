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
