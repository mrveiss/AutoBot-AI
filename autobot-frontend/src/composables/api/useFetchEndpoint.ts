// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useFetchEndpoint
 *
 * Generic single-call fetcher that collapses the loading / error /
 * status-branch / assign boilerplate repeated across Vue composables.
 *
 * Originally shipped as `analytics/useAnalyticsEndpoint` (#5112). Rehomed
 * here per the audit in #5154 so non-analytics callers (workflow templates,
 * pattern analysis, landing pages) can use it without the source-scoping
 * friction baked into the analytics default.
 *
 * Differences vs the analytics-domain alias:
 *   - `deps` is OPTIONAL.           (analytics alias: required)
 *   - `scopeToSource` defaults FALSE. (analytics alias: true, preserving #5111)
 *   - `withSourceId` defaults to identity (no-op) when deps is omitted.
 *
 * Source-scoping stays explicit: `scopeToSource: true` + a `deps.withSourceId`
 * injection point. The analytics alias flips the default back for its own
 * callers so the #5111 bug class remains structurally prevented there.
 *
 * Issue #5153 scope C.
 */

import { ref, type Ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useFetchEndpoint')

export type FetchEndpointMethod = 'GET' | 'POST' | 'DELETE'

export interface UseFetchEndpointOptions<TRaw, TOut, Ctx = undefined> {
  /** API path appended to the resolved backend URL, e.g. '/api/analytics/codebase/stats'. */
  path: string
  /** HTTP method. Defaults to 'GET'. */
  method?: FetchEndpointMethod
  /**
   * Factory returning the JSON body to send. Called at each `load()` so it
   * reads fresh reactive state. Serialised when `method` is anything other
   * than 'GET' (POST and DELETE both accept a body; DELETE without a body
   * simply omits it).
   */
  body?: () => unknown
  /**
   * When `true`, wraps the URL with `deps.withSourceId(...)` before fetching.
   *
   * Defaults to **false** at this (generic) layer. The analytics-domain
   * alias flips the default to `true` because forgetting to scope is a
   * known recurring bug class there (#5111).
   */
  scopeToSource?: boolean
  /**
   * Reducer from raw JSON to the target data type.
   * Return `null` to indicate "no data" (leaves `data` as null without error).
   */
  pickData: (raw: TRaw) => TOut | null
  /**
   * Optional side-effect fired after `data` is assigned on success.
   *
   * Issue #5457: receives the per-request `context` passed to `load()`.
   * Lets callers thread request-scope state (filename hints, user-action
   * tags, etc.) into the success handler without module-scope `let`
   * workarounds — see the #5455 exportReport race this addresses.
   */
  onSuccess?: (data: TOut, raw: TRaw, context: Ctx) => void
  /** Optional side-effect fired when `pickData` returns null (no-data path). */
  onNoData?: (context: Ctx) => void
  /**
   * Optional side-effect fired when fetch fails or throws. Receives the
   * resolved error message (same value that lands in `error.value`) plus
   * the per-request `context` (#5457).
   */
  onError?: (message: string, err: unknown, context: Ctx) => void
  /**
   * Hook fired with the raw Response **before** the default `!ok` throw.
   * Return a string to override the default `${label} returned ${status}`
   * error message (useful for status-specific copy like 504 -> "timeout"
   * or for parsing a `{ detail }` JSON body). Return `undefined` / void
   * to fall through to the default error handling.
   *
   * Only called when `response.ok === false`. Does NOT prevent the throw
   * — the return value only shapes the error message that ends up in
   * `error.value` and in `onError(message, err)`.
   *
   * Introduced in #5235 to unblock migration of fetchers with special-
   * case error handling (504 timeout copy, `detail` field extraction).
   */
  onResponse?: (
    response: Response,
    context: Ctx,
  ) => string | undefined | Promise<string | undefined>
  /**
   * Custom response parser. Defaults to `(r) => r.json()`. Override to
   * handle non-JSON responses — e.g. `text/markdown` exports (see
   * `useCodebaseExport.exportReport`), CSV exports, blobs, etc.
   *
   * The returned value is passed verbatim to `pickData(raw)`, so the
   * `TRaw` type parameter should reflect whatever shape the custom
   * parser yields.
   *
   * Introduced in #5276 so fetchers returning non-JSON can route
   * through the same loading/error/assign plumbing as JSON fetchers.
   */
  parseResponse?: (response: Response) => Promise<TRaw>
  /**
   * Graceful-degradation value returned when the fetch fails. When
   * provided:
   *   - On any failure (network error, `!ok`, parser throw, etc.)
   *     `data.value` is set to `fallbackData` (or its factory result).
   *   - `error.value` remains empty (no user-visible error).
   *   - `onError` still fires so callers can log or surface a warning.
   *
   * Useful for export endpoints where a stale cached value is
   * preferable to a user-visible error (see
   * `useCodebaseExport._fetchEnvironmentExportData`).
   *
   * Default absence preserves the existing strict error behavior.
   *
   * Introduced in #5389.
   */
  fallbackData?: TOut | (() => TOut)
  /** Human-readable label used only for log messages. */
  label?: string
}

export interface UseFetchEndpointDeps {
  /**
   * Wraps the URL when `scopeToSource: true`. Optional — defaults to
   * identity (no-op) so non-analytics callers don't need a shim.
   */
  withSourceId?: (url: string) => string
}

export interface UseFetchEndpointReturn<TOut, Ctx = undefined> {
  data: Ref<TOut | null>
  loading: Ref<boolean>
  error: Ref<string>
  /**
   * Trigger the fetch.
   *
   * @param queryExtras - Optional extra query-string params appended to the URL.
   * @param context - Optional per-request context threaded into the
   *   lifecycle callbacks (`onSuccess`/`onError`/`onNoData`/`onResponse`).
   *   Introduced in #5457 to eliminate module-scope `let` workarounds for
   *   request-specific state like filename hints.
   */
  load: (queryExtras?: Record<string, string>, context?: Ctx) => Promise<void>
  /**
   * Clear `data`, `loading`, and `error` back to their initial state.
   * Parity with the deleted `useAnalyticsFetch` (#5208/#5235).
   */
  reset: () => void
}

function appendQueryExtras(
  url: string,
  extras?: Record<string, string>,
): string {
  if (!extras) return url
  const entries = Object.entries(extras).filter(
    ([, v]) => v !== undefined && v !== null && v !== '',
  )
  if (entries.length === 0) return url
  const sep = url.includes('?') ? '&' : '?'
  const qs = entries
    .map(
      ([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`,
    )
    .join('&')
  return `${url}${sep}${qs}`
}

export function useFetchEndpoint<TRaw, TOut, Ctx = undefined>(
  opts: UseFetchEndpointOptions<TRaw, TOut, Ctx>,
  deps?: UseFetchEndpointDeps,
): UseFetchEndpointReturn<TOut, Ctx> {
  const data = ref<TOut | null>(null) as Ref<TOut | null>
  const loading = ref(false)
  const error = ref('')

  const scopeToSource = opts.scopeToSource === true
  const method: FetchEndpointMethod = opts.method ?? 'GET'
  const label = opts.label ?? opts.path

  if (scopeToSource && !deps?.withSourceId) {
    // Caller opted in to source scoping but didn't wire the injector.
    // Fall back to identity so we don't throw at mount time, but log loudly
    // so the misconfiguration is visible.
    logger.warn(
      `scopeToSource=true but no deps.withSourceId provided for ${label}; falling back to identity (no scoping applied)`,
    )
  }
  const withSourceId = deps?.withSourceId ?? ((u: string) => u)

  const load = async (
    queryExtras?: Record<string, string>,
    context?: Ctx,
  ): Promise<void> => {
    // #5457: context is captured into the closure at load-time, so
    // concurrent load() calls each see their own context in callbacks —
    // no module-scope `let` workaround needed. The `as Ctx` cast is safe
    // because when `Ctx = undefined` (the default) the optional parameter
    // fills the slot correctly.
    const ctx = context as Ctx
    loading.value = true
    error.value = ''
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      let url = `${backendUrl}${opts.path}`
      if (scopeToSource) {
        url = withSourceId(url)
      }
      url = appendQueryExtras(url, queryExtras)

      const init: RequestInit = {
        method,
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      }
      if (method !== 'GET' && opts.body) {
        init.body = JSON.stringify(opts.body())
      }
      const response = await fetchWithAuth(url, init)
      if (!response.ok) {
        const overrideMsg = opts.onResponse
          ? await opts.onResponse(response, ctx)
          : undefined
        throw new Error(
          overrideMsg ?? `${label} returned ${response.status}`,
        )
      }
      const raw = opts.parseResponse
        ? await opts.parseResponse(response)
        : ((await response.json()) as TRaw)
      const picked = opts.pickData(raw)
      if (picked === null) {
        data.value = null
        opts.onNoData?.(ctx)
        return
      }
      data.value = picked
      opts.onSuccess?.(picked, raw, ctx)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      logger.error(`Failed to load ${label}:`, err)
      opts.onError?.(message, err, ctx)
      // #5389: when a fallback value is configured, return it as the
      // effective result instead of exposing the error. Callers opting
      // into this explicitly accept "success with stale/default data"
      // over "user-visible error" semantics.
      if (opts.fallbackData !== undefined) {
        const fallback =
          typeof opts.fallbackData === 'function'
            ? (opts.fallbackData as () => TOut)()
            : opts.fallbackData
        data.value = fallback
        error.value = ''
      } else {
        error.value = message
        data.value = null
      }
    } finally {
      loading.value = false
    }
  }

  const reset = (): void => {
    data.value = null
    loading.value = false
    error.value = ''
  }

  return { data, loading, error, load, reset }
}
