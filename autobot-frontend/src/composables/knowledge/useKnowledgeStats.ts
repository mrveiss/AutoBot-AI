/**
 * useKnowledgeStats Composable
 *
 * Fetches knowledge base statistics (full and basic).
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import type { KnowledgeStats } from '@/types/knowledgeBase'

export function useKnowledgeStats() {
  /**
   * Fetch knowledge base statistics
   */
  const fetchStats = (): Promise<KnowledgeStats> =>
    apiClient.get<KnowledgeStats>(`${getApiBase()}/knowledge_base/stats`)

  /**
   * Fetch basic knowledge base statistics
   * GET /api/knowledge_base/stats/basic
   *
   * Returns null on error to preserve previous caller expectations
   * (UI treats missing basic stats as non-fatal).
   */
  const fetchBasicStats = async (): Promise<KnowledgeStats | null> => {
    try {
      return await apiClient.get<KnowledgeStats>(`${getApiBase()}/knowledge_base/stats/basic`)
    } catch {
      return null
    }
  }

  return {
    fetchStats,
    fetchBasicStats,
  }
}
