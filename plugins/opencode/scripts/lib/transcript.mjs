import fs from "node:fs";
import path from "node:path";

function capitalize(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

function buildFrontmatter(meta) {
  const lines = ["---"];
  for (const [key, value] of Object.entries(meta)) {
    if (value === null || value === undefined) {
      lines.push(`${key}: null`);
    } else if (typeof value === "number") {
      lines.push(`${key}: ${value}`);
    } else {
      lines.push(`${key}: ${value}`);
    }
  }
  lines.push("---\n");
  return lines.join("\n");
}

function rewriteFrontmatter(filePath, updates) {
  const content = fs.readFileSync(filePath, "utf8");
  const endIdx = content.indexOf("---\n", 4);
  if (endIdx === -1) return;
  const frontmatter = content.slice(4, endIdx);
  let newFM = frontmatter;
  for (const [key, value] of Object.entries(updates)) {
    const regex = new RegExp(`^${key}:.*$`, "m");
    const replacement =
      value === null ? `${key}: null` : `${key}: ${value}`;
    if (regex.test(newFM)) {
      newFM = newFM.replace(regex, replacement);
    } else {
      newFM += `${replacement}\n`;
    }
  }
  const rest = content.slice(endIdx);
  const updated = `---\n${newFM}${rest}`;
  const tmpPath = filePath + ".tmp";
  fs.writeFileSync(tmpPath, updated, "utf8");
  fs.renameSync(tmpPath, filePath);
}

export class TranscriptWriter {
  #reviewId;
  #workspaceRoot;
  #config;
  #logPath;
  #reviewFilePath;
  #metadata;

  constructor({ reviewId, workspaceRoot, config }) {
    this.#reviewId = reviewId;
    this.#workspaceRoot = workspaceRoot;
    this.#config = config;
    const dir = path.join(workspaceRoot, config.transcript.directory);
    this.#logPath = path.join(dir, `${reviewId}.log.md`);
    this.#reviewFilePath = path.join(dir, `${reviewId}.review.md`);
  }

  attach(eventStream) {
    eventStream.on("tool-start", ({ tool, input }) => {
      const line = `\n● ${capitalize(tool)}(\`${input}\`)\n  \u23BF (output hidden)\n`;
      this.#append(line);
    });

    eventStream.on("phase", ({ label }) => {
      if (label === "thinking") {
        this.#append("\n_Thinking\u2026_\n");
      } else if (label === "writing") {
        this.#append("\n_Writing report\u2026_\n\n");
      }
    });

    eventStream.on("text-delta", ({ text }) => {
      this.#append(text);
    });

    if (this.#config.transcript.include_reasoning) {
      eventStream.on("reasoning", ({ text }) => {
        this.#append(`\n> ${text.replace(/\n/g, "\n> ")}\n`);
      });
    }
  }

  async start({ metadata }) {
    this.#metadata = metadata;
    const dir = path.dirname(this.#logPath);
    fs.mkdirSync(dir, { recursive: true });

    const fm = buildFrontmatter({
      id: metadata.id,
      command: metadata.command,
      agent: metadata.agent,
      provider: metadata.provider ?? null,
      model: metadata.model ?? null,
      session_id: metadata.sessionId,
      workspace: metadata.workspace,
      target: metadata.target,
      status: "running",
      started_at: metadata.startedAt,
      completed_at: null,
      duration: null,
      tool_calls: 0,
    });

    const header = `\n# Opencode Review \u2014 ${metadata.startedAt.split("T")[0]}\n\n`;
    fs.writeFileSync(this.#logPath, fm + header, "utf8");
  }

  async finish({ finalReviewText, status, duration, toolCount, completedAt, errorMessage }) {
    // Append final review section to log
    if (finalReviewText) {
      this.#append(`\n\n## Final Review\n\n${finalReviewText}\n`);
    }

    // Append error section if non-completed
    if (status !== "completed" && errorMessage) {
      this.#append(`\n\n## Error\n\n${errorMessage}\n`);
    }

    // Rewrite frontmatter in log file
    rewriteFrontmatter(this.#logPath, {
      status,
      completed_at: completedAt,
      duration,
      tool_calls: toolCount,
    });

    // Only create review file on success
    if (status === "completed" && finalReviewText) {
      const fm = buildFrontmatter({
        id: this.#reviewId,
        command: this.#metadata.command,
        agent: this.#metadata.agent,
        provider: this.#metadata.provider ?? null,
        model: this.#metadata.model ?? null,
        status: "completed",
        duration,
      });
      fs.writeFileSync(
        this.#reviewFilePath,
        fm + `\n${finalReviewText}\n`,
        "utf8"
      );
    }
  }

  #append(text) {
    try {
      fs.appendFileSync(this.#logPath, text, "utf8");
    } catch {
      // Silently ignore write failures (e.g. if the log was deleted mid-review)
    }
  }
}
