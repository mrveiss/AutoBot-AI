// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'
import type { Ref } from 'vue'

/**
 * Lightweight composable that eliminates the manual isLoading boilerplate:
 *   isLoading.value = true
 *   try { ... } finally { isLoading.value = false }
 *
 * Usage:
 *   const { isLoading, wrap } = useLoadingState()
 *   async function doSomething() {
 *     return wrap(() => ApiClient.post('/endpoint', payload))
 *   }
 *
 * --- When to use this vs useFetchEndpoint ---
 *
 * Use `useLoadingState` when:
 *   - The call is a mutation (POST/DELETE/PUT) triggered by a user action
 *   - You are using `ApiClient` (which handles auth/retry/timeout internally)
 *   - You don't need abort-on-unmount, race-condition guards, or reactive `data`
 *   - The result is consumed inline inside the same function that called `wrap()`
 *
 * Use `useFetchEndpoint` (built on `useApiResource`) when:
 *   - The call is a read (GET) that populates reactive `data` displayed in the UI
 *   - You need abort-on-component-unmount to prevent "update after dispose" bugs
 *   - You need race-condition safety (rapid refresh() calls — last writer wins)
 *   - You need `keepPreviousData`, `fallbackData`, or `onSuccess`/`onError` hooks
 *
 * Long-term consolidation path: tracked in issue #5884. The two patterns coexist
 * intentionally — `ApiClient` composables are mutation-oriented and the `wrap()`
 * API is more ergonomic for that use case. Full migration to `useFetchEndpoint`
 * for reads is the eventual goal but is deferred until `ApiClient` can forward
 * its AbortSignal externally.
 *
 * See docs/developer/COMPOSABLE_HTTP_PATTERNS.md for the full decision guide.
 */
export function useLoadingState(initial = false): {
  isLoading: Ref<boolean>
  wrap: <T>(fn: () => Promise<T>) => Promise<T>
} {
  let _pending = 0
  const isLoading = ref(initial)

  async function wrap<T>(fn: () => Promise<T>): Promise<T> {
    if (++_pending === 1) isLoading.value = true
    try {
      return await fn()
    } finally {
      if (--_pending === 0) isLoading.value = false
    }
  }

  return { isLoading, wrap }
}

export default useLoadingState
