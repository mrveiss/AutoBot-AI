/**
 * useKnowledgeFacts Composable
 *
 * Search (basic + advanced) and direct-fact management for the knowledge base.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import type {
  SearchResponse,
  AddFactResponse,
} from '@/types/knowledgeBase'

/**
 * Advanced search options (Issue #555).
 *
 * Uses the consolidated search endpoint with all available features:
 * - mode: 'semantic' | 'keyword' | 'hybrid' | 'auto'
 * - enable_rag: Enable RAG synthesis for responses
 * - enable_reranking: Enable cross-encoder reranking
 * - tags: Filter by tags
 * - min_score: Minimum similarity threshold
 * - category: Filter by category
 */
export interface AdvancedSearchOptions {
  query: string
  top_k?: number
  mode?: 'semantic' | 'keyword' | 'hybrid' | 'auto'
  enable_rag?: boolean
  enable_reranking?: boolean
  reformulate_query?: boolean
  tags?: string[]
  tags_match_any?: boolean
  min_score?: number
  category?: string
  offset?: number
}

export function useKnowledgeFacts() {
  /**
   * Search knowledge base (basic)
   * Issue #552: Backend expects POST for search
   */
  const searchKnowledge = (query: string): Promise<SearchResponse> =>
    apiClient.post<SearchResponse>(`${getApiBase()}/knowledge_base/search`, { query })

  /**
   * Advanced search with full options (Issue #555)
   */
  const advancedSearch = (options: AdvancedSearchOptions): Promise<SearchResponse> =>
    apiClient.post<SearchResponse>(`${getApiBase()}/knowledge_base/search`, options)

  /**
   * Add new fact to knowledge base
   */
  const addFact = (fact: {
    content: string
    category: string
    metadata?: Record<string, unknown>
  }): Promise<AddFactResponse> =>
    apiClient.post<AddFactResponse>(`${getApiBase()}/knowledge_base/facts`, fact)

  return {
    searchKnowledge,
    advancedSearch,
    addFact,
  }
}
