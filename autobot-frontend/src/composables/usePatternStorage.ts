// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Pattern storage reads and the report fetch, scoped to the selected source (#20513).
 *
 * Split out of `usePatternAnalysis.ts`, a grandfathered file that may not grow. Each call asks
 * `hasSource` first: the routes answer 422 without a `source_id`, so with no source selected
 * nothing is requested.
 *
 * Author: mrveiss
 */

import type { Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { extractErrorMessage } from '@/utils/errorExtract'
import type { PatternStorageStats } from '@/composables/usePatternAnalysis'

const logger = createLogger('usePatternStorage')

export interface PatternStorageDeps {
  withSourceId: (url: string) => string
  hasSource: (url: string, what: string) => boolean
  wrap: <T>(fn: () => Promise<T>) => Promise<T>
  error: Ref<string | null>
  storageStats: Ref<PatternStorageStats | null>
}

export function usePatternStorage(deps: PatternStorageDeps) {
  const { withSourceId, hasSource, wrap, error, storageStats } = deps

  /**
   * Get pattern storage stats
   */
  const getStorageStats = async (): Promise<void> => {
    await wrap(async () => {
      const url = withSourceId('/api/analytics/codebase/patterns/storage/stats')
      if (!hasSource(url, 'pattern storage stats')) return
      const data = await apiClient.get<{ status: string; stats?: PatternStorageStats }>(url)
      if (data.status === 'success') {
        storageStats.value = data.stats ?? null
      }
    }).catch((e: unknown) => {
      logger.error('Storage stats fetch failed:', e)
    })
  }

  /**
   * Clear pattern storage
   */
  const clearStorage = async (): Promise<boolean> => {
    return wrap(async () => {
      // Handler returns {message} on 2xx and raises on failure (no status field).
      const url = withSourceId('/api/analytics/codebase/patterns/storage/clear')
      if (!hasSource(url, 'pattern storage clear')) return false
      await apiClient.post(url)
      storageStats.value = null
      return true
    }).catch((e: unknown) => {
      error.value = extractErrorMessage(e, 'Clearing the stored patterns failed')
      logger.error('Clear storage failed:', e)
      return false
    })
  }

  /**
   * Get markdown report
   */
  const getReport = async (path?: string): Promise<string | null> => {
    return wrap(async () => {
      const params = path ? `?path=${encodeURIComponent(path)}` : ''
      const url = withSourceId(`/api/analytics/codebase/patterns/report${params}`)
      if (!hasSource(url, 'pattern report')) return null
      const data = await apiClient.get<{ status: string; report?: string }>(url)
      if (data.status === 'success') {
        return data.report ?? null
      }
      return null
    }).catch((e: unknown) => {
      error.value = extractErrorMessage(e, 'Report fetch failed')
      logger.error('Report fetch failed:', e)
      return null
    })
  }

  return { getStorageStats, clearStorage, getReport }
}
