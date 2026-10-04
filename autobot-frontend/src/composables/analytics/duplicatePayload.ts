// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Read a duplicate-detection payload by its `status` (#17983).
 *
 * The backend answers HTTP 200 for every outcome -- `success`, `partial` (a
 * timeout with what was found so far), `error` (the scan did not run, e.g. the
 * source does not resolve: #17982) and `no_data`/no cache yet. Reading only
 * `duplicates` collapsed a failed scan into "0 duplicates found", which is the
 * one answer a failed scan must never give.
 */
import type { DuplicateCode } from './analyticsTypes'

/** done: a real result (possibly empty); not_scanned: nothing to show yet; failed: the scan did not run. */
export type DuplicateScanState = 'done' | 'not_scanned' | 'failed'

export interface DuplicateReading {
  state: DuplicateScanState
  duplicates: DuplicateCode[]
}

export function readDuplicatePayload(raw: unknown): DuplicateReading {
  const payload = (raw ?? {}) as { status?: unknown; duplicates?: unknown }
  if ((payload.status === 'success' || payload.status === 'partial') && Array.isArray(payload.duplicates)) {
    return { state: 'done', duplicates: payload.duplicates as DuplicateCode[] }
  }
  return { state: payload.status === 'error' ? 'failed' : 'not_scanned', duplicates: [] }
}
