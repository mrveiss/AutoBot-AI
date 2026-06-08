// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeStats Composable
 *
 * Fetches knowledge base statistics (full and basic) and category fact counts.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 *
 * Reactive refs layer (#5149): the composable now owns loading/error state
 * via `ref`s and exposes a `refresh` action. The bare imperative functions
 * are still exported at module scope so non-reactive consumers (and the
 * `useKnowledgeBase` BC shim) keep working unchanged.
 *
 * Category facts extraction (#6052): fetchCategoryFacts / refreshCategoryFacts
 * extracted from KnowledgeStats.vue inline apiClient call.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '../useLoadingState'
import type { KnowledgeStats } from '@/types/knowledgeBase'

// ==================== Bare imperative API ====================

/**
 * Fetch knowledge base statistics.
 */
export const fetchStats = (): Promise<KnowledgeStats> =>
  apiClient.get<KnowledgeStats>(`${getApiBase()}/knowledge_base/stats`)

/**
 * Fetch basic knowledge base statistics.
 * Returns null on error to preserve previous caller expectations
 * (UI treats missing basic stats as non-fatal).
 */
export const fetchBasicStats = async (): Promise<KnowledgeStats | null> => {
  try {
    return await apiClient.get<KnowledgeStats>(`${getApiBase()}/knowledge_base/stats/basic`)
  } catch {
    return null
  }
}

/**
 * Fetch per-category fact counts from the knowledge base.
 * Returns a map of category name → fact count, or null on error
 * (UI treats missing category facts as non-fatal — stats still render).
 */
export const fetchCategoryFacts = async (): Promise<Record<string, number> | null> => {
  try {
    const data = await apiClient.get<Record<string, any>>(`${getApiBase()}/knowledge_base/facts/by_category`)
    if (!data?.categories) return null
    const counts: Record<string, number> = {}
    Object.keys(data.categories).forEach((category: string) => {
      counts[category] = data.categories[category].length
    })
    return counts
  } catch {
    return null
  }
}

// ==================== Reactive composable ====================

export interface UseKnowledgeStatsReturn {
  /** Latest full stats result, or null if never fetched / fetch failed. */
  stats: Readonly<Ref<KnowledgeStats | null>>
  /** Latest basic stats result, or null. */
  basicStats: Readonly<Ref<KnowledgeStats | null>>
  /** Latest per-category fact counts, or empty object. */
  categoryFactCounts: Readonly<Ref<Record<string, number>>>
  /** True while any fetch is in-flight. */
  isLoading: Readonly<Ref<boolean>>
  /** Last error raised by `refresh`/`refreshBasic`, cleared on the next call. */
  error: Readonly<Ref<Error | null>>
  /** Fetch full stats, update `stats` + state refs, return the payload. */
  refresh: () => Promise<KnowledgeStats | null>
  /** Fetch basic stats, update `basicStats` + state refs, return the payload. */
  refreshBasic: () => Promise<KnowledgeStats | null>
  /** Fetch category fact counts, update `categoryFactCounts`, return the payload. */
  refreshCategoryFacts: () => Promise<Record<string, number> | null>
  // Imperative passthroughs — BC with pre-#5149 callers
  fetchStats: typeof fetchStats
  fetchBasicStats: typeof fetchBasicStats
  fetchCategoryFacts: typeof fetchCategoryFacts
}

export function useKnowledgeStats(): UseKnowledgeStatsReturn {
  const stats = ref<KnowledgeStats | null>(null)
  const basicStats = ref<KnowledgeStats | null>(null)
  const categoryFactCounts = ref<Record<string, number>>({})
  const { isLoading, wrap } = useLoadingState()
  const error = ref<Error | null>(null)

  const refresh = async (): Promise<KnowledgeStats | null> => {
    error.value = null
    return wrap(async () => {
      try {
        const data = await fetchStats()
        stats.value = data
        return data
      } catch (err) {
        error.value = err instanceof Error ? err : new Error(String(err))
        throw err
      }
    })
  }

  const refreshBasic = async (): Promise<KnowledgeStats | null> => {
    error.value = null
    return wrap(async () => {
      const data = await fetchBasicStats()
      basicStats.value = data
      return data
    })
  }

  const refreshCategoryFacts = async (): Promise<Record<string, number> | null> => {
    const data = await fetchCategoryFacts()
    if (data !== null) {
      categoryFactCounts.value = data
    }
    return data
  }

  return {
    stats: readonly(stats) as Readonly<Ref<KnowledgeStats | null>>,
    basicStats: readonly(basicStats) as Readonly<Ref<KnowledgeStats | null>>,
    categoryFactCounts: readonly(categoryFactCounts) as Readonly<Ref<Record<string, number>>>,
    isLoading: readonly(isLoading),
    error: readonly(error),
    refresh,
    refreshBasic,
    refreshCategoryFacts,
    fetchStats,
    fetchBasicStats,
    fetchCategoryFacts,
  }
}
