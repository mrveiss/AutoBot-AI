// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * @autobot/ui — the one numeric `VITE_*` reader (#20135, #19614).
 *
 * Both apps declared their own: the SLM's rejected 0 and negatives, the main
 * app's accepted them, including for ports. The kit cannot rely on each app's
 * `import.meta.env` (Vite replaces it per build), so the env object is an
 * argument: call `getEnvPositiveInt(import.meta.env, 'VITE_X', 30_000)`.
 */

/** The shape of `import.meta.env` the reader needs. */
export type EnvSource = Record<string, unknown>

/**
 * Read a numeric `VITE_*` variable as a positive integer.
 *
 * Every caller is a timeout, a count, a limit or a port, where 0 or a negative
 * value is a misconfiguration, not a request, so unset, empty, non-numeric,
 * zero and negative values all fall back to `defaultValue`.
 */
export function getEnvPositiveInt(env: EnvSource, key: string, defaultValue: number): number {
  const value = env[key]
  if (value === undefined || value === null || value === '') {
    return defaultValue
  }
  const parsed = parseInt(String(value), 10)
  return Number.isNaN(parsed) || parsed <= 0 ? defaultValue : parsed
}
