// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Latest-request ownership (#21159): a monotonic token so only the most recent request of a kind may write
 * shared state. `begin()` claims ownership, `invalidate()` revokes it (close, session switch), and a reply
 * checks `isCurrent(token)` before touching state.
 */
export function useLatestRequest() {
  let current = 0
  return {
    begin: (): number => ++current,
    invalidate: (): void => {
      current++
    },
    isCurrent: (token: number): boolean => token === current
  }
}
