// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — scoped console logger.
 *
 * Self-contained equivalent of the main app's `createLogger` (from
 * `autobot-frontend/src/utils/debugUtils`). The kit is consumed by BOTH
 * frontends via a `file:` dependency and must not reach into either app's
 * `@/` alias, so it carries its own minimal logger for the composables that
 * emit developer warnings (usePagination, useFormValidation).
 *
 * Behavior is byte-for-byte identical to the app helper: each call forwards
 * a `[timestamp] [LEVEL]` prefix plus the scoped message to the matching
 * `console.*` method.
 */

/** Log levels for console output. */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

/**
 * Enhanced console logging with timestamp and level prefix. Supports
 * variadic args so callers can use printf-style placeholders or pass
 * multiple values.
 */
export function log(level: LogLevel, message: string, ...args: unknown[]): void {
  const timestamp = new Date().toISOString()
  const prefix = `[${timestamp}] [${level.toUpperCase()}]`
  const consoleFn = level === 'debug' ? console.debug
    : level === 'info' ? console.info
    : level === 'warn' ? console.warn
    : console.error

  consoleFn(prefix, message, ...args)
}

/**
 * Create a scoped logger with an automatic `[scope]` prefix.
 *
 * @param scope - Scope name (e.g. 'usePagination')
 * @returns Scoped logging functions
 */
export function createLogger(scope: string) {
  return {
    debug: (message: string, ...args: unknown[]) => log('debug', `[${scope}] ${message}`, ...args),
    info: (message: string, ...args: unknown[]) => log('info', `[${scope}] ${message}`, ...args),
    warn: (message: string, ...args: unknown[]) => log('warn', `[${scope}] ${message}`, ...args),
    error: (message: string, ...args: unknown[]) => log('error', `[${scope}] ${message}`, ...args),
  }
}
