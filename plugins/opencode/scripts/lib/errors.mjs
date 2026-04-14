export class OpencodePluginError extends Error {
  constructor(message, { exitCode = 1, suggestion } = {}) {
    super(message);
    this.name = this.constructor.name;
    this.exitCode = exitCode;
    this.suggestion = suggestion;
  }
}

export class ConfigError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 2, ...opts });
  }
}

export class CliArgumentError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 2, ...opts });
  }
}

export class GitError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 1, ...opts });
  }
}

export class OpencodeUnreachableError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 1, ...opts });
  }
}

export class OpencodeApiError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 1, ...opts });
  }
}

export class OpencodeResponseError extends OpencodePluginError {
  constructor(message, opts = {}) {
    super(message, { exitCode: 1, ...opts });
  }
}
