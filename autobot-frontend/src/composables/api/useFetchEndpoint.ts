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

export type FetchEndpointMethod = 'GET' | 'POST'

export interface UseFetchEndpointOptions<TRaw, TOut> {
  /** API path appended to the resolved backend URL, e.g. '/api/analytics/codebase/stats'. */
  path: string
  /** HTTP method. Defaults to 'GET'. */
  method?: FetchEndpointMethod
  /**
   * Factory returning the JSON body to send. Called at each `load()` so it
   * reads fresh reactive state. Ignored when `method === 'GET'`.
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
  /** Optional side-effect fired after `data` is assigned on success. */
  onSuccess?: (data: TOut, raw: TRaw) => void
  /** Optional side-effect fired when `pickData` returns null (no-data path). */
  onNoData?: () => void
  /**
   * Optional side-effect fired when fetch fails or throws. Receives the
   * resolved error message (same value that lands in `error.value`).
   */
  onError?: (message: string, err: unknown) => void
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

export interface UseFetchEndpointReturn<TOut> {
  data: Ref<TOut | null>
  loading: Ref<boolean>
  error: Ref<string>
  load: (queryExtras?: Record<string, string>) => Promise<void>
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

export function useFetchEndpoint<TRaw, TOut>(
  opts: UseFetchEndpointOptions<TRaw, TOut>,
  deps?: UseFetchEndpointDeps,
): UseFetchEndpointReturn<TOut> {
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
  ): Promise<void> => {
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
      if (method === 'POST' && opts.body) {
        init.body = JSON.stringify(opts.body())
      }
      const response = await fetchWithAuth(url, init)
      if (!response.ok) {
        throw new Error(`${label} returned ${response.status}`)
      }
      const raw = (await response.json()) as TRaw
      const picked = opts.pickData(raw)
      if (picked === null) {
        data.value = null
        opts.onNoData?.()
        return
      }
      data.value = picked
      opts.onSuccess?.(picked, raw)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      logger.error(`Failed to load ${label}:`, err)
      error.value = message
      data.value = null
      opts.onError?.(message, err)
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, load }
}
