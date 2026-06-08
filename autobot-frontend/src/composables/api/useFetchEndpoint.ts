// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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
 * Internally implemented on top of `useApiResource` so race-condition
 * handling, in-flight abort, and lifecycle teardown from `useApiResource`
 * automatically benefit all callers (#5180).
 *
 * Issue #5153 scope C.
 */

import { computed, type Ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import { useApiResource } from '@/composables/useApiResource'

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

  // Per-call parameters updated by load() before each refresh(). The fetcher
  // closure reads from these so each call sees its own queryExtras + context
  // without requiring per-call arguments on the useApiResource fetcher
  // signature (#5457 context threading is preserved).
  let pendingExtras: Record<string, string> | undefined = undefined
  let pendingCtx: Ctx = undefined as Ctx

  // Internally implemented on top of useApiResource (#5180) — race-condition
  // handling (monotonic call IDs), AbortController abort-prior, and lifecycle
  // teardown on scope dispose are all inherited automatically.
  //
  // The fetcher returns `TOut | null`:
  //   - `TOut`  → success, data assigned by useApiResource
  //   - `null`  → no-data path (pickData returned null), data stays null, no error
  //   - throw   → error path; message is surfaced via resource.error
  //
  // fallbackData is handled by catching inside the fetcher and returning the
  // fallback value rather than re-throwing, so useApiResource sees a success.
  const resource = useApiResource<TOut | null>(async (signal: AbortSignal) => {
    const ctx = pendingCtx
    const queryExtras = pendingExtras

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
      signal, // forward the AbortSignal so fetchWithAuth cancels the network request
    }
    if (method !== 'GET' && opts.body) {
      init.body = JSON.stringify(opts.body())
    }

    try {
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
        opts.onNoData?.(ctx)
        return null
      }
      opts.onSuccess?.(picked, raw, ctx)
      return picked
    } catch (err: unknown) {
      // AbortError fires on reset()/disposal/rapid reload — not a real failure
      if (
        (err instanceof DOMException && err.name === 'AbortError') ||
        (err as Error)?.name === 'AbortError'
      ) return null
      const message = err instanceof Error ? err.message : String(err)
      logger.error(`Failed to load ${label}:`, err)
      opts.onError?.(message, err, ctx)
      // #5389: when fallbackData is configured, return it as the effective
      // result so useApiResource sees a success (data=fallback, no error).
      if (opts.fallbackData !== undefined) {
        const fallback =
          typeof opts.fallbackData === 'function'
            ? (opts.fallbackData as () => TOut)()
            : opts.fallbackData
        return fallback
      }
      throw err
    }
  }, { immediate: false })

  const load = async (
    queryExtras?: Record<string, string>,
    context?: Ctx,
  ): Promise<void> => {
    // Capture per-call params before delegating to useApiResource.refresh().
    // Because refresh() immediately reads these inside the fetcher closure,
    // and useApiResource serialises concurrent calls (abort-prior), there is
    // no window where a second load() can clobber the first's pending params
    // before the fetcher reads them.
    pendingExtras = queryExtras
    pendingCtx = context as Ctx
    await resource.refresh()
  }

  const reset = (): void => {
    resource.abort() // cancel any in-flight request and clear isLoading atomically
    resource.data.value = null
    resource.error.value = null
    // isLoading is now managed by resource.abort() — do NOT set it directly here
  }

  // Map useApiResource's shape to useFetchEndpoint's public API:
  //   isLoading  → loading  (name alias)
  //   error: Ref<Error|null> → error: Ref<string>  (type transform via computed)
  //
  // ComputedRef<string> satisfies Ref<string> structurally — both expose
  // `.value: string`. The cast below is safe: callers only read error.value;
  // internal mutation goes through resource.error.value (an Error|null ref).
  const loading = resource.isLoading
  const error = computed(() => resource.error.value?.message ?? '') as unknown as Ref<string>

  return { data: resource.data as Ref<TOut | null>, loading, error, load, reset }
}
