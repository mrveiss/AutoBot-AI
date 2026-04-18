// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useAnalyticsEndpoint
 *
 * Generic GET-fetcher for analytics-style endpoints. Collapses the
 * 14x near-identical boilerplate that lived in useAnalyticsDataFetchers:
 *   loading flag → clear error → resolve backendUrl → withSourceId (opt-out)
 *   → fetchWithAuth → !ok throw → json() → status branching → assign
 *   → catch → finally.
 *
 * Key design: `scopeToSource` defaults to TRUE so forgetting to wire it
 * (the #5111 class of bugs) is impossible without an explicit opt-out.
 *
 * Issue #5112.
 */

import { ref, type Ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useAnalyticsEndpoint')

export type AnalyticsEndpointMethod = 'GET' | 'POST'

export interface UseAnalyticsEndpointOptions<TRaw, TOut> {
  /** API path appended to the resolved backend URL, e.g. '/api/analytics/codebase/stats'. */
  path: string
  /**
   * HTTP method. Defaults to 'GET'. Use 'POST' for action endpoints
   * (e.g. `/api/code-intelligence/analyze`) that accept a JSON body.
   */
  method?: AnalyticsEndpointMethod
  /**
   * Factory returning the JSON body to send. Called at each `load()` so it
   * can read fresh reactive state. Ignored when `method === 'GET'`.
   */
  body?: () => unknown
  /**
   * Whether to wrap the URL with `withSourceId()` before fetching.
   * Defaults to TRUE — opt-out only. #5111 was caused by forgetting this,
   * so the only way to skip source scoping is now an explicit `false`.
   */
  scopeToSource?: boolean
  /**
   * Reducer from raw JSON to the target data type.
   * Return `null` to indicate "no data" (leaves `data` as null without error).
   * Status-branching (success / no_data / indexing) lives here.
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

export interface UseAnalyticsEndpointDeps {
  withSourceId: (url: string) => string
}

export interface UseAnalyticsEndpointReturn<TOut> {
  data: Ref<TOut | null>
  loading: Ref<boolean>
  error: Ref<string>
  load: (queryExtras?: Record<string, string>) => Promise<void>
}

/**
 * Appends a query-extras map to a URL, preserving any existing query string
 * added by `withSourceId()`. Skips empty values.
 */
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
      ([k, v]) =>
        `${encodeURIComponent(k)}=${encodeURIComponent(v)}`,
    )
    .join('&')
  return `${url}${sep}${qs}`
}

export function useAnalyticsEndpoint<TRaw, TOut>(
  opts: UseAnalyticsEndpointOptions<TRaw, TOut>,
  deps: UseAnalyticsEndpointDeps,
): UseAnalyticsEndpointReturn<TOut> {
  const data = ref<TOut | null>(null) as Ref<TOut | null>
  const loading = ref(false)
  const error = ref('')

  const scopeToSource = opts.scopeToSource !== false
  const method: AnalyticsEndpointMethod = opts.method ?? 'GET'
  const label = opts.label ?? opts.path

  const load = async (
    queryExtras?: Record<string, string>,
  ): Promise<void> => {
    loading.value = true
    error.value = ''
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      let url = `${backendUrl}${opts.path}`
      if (scopeToSource) {
        url = deps.withSourceId(url)
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
