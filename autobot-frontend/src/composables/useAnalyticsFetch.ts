/**
 * Generic analytics fetch composable (#1321).
 *
 * Wraps fetchWithAuth with reactive loading/error/data state.
 * Replaces repetitive loadXxx() functions in CodebaseAnalytics.
 *
 * Usage:
 *   const { data, loading, error, load } = useAnalyticsFetch<SecurityFindings[]>(
 *     '/api/code-intelligence/security/analyze',
 *   )
 *   await load()   // data.value now holds the parsed JSON
 *
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, type Ref } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { getConfig } from '@/config/ssot-config'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useAnalyticsFetch')

async function getBackendUrl(): Promise<string> {
  try {
    return await appConfig.getServiceUrl('backend')
  } catch (_e) {
    logger.warn('AppConfig failed, using SSOT config backend URL')
    return getConfig().backendUrl
  }
}

export interface AnalyticsFetchOptions {
  /** HTTP method (default: GET). */
  method?: 'GET' | 'POST'
}

export interface AnalyticsFetchReturn<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  load: (
    query?: Record<string, string>,
    body?: Record<string, unknown>,
  ) => Promise<T | null>
  reset: () => void
}

/**
 * Reusable composable for direct-fetch analytics endpoints.
 *
 * @param path     API path (e.g. `/api/analytics/codebase/declarations`).
 * @param extract  Transform applied to the JSON response before storing.
 *                 Return `undefined` to signal "no data" (sets data to null).
 * @param opts     Optional fetch options (method).
 */
export function useAnalyticsFetch<T = Record<string, unknown>>(
  path: string,
  extract?: (json: Record<string, unknown>) => T | undefined,
  opts?: AnalyticsFetchOptions,
): AnalyticsFetchReturn<T> {
  const data: Ref<T | null> = ref(null)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)

  const method = opts?.method ?? 'GET'

  const load = async (
    query?: Record<string, string>,
    body?: Record<string, unknown>,
  ): Promise<T | null> => {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const qs = query
        ? '?' + new URLSearchParams(query).toString()
        : ''
      const fetchOpts: RequestInit = {
        method,
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      }
      if (body) {
        fetchOpts.body = JSON.stringify(body)
      }
      const resp = await fetchWithAuth(
        `${backendUrl}${path}${qs}`,
        fetchOpts,
      )
      if (!resp.ok) {
        throw new Error(`${resp.status} ${resp.statusText}`)
      }
      const json = await resp.json()
      if (extract) {
        const extracted = extract(json)
        data.value = extracted !== undefined ? extracted : null
      } else {
        data.value = json as T
      }
      return data.value
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      error.value = msg
      logger.error(`Failed to load ${path}: ${msg}`)
      return null
    } finally {
      loading.value = false
    }
  }

  const reset = () => {
    data.value = null
    loading.value = false
    error.value = null
  }

  return { data, loading, error, load, reset }
}

export default useAnalyticsFetch
