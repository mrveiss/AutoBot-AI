// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * shareInFlight — callers that arrive while a call is pending share its promise (#13942).
 *
 * Extracted from OrgChart.vue (#14556). There, `fetchTree` and `loadExecutorRollup` both
 * resolve the company on mount; without sharing, both raced into their own
 * `GET /api/llc/companies/` fallback on the view most users land on.
 *
 * Only the *pending* promise is shared: it is released when it settles, so a later call (a
 * retry, say) runs `fn` again instead of reusing a stale answer.
 *
 * `fn` runs synchronously on the first call, as the inlined original did: callers that flush
 * promises after mounting rely on the request having started by then.
 */
export function shareInFlight<T>(fn: () => T | Promise<T>): () => Promise<T> {
  let pending: Promise<T> | null = null
  return () => {
    if (!pending) {
      let started: Promise<T>
      try {
        started = Promise.resolve(fn())
      } catch (err) {
        started = Promise.reject(err)
      }
      pending = started.finally(() => {
        pending = null
      })
    }
    return pending
  }
}
