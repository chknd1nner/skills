import { CliArgumentError } from "./errors.mjs";

/**
 * Parse argv against a schema.
 * @param {string[]} argv
 * @param {{ valueOptions?: string[], booleanOptions?: string[], aliasMap?: Record<string,string> }} schema
 * @returns {{ options: Record<string, string|boolean>, positionals: string[] }}
 */
export function parseArgs(argv, schema = {}) {
  const valueSet = new Set(schema.valueOptions ?? []);
  const boolSet = new Set(schema.booleanOptions ?? []);
  const aliases = schema.aliasMap ?? {};

  const options = {};
  const positionals = [];
  let endOfOptions = false;

  // Initialize booleans to false
  for (const key of boolSet) {
    options[key] = false;
  }

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];

    if (endOfOptions) {
      positionals.push(arg);
      continue;
    }

    if (arg === "--") {
      endOfOptions = true;
      continue;
    }

    // Long option: --name or --name value
    if (arg.startsWith("--")) {
      const name = arg.slice(2);
      if (boolSet.has(name)) {
        options[name] = true;
      } else if (valueSet.has(name)) {
        if (i + 1 >= argv.length) {
          throw new CliArgumentError(`Option '--${name}' requires a value.`);
        }
        options[name] = argv[++i];
      } else {
        throw new CliArgumentError(`Unknown option '--${name}'.`);
      }
      continue;
    }

    // Short option: -x (single char, resolved via alias)
    if (arg.startsWith("-") && arg.length === 2) {
      const short = arg[1];
      const resolved = aliases[short];
      if (resolved && boolSet.has(resolved)) {
        options[resolved] = true;
      } else if (resolved && valueSet.has(resolved)) {
        if (i + 1 >= argv.length) {
          throw new CliArgumentError(
            `Option '-${short}' (--${resolved}) requires a value.`
          );
        }
        options[resolved] = argv[++i];
      } else {
        throw new CliArgumentError(`Unknown option '${arg}'.`);
      }
      continue;
    }

    positionals.push(arg);
  }

  return { options, positionals };
}
