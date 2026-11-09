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
import i18n from '@/i18n'
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

  const t = (key: string): string => i18n.global.t(`analytics.patterns.${key}`) as string

  // The route answers the statistics at the top level; an unavailable store comes back as `{ error }`.
  const statsEndpoint = useFetchEndpoint<Partial<PatternStorageStats> & { error?: string }, PatternStorageStats>(
    {
      path: '/api/analytics/codebase/patterns/storage/stats',
      scopeToSource: true,
      requireSource: true,
      pickData: (raw) => {
        if (raw.error) throw new Error(raw.error)
        return typeof raw.total_patterns === 'number' ? (raw as PatternStorageStats) : null
      },
      onSuccess: (stats) => {
        storageStats.value = stats
      },
      // A failed stats read stays distinguishable from "nothing stored" (#17651).
      onError: (message) => {
        error.value = message || t('storageStatsFailed')
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
        error.value = extractErrorMessage(err, t('storageClearFailed'))
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
      error.value = extractErrorMessage(e, t('storageClearFailed'))
      logger.error('Clear storage failed:', e)
    })
    return cleared
  }

  let reportText: string | null = null
  // The route returns the Markdown report as text when asked for `format=markdown`.
  const reportEndpoint = useFetchEndpoint<string, string>(
    {
      path: '/api/analytics/codebase/patterns/report',
      scopeToSource: true,
      requireSource: true,
      parseResponse: (response) => response.text(),
      pickData: (raw) => raw || null,
      onSuccess: (report) => {
        reportText = report
      },
      onError: (_message, err) => {
        error.value = extractErrorMessage(err, t('reportFetchFailed'))
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
    await wrap(() => reportEndpoint.load({ format: 'markdown', ...(path ? { path } : {}) })).catch((e: unknown) => {
      error.value = extractErrorMessage(e, t('reportFetchFailed'))
      logger.error('Report fetch failed:', e)
    })
    return reportText
  }

  return { getStorageStats, clearStorage, getReport }
}
