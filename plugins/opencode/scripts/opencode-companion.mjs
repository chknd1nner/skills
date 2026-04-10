#!/usr/bin/env node

import crypto from "node:crypto";
import process from "node:process";

import { parseArgs } from "./lib/args.mjs";
import { loadConfig, ensureDefaultConfig } from "./lib/config.mjs";
import { healthCheck, createSession, sendMessage } from "./lib/client.mjs";
import { resolveReviewTarget } from "./lib/git.mjs";
import { EventStream } from "./lib/events.mjs";
import { StatusRenderer } from "./lib/render.mjs";
import { TranscriptWriter } from "./lib/transcript.mjs";
import { buildReviewPrompt } from "./lib/prompts.mjs";
import {
  OpencodePluginError,
  OpencodeUnreachableError,
  OpencodeApiError,
  OpencodeResponseError,
} from "./lib/errors.mjs";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeReviewId() {
  const now = new Date();
  const ts = now.toISOString().replace(/:/g, "-").replace(/\.\d+Z$/, "");
  const ms = String(now.getMilliseconds()).padStart(3, "0");
  const rand = crypto.randomBytes(2).toString("hex");
  return `${ts}-${ms}Z-${rand}`;
}

function formatDuration(ms) {
  const totalSec = Math.floor(ms / 1000);
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  }
  return `${seconds}s`;
}

function printUsage() {
  console.log(
    [
      "Usage:",
      "  opencode-companion.mjs setup",
      "  opencode-companion.mjs review [--base <ref>] [--scope auto|working-tree|branch] [--model <spec>] [--agent <name>] [--json]",
    ].join("\n")
  );
}

// ---------------------------------------------------------------------------
// handleSetup
// ---------------------------------------------------------------------------

async function handleSetup(argv) {
  const { options } = parseArgs(argv, { booleanOptions: ["json"] });

  // Ensure config file exists
  const { created, path: cfgPath } = ensureDefaultConfig();

  // Load config (validates it)
  let config;
  let configValid = true;
  let configError = null;
  try {
    config = loadConfig();
  } catch (err) {
    configValid = false;
    configError = err.message;
    config = null;
  }

  // Health check
  let serverHealthy = false;
  let serverVersion = null;
  if (config) {
    const health = await healthCheck(config);
    serverHealthy = health.healthy;
    serverVersion = health.version ?? null;
  }

  const report = {
    configFile: {
      path: cfgPath,
      created,
      valid: configValid,
      error: configError,
    },
    server: {
      url: config?.server?.url ?? "(unknown — config invalid)",
      healthy: serverHealthy,
      version: serverVersion,
    },
  };

  if (options.json) {
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    return;
  }

  // Human-readable output
  const lines = [];
  lines.push("Opencode Plugin Setup");
  lines.push("=====================\n");

  // Config file
  if (created) {
    lines.push(`Config:  Created default at ${cfgPath}`);
  } else if (configValid) {
    lines.push(`Config:  ${cfgPath} (valid)`);
  } else {
    lines.push(`Config:  ${cfgPath} (INVALID: ${configError})`);
  }

  // Server
  if (serverHealthy) {
    const ver = serverVersion ? ` (v${serverVersion})` : "";
    lines.push(`Server:  ${config.server.url} (healthy${ver})`);
  } else if (config) {
    lines.push(`Server:  ${config.server.url} (NOT REACHABLE)`);
    lines.push(`\n  Start it in another terminal:`);
    lines.push(`    opencode serve\n`);
  } else {
    lines.push(`Server:  Cannot check — fix config errors first.`);
  }

  // Next steps
  if (!serverHealthy && configValid) {
    lines.push("Next: start your Opencode server, then run /opencode:review.");
  } else if (serverHealthy) {
    lines.push("Ready! Run /opencode:review to start a code review.");
  }

  process.stdout.write(lines.join("\n") + "\n");
}

// ---------------------------------------------------------------------------
// executeReviewRun — the review core (extracted for future background mode)
// ---------------------------------------------------------------------------

