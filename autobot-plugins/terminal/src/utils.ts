// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

/** Minimal scoped logger for plugin-internal use. */
export function createLogger(scope: string) {
  const prefix = `[${scope}]`
  return {
    debug: (...args: unknown[]) => console.debug(prefix, ...args),
    info: (...args: unknown[]) => console.info(prefix, ...args),
    warn: (...args: unknown[]) => console.warn(prefix, ...args),
    error: (...args: unknown[]) => console.error(prefix, ...args),
  }
}
