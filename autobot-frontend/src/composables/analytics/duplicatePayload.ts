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
 *
 * `partial` needs its emptiness read, not just its presence: it means the scan
 * TIMED OUT carrying what it had. Empty means it learned nothing, so it is a
 * failure wearing a success's status string.
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
  const found = Array.isArray(payload.duplicates) ? (payload.duplicates as DuplicateCode[]) : null

  // `success` is a real answer even when the list is empty: the scan ran and
  // found nothing, which is the one case allowed to render "none found".
  if (payload.status === 'success' && found) {
    return { state: 'done', duplicates: found }
  }

  // `partial` is a TIMEOUT carrying whatever was found before the clock ran out,
  // so its emptiness is the whole question. With rows, it is a real (if
  // incomplete) result. With NO rows the scan learned nothing, and calling that
  // 'done' is the same defect as reading a failed scan as "0 duplicates" -- the
  // exact thing this module exists to stop, surviving in the branch nobody
  // separated. Measured against the live backend on 2026-10-07, which is the
  // shape this codebase actually produces:
  //   {"status":"partial","message":"Analysis timed out after 120.0s...",
  //    "duplicates":[],"total_count":0,"storage_type":"timeout"}
  if (payload.status === 'partial' && found) {
    return found.length > 0
      ? { state: 'done', duplicates: found }
      : { state: 'failed', duplicates: [] }
  }

  return { state: payload.status === 'error' ? 'failed' : 'not_scanned', duplicates: [] }
}