async function executeReviewRun({
  config,
  reviewId,
  cwd,
  target,
  jsonMode,
  command,
}) {
  // Health check — fail fast
  const health = await healthCheck(config).catch(() => ({ healthy: false }));
  if (!health.healthy) {
    throw new OpencodeUnreachableError(
      `Can't reach Opencode at ${config.server.url}.`,
      {
        suggestion: [
          "Start the server in another terminal:",
          "  opencode serve",
          "",
          "Then re-run the command.",
          "",
          `If your server runs on a different URL, set [server].url in`,
          `~/.config/opencode-plugin/config.toml.`,
        ].join("\n"),
      }
    );
  }

  // Create session scoped to project directory
  const { id: sessionId } = await createSession(config, { directory: cwd });

  // Build prompt
  const prompt = buildReviewPrompt(target, cwd);

  // Wire up event stream + consumers
  const stream = new EventStream(config, sessionId);
  const renderer = jsonMode ? null : new StatusRenderer();
  const transcript = new TranscriptWriter({
    reviewId,
    workspaceRoot: cwd,
    config,
  });

  transcript.attach(stream);
  renderer?.attach(stream);

  // Listen for SSE-level errors (server-side failures, stream drops)
  stream.on("stream-error", ({ error }) => {
    process.stderr.write(`\nOpencode stream error: ${error}\n`);
  });

  // Write transcript header immediately (status: running)
  const startedAt = new Date();
  await transcript.start({
    metadata: {
      id: reviewId,
      command: `/opencode:review ${command.join(" ")}`,
      agent: config.commands.review.agent,
      provider: config.commands.review.provider,
      model: config.commands.review.model,
      sessionId,
      workspace: cwd,
      target: target.label,
      startedAt: startedAt.toISOString(),
      status: "running",
    },
  });

  // SSE stream MUST be connected before sending the prompt
  await stream.start();
  renderer?.start();

  // SIGINT handler for graceful cancellation
  const abortController = new AbortController();
  let cancelledByUser = false;
  const sigintHandler = () => {
    if (cancelledByUser) {
      process.exit(130);
    }
    cancelledByUser = true;
    process.stderr.write(
      "\nCancelling\u2026 (press Ctrl-C again to force-quit)\n"
    );
    abortController.abort();
  };
  process.on("SIGINT", sigintHandler);

  // Blocking POST
  let response = null;
  let runError = null;
  let finalReviewText = "";
  try {
    response = await sendMessage(config, sessionId, {
      directory: cwd,
      prompt,
      agent: config.commands.review.agent,
      model:
        config.commands.review.provider && config.commands.review.model
          ? {
              providerID: config.commands.review.provider,
              modelID: config.commands.review.model,
            }
          : undefined,
      signal: abortController.signal,
    });
    if (response.info?.finish !== "stop") {
      throw new OpencodeResponseError(
        `Opencode review ended unexpectedly (finish: '${response.info?.finish}').`,
        {
          suggestion: `Transcript: ${config.transcript.directory}/${reviewId}.log.md`,
        }
      );
    }
  } catch (err) {
    runError = err;
  } finally {
    process.off("SIGINT", sigintHandler);

    // Drain SSE stream
    try {
      await stream.waitForDone({ timeoutMs: 2000 });
    } catch {
      /* timeout is fine */
    }

    renderer?.stop();
    await stream.stop();

    // Map error to terminal status
    const resultStatus = (() => {
      if (cancelledByUser) return "cancelled";
      if (!runError) return "completed";
      if (runError instanceof OpencodeUnreachableError) return "error";
      if (runError instanceof OpencodeApiError) return "error";
      if (runError instanceof OpencodeResponseError) return "error";
      return "interrupted";
    })();

    finalReviewText = response
      ? response.parts
          .filter((p) => p.type === "text" && p.text)
          .map((p) => p.text)
          .join("\n\n")
      : "";

    const completedAt = new Date();
    await transcript.finish({
      finalReviewText,
      status: resultStatus,
      duration: formatDuration(completedAt - startedAt),
      toolCount: stream.toolCount,
      completedAt: completedAt.toISOString(),
      errorMessage: runError?.message,
    });

    if (runError) throw runError;

    // Build result (only reachable when runError is null → response is defined)
    // Reuses finalReviewText already computed above in the finally block.
    return {
      reviewId,
      sessionId,
      target,
      finalReviewText,
      logPath: `${config.transcript.directory}/${reviewId}.log.md`,
      reviewPath: `${config.transcript.directory}/${reviewId}.review.md`,
      status: "completed",
      durationMs: completedAt - startedAt,
      toolCount: stream.toolCount,
    };
  }
}

// ---------------------------------------------------------------------------
// handleReview — thin CLI glue
// ---------------------------------------------------------------------------

async function handleReview(argv) {
  const { options } = parseArgs(argv, {
    valueOptions: ["base", "scope", "model", "agent"],
    booleanOptions: ["json"],
    aliasMap: { m: "model" },
  });

  // Parse --model spec as "provider/model" if it contains a slash
  const modelOverrides = {};
  if (options.model) {
    const slashIdx = options.model.indexOf("/");
    if (slashIdx > 0) {
      modelOverrides.provider = options.model.slice(0, slashIdx);
      modelOverrides.model = options.model.slice(slashIdx + 1);
    } else {
      modelOverrides.model = options.model;
    }
  }

  // Ensure config file exists on first run
  ensureDefaultConfig();

  const config = loadConfig({
    overrides: {
      commands: {
        review: {
          ...modelOverrides,
          ...(options.agent && { agent: options.agent }),
        },
      },
    },
  });

  const cwd = process.cwd();
  const target = resolveReviewTarget(cwd, {
    base: options.base,
    scope: options.scope,
  });
  const reviewId = makeReviewId();

  const result = await executeReviewRun({
    config,
    reviewId,
    cwd,
    target,
    jsonMode: options.json,
    command: argv,
  });

  if (options.json) {
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  } else if (!result.finalReviewText) {
    process.stderr.write(
      `Warning: Opencode completed but returned no review text.\n` +
        `Log: ${result.logPath}\n`
    );
  } else {
    process.stdout.write(result.finalReviewText);
    process.stdout.write(`\n\n\u2014 saved to ${result.reviewPath}\n`);
  }
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

async function main() {
  const [subcommand, ...argv] = process.argv.slice(2);
  switch (subcommand) {
    case "review":
      return handleReview(argv);
    case "setup":
      return handleSetup(argv);
    case "help":
    case "--help":
    case undefined:
      printUsage();
      return;
    default:
      printUsage();
      process.exitCode = 2;
  }
}

main().catch((err) => {
  if (err.name === "AbortError") {
    // User cancelled via Ctrl-C — clean exit
    process.exitCode = 130;
  } else if (err instanceof OpencodePluginError) {
    process.stderr.write(`Error: ${err.message}\n`);
    if (err.suggestion) {
      process.stderr.write(`\n${err.suggestion}\n`);
    }
    process.exitCode = err.exitCode;
  } else {
    process.stderr.write(`Unexpected error: ${err.message}\n${err.stack}\n`);
    process.stderr.write(`\nThis looks like a bug. Please report it.\n`);
    process.exitCode = 1;
  }
});
