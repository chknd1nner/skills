import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { parse as parseTOML } from "smol-toml";
import { ConfigError } from "./errors.mjs";

export const DEFAULTS = {
  server: {
    url: "http://localhost:4096",
    password: null,
  },
  commands: {
    review: {
      agent: "code-reviewer",
      provider: null,
      model: null,
    },
  },
  transcript: {
    directory: ".opencode/reviews",
    include_reasoning: false,
  },
};

const DEFAULT_CONFIG_PATH = path.join(
  os.homedir(),
  ".config",
  "opencode-plugin",
  "config.toml"
);

const DEFAULT_TEMPLATE = `# Opencode Plugin Configuration
# Start your opencode server separately: opencode serve

[server]
url = "http://localhost:4096"
# password = "your-password-here"

[commands.review]
agent    = "code-reviewer"
# provider = "poe"
# model    = "openai/gpt-5.4"

[transcript]
directory         = ".opencode/reviews"
include_reasoning = false
`;

function deepMerge(target, source) {
  const result = { ...target };
  for (const key of Object.keys(source)) {
    if (source[key] === undefined || source[key] === null) continue;
    if (
      typeof source[key] === "object" &&
      !Array.isArray(source[key]) &&
      typeof target[key] === "object" &&
      !Array.isArray(target[key])
    ) {
      result[key] = deepMerge(target[key] ?? {}, source[key]);
    } else {
      result[key] = source[key];
    }
  }
  return result;
}

function validate(config) {
  // server.url must be a valid URL
  try {
    new URL(config.server.url);
  } catch {
    throw new ConfigError(
      `config: 'server.url' is not a valid URL: '${config.server.url}'.`
    );
  }

  // commands.review.agent must be non-empty
  if (!config.commands?.review?.agent) {
    throw new ConfigError(
      "config: 'commands.review.agent' is required. Set it under [commands.review]."
    );
  }

  // provider and model are a pair
  const rev = config.commands.review;
  const hasProvider = rev.provider != null && rev.provider !== "";
  const hasModel = rev.model != null && rev.model !== "";
  if (hasProvider !== hasModel) {
    throw new ConfigError(
      "config: 'commands.review.provider' and 'commands.review.model' must be set both or neither."
    );
  }

  // transcript.directory must be relative
  const dir = config.transcript?.directory;
  if (dir && (path.isAbsolute(dir) || dir.includes(".."))) {
    throw new ConfigError(
      `config: 'transcript.directory' must be a relative path, got '${dir}'.`
    );
  }

  // transcript.include_reasoning must be boolean
  if (typeof config.transcript?.include_reasoning !== "boolean") {
    throw new ConfigError(
      "config: 'transcript.include_reasoning' must be a boolean."
    );
  }

  return config;
}

/**
 * Load and validate the TOML config, merge with defaults and overrides.
 * @param {{ configPath?: string, overrides?: object }} opts
 * @returns {object} Fully resolved config
 */
export function loadConfig({ configPath, overrides } = {}) {
  const cfgPath =
    configPath ??
    process.env.OPENCODE_PLUGIN_CONFIG ??
    DEFAULT_CONFIG_PATH;

  let fileConfig = {};
  try {
    const raw = fs.readFileSync(cfgPath, "utf8");
    fileConfig = parseTOML(raw);
  } catch (err) {
    if (err.code === "ENOENT") {
      // File missing — use defaults only
    } else if (err.line != null) {
      throw new ConfigError(
        `Failed to parse ${cfgPath} at line ${err.line}: ${err.message}`
      );
    } else {
      throw new ConfigError(`Failed to read ${cfgPath}: ${err.message}`);
    }
  }

  // Three-layer merge: defaults ← TOML file ← CLI overrides
  let merged = deepMerge(DEFAULTS, fileConfig);
  if (overrides) {
    merged = deepMerge(merged, overrides);
  }

  return validate(merged);
}

/**
 * Create the default config file if it doesn't exist.
 * @param {string} [cfgPath]
 * @returns {{ created: boolean, path: string }}
 */
export function ensureDefaultConfig(cfgPath) {
  const target = cfgPath ?? DEFAULT_CONFIG_PATH;
  if (fs.existsSync(target)) {
    return { created: false, path: target };
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, DEFAULT_TEMPLATE, "utf8");
  return { created: true, path: target };
}
