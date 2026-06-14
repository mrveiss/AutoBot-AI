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
