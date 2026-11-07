// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Pattern storage reads and the report fetch, scoped to the selected source (#20513).
 *
 * Split out of `usePatternAnalysis.ts`, a grandfathered file that may not grow. The routes answer
 * 422 without a `source_id`, so with no source selected nothing is requested: storage stats and
 * clear and the report read all go through `useFetchEndpoint({ scopeToSource, requireSource })`,
 * which skips the request itself.
 *
 * Author: mrveiss
 */

import type { Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { extractErrorMessage, extractResponseErrorDetail } from '@/utils/errorExtract'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import type { PatternStorageStats } from '@/composables/usePatternAnalysis'

const logger = createLogger('usePatternStorage')

export interface PatternStorageDeps {
  withSourceId: (url: string) => string
  wrap: <T>(fn: () => Promise<T>) => Promise<T>
  error: Ref<string | null>
  storageStats: Ref<PatternStorageStats | null>
}

export function usePatternStorage(deps: PatternStorageDeps) {
  const { withSourceId, wrap, error, storageStats } = deps

  const statsEndpoint = useFetchEndpoint<{ status: string; stats?: PatternStorageStats }, PatternStorageStats>(
    {
      path: '/api/analytics/codebase/patterns/storage/stats',
      scopeToSource: true,
      requireSource: true,
      pickData: (raw) => (raw.status === 'success' ? (raw.stats ?? null) : null),
      onSuccess: (stats) => {
        storageStats.value = stats
      },
      label: 'Pattern storage stats',
    },
    { withSourceId },
  )

  // Handler returns {message} on 2xx and raises on failure (no status field).
  let cleared = false
  const clearEndpoint = useFetchEndpoint<unknown, true>(
    {
      path: '/api/analytics/codebase/patterns/storage/clear',
      method: 'POST',
      scopeToSource: true,
      requireSource: true,
      pickData: () => true,
      onSuccess: () => {
        cleared = true
        storageStats.value = null
      },
      onResponse: async (response) => (await extractResponseErrorDetail(response)) || undefined,
      onError: (_message, err) => {
        error.value = extractErrorMessage(err, 'Clearing the stored patterns failed')
      },
      label: 'Pattern storage clear',
    },
    { withSourceId },
  )

  /**
   * Get pattern storage stats
   */
  const getStorageStats = async (): Promise<void> => {
    await wrap(() => statsEndpoint.load()).catch((e: unknown) => {
      logger.error('Storage stats fetch failed:', e)
    })
  }

  /**
   * Clear pattern storage
   */
  const clearStorage = async (): Promise<boolean> => {
    cleared = false
    await wrap(() => clearEndpoint.load()).catch((e: unknown) => {
      error.value = extractErrorMessage(e, 'Clearing the stored patterns failed')
      logger.error('Clear storage failed:', e)
    })
    return cleared
  }

  let reportText: string | null = null
  const reportEndpoint = useFetchEndpoint<{ status: string; report?: string }, string>(
    {
      path: '/api/analytics/codebase/patterns/report',
      scopeToSource: true,
      requireSource: true,
      pickData: (raw) => (raw.status === 'success' ? (raw.report ?? null) : null),
      onSuccess: (report) => {
        reportText = report
      },
      onError: (_message, err) => {
        error.value = extractErrorMessage(err, 'Report fetch failed')
      },
      label: 'Pattern report',
    },
    { withSourceId },
  )

  /**
   * Get markdown report
   */
  const getReport = async (path?: string): Promise<string | null> => {
    reportText = null
    await wrap(() => reportEndpoint.load(path ? { path } : undefined)).catch((e: unknown) => {
      error.value = extractErrorMessage(e, 'Report fetch failed')
      logger.error('Report fetch failed:', e)
    })
    return reportText
  }

  return { getStorageStats, clearStorage, getReport }
}
