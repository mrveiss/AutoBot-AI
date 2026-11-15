// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Bound for RumAgent's per-call buffers (#21583).
 *
 * Every kit-client request is recorded now, so a polling view would grow the buffers without bound. They keep the
 * latest N. The unflushed reporting queue is bounded too: it is only drained by the periodic reporter, which runs
 * only when RUM is enabled. N is env-backed (`VITE_RUM_MAX_API_CALLS`); an unset or non-positive value falls back
 * to the default.
 */

const DEFAULT_MAX_API_CALLS = 200
const configured = Number(import.meta.env.VITE_RUM_MAX_API_CALLS)

export const RUM_MAX_API_CALLS = Number.isInteger(configured) && configured > 0 ? configured : DEFAULT_MAX_API_CALLS

/** Append *item* and drop the oldest entries so *list* holds at most RUM_MAX_API_CALLS. */
export function pushCapped<T>(list: T[], item: T): void {
  list.push(item)
  if (list.length > RUM_MAX_API_CALLS) list.splice(0, list.length - RUM_MAX_API_CALLS)
}
