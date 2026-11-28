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

import { watch, type Ref } from 'vue'
import i18n from '@/i18n'
import { createLogger } from '@/utils/debugUtils'
import { extractErrorMessage, extractResponseErrorDetail } from '@/utils/errorExtract'
import { sourceIdInUrl } from '@/utils/sourceIdInUrl'
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

  // The source the displayed statistics belong to. A clear is bound to it (#20513).
  const currentSource = (): string | null => sourceIdInUrl(withSourceId('/'))
  let statsSource: string | null = null

  const t = (key: string): string => i18n.global.t(key) as string

  // The route answers the statistics at the top level; an unavailable store comes back as `{ error }`.
  const statsEndpoint = useFetchEndpoint<Partial<PatternStorageStats> & { error?: string }, PatternStorageStats, string | null>(
    {
      path: '/api/analytics/codebase/patterns/storage/stats',
      scopeToSource: true,
      requireSource: true,
      pickData: (raw) => {
        if (raw.error) throw new Error(raw.error)
        return typeof raw.total_patterns === 'number' ? (raw as PatternStorageStats) : null
      },
      onSuccess: (stats, _raw, requestedSource) => {
        // A late answer for a source that is no longer selected must not restore its statistics.
        if (requestedSource !== currentSource()) return
        statsSource = requestedSource
        storageStats.value = stats
      },
      // A non-numeric total_patterns is "no data": drop statistics that may belong to an earlier answer.
      onNoData: () => {
        storageStats.value = null
        statsSource = null
      },
      // A failed stats read stays distinguishable from "nothing stored" (#17651).
      onError: (message) => {
        error.value = message || t('analytics.patterns.storageStatsFailed')
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
        statsSource = null
      },
      onResponse: async (response) => (await extractResponseErrorDetail(response)) || undefined,
      onError: (_message, err) => {
        error.value = extractErrorMessage(err, t('analytics.patterns.storageClearFailed'))
      },
      label: 'Pattern storage clear',
    },
    { withSourceId },
  )

  /**
   * Get pattern storage stats
   */
  const getStorageStats = async (): Promise<void> => {
    const requestedSource = currentSource()
    await wrap(() => statsEndpoint.load(undefined, requestedSource)).catch((e: unknown) => {
      logger.error('Storage stats fetch failed:', e)
    })
  }

  /**
   * Clear pattern storage
   */
  const clearStorage = async (): Promise<boolean> => {
    cleared = false
    // The statistics on screen are for another source than the one selected now: the request would
    // delete that other source's patterns. Drop the stale statistics and let the reload show the truth.
    if (storageStats.value && statsSource !== currentSource()) {
      storageStats.value = null
      statsSource = null
      return false
    }
    await wrap(() => clearEndpoint.load()).catch((e: unknown) => {
      error.value = extractErrorMessage(e, t('analytics.patterns.storageClearFailed'))
      logger.error('Clear storage failed:', e)
    })
    return cleared
  }

  // A source switch drops the previous source's statistics and reloads them for the new one.
  watch(currentSource, () => {
    storageStats.value = null
    statsSource = null
    void getStorageStats()
  })

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
        error.value = extractErrorMessage(err, t('analytics.patterns.reportFetchFailed'))
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
      error.value = extractErrorMessage(e, t('analytics.patterns.reportFetchFailed'))
      logger.error('Report fetch failed:', e)
    })
    return reportText
  }

  return { getStorageStats, clearStorage, getReport }
}
