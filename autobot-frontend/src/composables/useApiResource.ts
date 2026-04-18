// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useApiResource
 *
 * Generic wrapper around any async fetcher that exposes reactive `data`,
 * `error`, `isLoading` refs plus a `refresh()` method. Designed to eliminate
 * the imperative "loading ref + try/catch + assign" boilerplate that every
 * fetch-style composable in `useKnowledgeBase.ts` (#5149) reimplements.
 *
 * Typical use with the typed ApiClient:
 *
 *   const stats = useApiResource<KnowledgeStats>(() =>
 *     apiClient.get<KnowledgeStats>(`${getApiBase()}/knowledge_base/stats`)
 *   )
 *   onMounted(stats.refresh)
 *   // stats.data.value, stats.error.value, stats.isLoading.value are reactive
 *
 * Prior art in this repo: `composables/analytics/useAnalyticsEndpoint.ts`
 * solves a narrower problem (fetchWithAuth + path + source-scoping). This
 * composable is the generic form — any fetcher callback, no URL assumptions.
 *
 * Issue #5149.
 */

import { ref, getCurrentScope, onScopeDispose, type Ref } from 'vue'

export interface UseApiResourceOptions {
  /** Trigger `refresh()` immediately on composable creation. Default: false. */
  immediate?: boolean
  /**
   * Keep the previous `data` value visible while the next `refresh()` is in
   * flight. Default: true — matches what most UIs want (avoid flicker).
   * Set to false to clear `data` before each refresh.
   */
  keepPreviousData?: boolean
}

export interface UseApiResourceReturn<T> {
  /** The latest successful result, or `null` before the first success. */
  data: Ref<T | null>
  /** The last error from `refresh()`, cleared on successful refetch. */
  error: Ref<Error | null>
  /** True while a `refresh()` call is in flight. */
  isLoading: Ref<boolean>
  /** Invoke the fetcher. Resolves after state has been updated. */
  refresh: () => Promise<void>
}

/**
 * Wrap an async fetcher to get reactive loading/error/data refs.
 *
 * Race-condition handling: if `refresh()` is called again before the previous
 * call resolves, the older call's result is discarded once it lands. The last
 * caller wins. This prevents stale data from overwriting fresh data when a
 * consumer fires refresh() multiple times in quick succession.
 *
 * Lifecycle: on `onScopeDispose` (component unmount / effect scope teardown),
 * any pending fetches are effectively ignored — their resolutions no longer
 * touch the refs. This prevents the classic "setState on unmounted component"
 * warning and any memory leak from stale closures.
 */
export function useApiResource<T>(
  fetcher: () => Promise<T>,
  options: UseApiResourceOptions = {}
): UseApiResourceReturn<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref<Error | null>(null)
  const isLoading = ref(false)

  const keepPreviousData = options.keepPreviousData !== false

  // Monotonic ID for race-condition tracking. Incremented per refresh() call.
  // When a fetch resolves, we ignore it unless its ID still matches the latest.
  let latestCallId = 0
  let disposed = false

  const refresh = async (): Promise<void> => {
    const callId = ++latestCallId
    isLoading.value = true
    error.value = null
    if (!keepPreviousData) {
      data.value = null
    }

    try {
      const result = await fetcher()
      if (disposed || callId !== latestCallId) return
      data.value = result
    } catch (e) {
      if (disposed || callId !== latestCallId) return
      error.value = e instanceof Error ? e : new Error(String(e))
    } finally {
      if (disposed || callId !== latestCallId) return
      isLoading.value = false
    }
  }

  // Only register the disposer if called inside an effect scope (e.g. a Vue
  // component setup). Calling onScopeDispose outside a scope emits a warning
  // and does nothing — guarding here keeps unit tests quiet and the callsite
  // contract unchanged.
  if (getCurrentScope()) {
    onScopeDispose(() => {
      disposed = true
    })
  }

  if (options.immediate) {
    // Fire-and-forget — caller can still `await refresh()` later; we don't
    // want `useApiResource` itself to be async.
    refresh()
  }

  return { data, error, isLoading, refresh }
}
