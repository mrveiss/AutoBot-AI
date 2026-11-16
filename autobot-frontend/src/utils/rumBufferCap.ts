// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Bound for RumAgent's per-call buffers (#21583).
 *
 * Every kit-client request is recorded now, so a polling view would grow the buffers without bound. They keep the
 * latest N. Tracked errors (the error log and its unflushed metrics queue) are bounded the same way by their own N
 * (`VITE_RUM_MAX_ERRORS`). The unflushed reporting queues (API calls and critical issues) are bounded too: they are only drained by
 * the periodic reporter, which runs only when RUM is enabled. N is env-backed (`VITE_RUM_MAX_API_CALLS`); an unset, non-numeric or non-positive value
 * falls back to the default (read through the kit's `getEnvPositiveInt`, #20135).
 */

import { getEnvPositiveInt } from '@autobot/ui'

const DEFAULT_MAX_API_CALLS = 200
// The retired ErrorHandler.js kept its error log at 100 entries; the tracked-error buffers keep that bound (#21583).
const DEFAULT_MAX_ERRORS = 100

export const RUM_MAX_API_CALLS = getEnvPositiveInt(import.meta.env, 'VITE_RUM_MAX_API_CALLS', DEFAULT_MAX_API_CALLS)
export const RUM_MAX_ERRORS = getEnvPositiveInt(import.meta.env, 'VITE_RUM_MAX_ERRORS', DEFAULT_MAX_ERRORS)

/** Append *item* and drop the oldest entries so *list* holds at most *max* (default RUM_MAX_API_CALLS). */
export function pushCapped<T>(list: T[], item: T, max: number = RUM_MAX_API_CALLS): void {
  list.push(item)
  if (list.length > max) list.splice(0, list.length - max)
}
