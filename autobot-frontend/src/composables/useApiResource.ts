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
 * Fetchers that want abort support accept an AbortSignal:
 *
 *   const stats = useApiResource<KnowledgeStats>((signal) =>
 *     apiClient.get<KnowledgeStats>(`${getApiBase()}/knowledge_base/stats`, { signal })
 *   )
 *
 * Prior art in this repo: `composables/analytics/useAnalyticsEndpoint.ts`
 * solves a narrower problem (fetchWithAuth + path + source-scoping). This
 * composable is the generic form — any fetcher callback, no URL assumptions.
 *
 * Issue #5149. AbortController integration: #5179.
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
  /**
   * Abort the prior in-flight request when `refresh()` is called again.
   * Default: true. The signal is always passed to the fetcher as the first
   * argument — JS allows passing extra arguments to functions that do not
   * declare them, so zero-arg fetchers remain fully backward compatible.
   */
  abortPrior?: boolean
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
  /**
   * Abort the current in-flight request (if any) and immediately clear
   * `isLoading`. Safe to call when no request is in flight. Advances the
   * internal call-ID counter so the in-flight finally block exits early
   * without touching the refs.
   */
  abort: () => void
}

/**
 * Wrap an async fetcher to get reactive loading/error/data refs.
 *
 * Race-condition handling: if `refresh()` is called again before the previous
 * call resolves, the older call's result is discarded once it lands. The last
 * caller wins. This prevents stale data from overwriting fresh data when a
 * consumer fires refresh() multiple times in quick succession.
 *
 * Network efficiency: when `abortPrior` is true (default), each new refresh()
 * call aborts the previous in-flight request via AbortController so no
 * redundant network requests complete in the background.
 *
 * Lifecycle: on `onScopeDispose` (component unmount / effect scope teardown),
 * any pending fetches are aborted and their resolutions no longer touch the
 * refs. This prevents the classic "setState on unmounted component" warning
 * and any memory leak from stale closures.
 */
export function useApiResource<T>(
  fetcher: ((signal: AbortSignal) => Promise<T>) | (() => Promise<T>),
  options: UseApiResourceOptions = {}
): UseApiResourceReturn<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref<Error | null>(null)
  const isLoading = ref(false)

  const keepPreviousData = options.keepPreviousData !== false
  const abortPrior = options.abortPrior !== false

  // Monotonic ID for race-condition tracking. Incremented per refresh() call.
  // When a fetch resolves, we ignore it unless its ID still matches the latest.
  let latestCallId = 0
  let disposed = false
  // Tracks the AbortController for the current in-flight request.
  let currentController: AbortController | null = null

  const refresh = async (): Promise<void> => {
    // Abort the previous in-flight request before starting a new one.
    if (abortPrior && currentController !== null) {
      currentController.abort()
    }

    const controller = abortPrior ? new AbortController() : null
    currentController = controller

    const callId = ++latestCallId
    isLoading.value = true
    error.value = null
    if (!keepPreviousData) {
      data.value = null
    }

    try {
      // Always pass the signal when we have a controller. JS allows passing
      // extra arguments to functions that do not declare them — zero-arg
      // fetchers remain fully backward compatible (#5801: drop fetcher.length
      // check which was broken for optional-parameter fetchers because
      // Function.prototype.length counts only REQUIRED parameters).
      const result =
        controller !== null
          ? await (fetcher as (signal?: AbortSignal) => Promise<T>)(
              controller.signal
            )
          : await (fetcher as () => Promise<T>)()

      if (disposed || callId !== latestCallId) return
      data.value = result
    } catch (e) {
      // AbortError means this call was superseded — not a real failure.
      // Guard by name only: DOMException is not an Error subclass in jsdom,
      // and some fetch polyfills throw plain Error objects with name='AbortError'.
      if (e != null && (e as { name?: unknown }).name === 'AbortError') return
      if (disposed || callId !== latestCallId) return
      error.value = e instanceof Error ? e : new Error(String(e))
    } finally {
      // Only clear the loading state for the call that is still current.
      if (!disposed && callId === latestCallId) {
        isLoading.value = false
        if (currentController === controller) {
          currentController = null
        }
      }
    }
  }

  const abort = (): void => {
    if (currentController !== null) {
      currentController.abort()
      currentController = null
    }
    // Advance the call ID so the in-flight finally block sees a stale ID and
    // exits without touching isLoading or data.
    latestCallId++
    isLoading.value = false
  }

  // Only register the disposer if called inside an effect scope (e.g. a Vue
  // component setup). Calling onScopeDispose outside a scope emits a warning
  // and does nothing — guarding here keeps unit tests quiet and the callsite
  // contract unchanged.
  if (getCurrentScope()) {
    onScopeDispose(() => {
      disposed = true
      if (currentController !== null) {
        currentController.abort()
        currentController = null
      }
    })
  }

  if (options.immediate) {
    // Fire-and-forget — caller can still `await refresh()` later; we don't
    // want `useApiResource` itself to be async.
    refresh()
  }

  return { data, error, isLoading, refresh, abort }
}
