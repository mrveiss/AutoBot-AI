// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useDebouncedSearch Composable
 *
 * Primitive for debounced, race-safe async search driven by a reactive query.
 *
 * Consolidates the input-watcher + loading-state + empty-query-guard pattern
 * duplicated across 4 KB components (KnowledgeSearch, KnowledgeEntries,
 * KnowledgeBrowser, KnowledgeCategories). See issue #5198.
 *
 * Features:
 * - Debounced execution via `useDebouncedFn`
 * - Min-length guard (skips onSearch for short queries, clears results)
 * - Race protection: last-caller-wins via monotonic call id
 * - `isSearching` loading ref toggled around onSearch
 * - `error` ref populated on thrown exceptions
 * - `flush()` bypasses debounce; `cancel()` stops future state updates
 * - Automatic cleanup via `onScopeDispose`
 *
 * @example
 * ```typescript
 * const query = ref('')
 * const { results, isSearching, error } = useDebouncedSearch(
 *   query,
 *   async (q) => api.search(q),
 *   { delayMs: 350, minLength: 2 }
 * )
 * ```
 */

import { ref, readonly, watch, onScopeDispose, getCurrentScope, type Ref } from 'vue'
import { useDebouncedFn } from './useDebounce'

export interface UseDebouncedSearchOptions {
  /** Debounce delay in milliseconds. Default: 350 */
  delayMs?: number
  /** Minimum trimmed query length before onSearch fires. Shorter queries clear results. Default: 1 */
  minLength?: number
  /** If true, the query watcher fires immediately with the current value. Default: false */
  immediate?: boolean
}

export interface UseDebouncedSearchReturn<T> {
  results: Readonly<Ref<T | null>>
  isSearching: Readonly<Ref<boolean>>
  error: Readonly<Ref<Error | null>>
  flush: () => void
  cancel: () => void
}

export function useDebouncedSearch<T>(
  query: Ref<string>,
  onSearch: (q: string) => Promise<T>,
  options: UseDebouncedSearchOptions = {}
): UseDebouncedSearchReturn<T> {
  const { delayMs = 350, minLength = 1, immediate = false } = options

  const results = ref<T | null>(null) as Ref<T | null>
  const isSearching = ref(false)
  const error = ref<Error | null>(null)
  let callId = 0
  let cancelled = false

  async function doSearch(q: string): Promise<void> {
    const trimmed = q.trim()
    if (trimmed.length < minLength) {
      results.value = null
      isSearching.value = false
      return
    }
    const myCallId = ++callId
    isSearching.value = true
    error.value = null
    try {
      const result = await onSearch(trimmed)
      if (myCallId !== callId || cancelled) return
      results.value = result
    } catch (err) {
      if (myCallId !== callId || cancelled) return
      error.value = err instanceof Error ? err : new Error(String(err))
    } finally {
      if (myCallId === callId && !cancelled) isSearching.value = false
    }
  }

  const { debouncedFn: debounced } = useDebouncedFn(doSearch, delayMs)

  watch(
    query,
    (q) => {
      if (!cancelled) debounced(q)
    },
    { immediate }
  )

  function flush(): void {
    void doSearch(query.value)
  }

  function cancel(): void {
    cancelled = true
    isSearching.value = false
  }

  if (getCurrentScope()) onScopeDispose(cancel)

  return {
    results: readonly(results) as Readonly<Ref<T | null>>,
    isSearching: readonly(isSearching),
    error: readonly(error),
    flush,
    cancel
  }
}
