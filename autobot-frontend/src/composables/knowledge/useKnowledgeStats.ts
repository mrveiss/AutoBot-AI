// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useKnowledgeStats Composable
 *
 * Fetches knowledge base statistics (full and basic) and category fact counts.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 *
 * Reactive refs layer (#5149): the composable owns loading/error state and a
 * `refresh` action. The bare imperative functions are still exported at module
 * scope so non-reactive consumers (and the `useKnowledgeBase` BC shim) keep
 * working unchanged.
 *
 * Category facts extraction (#6052): fetchCategoryFacts / refreshCategoryFacts
 * extracted from KnowledgeStats.vue inline apiClient call.
 *
 * SHARED-SINGLETON STATE CONTRACT (#11658): the reactive refs below
 * (`stats`, `basicStats`, `categoryFactCounts`, `isLoading`, `error`) are
 * declared at MODULE scope, so every `useKnowledgeStats()` call returns the
 * SAME refs. This is intentional — knowledge-base stats are global (there is
 * one knowledge base, not one-per-component), so a refresh triggered by any
 * consumer is observed by all readers. Previously these refs were per-call,
 * which produced the #11619 bug: a parent fetched `refreshCategoryFacts()`
 * into instance A while a child read `categoryFactCounts` from instance B, so
 * the distribution chart rendered 0% bars. Do NOT move this state back inside
 * the function. Use `resetKnowledgeStats()` to clear it (logout / KB switch /
 * test teardown).
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
    const data = await apiClient.get<{ categories?: Record<string, unknown[]> }>(`${getApiBase()}/knowledge_base/facts/by_category`)
    const categories = data?.categories
    if (!categories) return null
    const counts: Record<string, number> = {}
    Object.keys(categories).forEach((category: string) => {
      counts[category] = categories[category].length
    })
    return counts
  } catch {
    return null
  }
}

// ==================== Shared-singleton reactive state (#11658) ====================
// Declared at module scope so all consumers share one instance — see the
// SHARED-SINGLETON STATE CONTRACT note in the file header.

const stats = ref<KnowledgeStats | null>(null)
const basicStats = ref<KnowledgeStats | null>(null)
const categoryFactCounts = ref<Record<string, number>>({})
const error = ref<Error | null>(null)
const { isLoading, wrap } = useLoadingState()

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

/**
 * Clear all shared knowledge-stats state back to its initial (empty) values.
 * Call on logout, when switching knowledge bases, or in test teardown so the
 * module-level singleton does not leak state across contexts.
 */
export function resetKnowledgeStats(): void {
  stats.value = null
  basicStats.value = null
  categoryFactCounts.value = {}
  error.value = null
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
  /** Clear all shared state (logout / KB switch / test teardown). */
  reset: () => void
  // Imperative passthroughs — BC with pre-#5149 callers
  fetchStats: typeof fetchStats
  fetchBasicStats: typeof fetchBasicStats
  fetchCategoryFacts: typeof fetchCategoryFacts
}

export function useKnowledgeStats(): UseKnowledgeStatsReturn {
  return {
    stats: readonly(stats) as Readonly<Ref<KnowledgeStats | null>>,
    basicStats: readonly(basicStats) as Readonly<Ref<KnowledgeStats | null>>,
    categoryFactCounts: readonly(categoryFactCounts) as Readonly<Ref<Record<string, number>>>,
    isLoading: readonly(isLoading),
    error: readonly(error),
    refresh,
    refreshBasic,
    refreshCategoryFacts,
    reset: resetKnowledgeStats,
    fetchStats,
    fetchBasicStats,
    fetchCategoryFacts,
  }
}
