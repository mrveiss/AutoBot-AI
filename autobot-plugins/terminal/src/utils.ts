// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform

type LogFn = (...args: unknown[]) => void
const noop: LogFn = () => {}

/** Minimal scoped logger for plugin-internal use. No-op by default to comply with no-console rule. */
export function createLogger(_scope: string) {
  return {
    debug: noop,
    info: noop,
    warn: noop,
    error: noop,
  }
}

/**
 * URL/error log redaction is the kit's single implementation (#18550).
 * This package used to carry a copy held in sync by a drift test (#15002);
 * it now imports the kit like the rest of the shared frontend code.
 */
export { redactUrlForLogging, redactErrorForLogging } from '@autobot/ui'
