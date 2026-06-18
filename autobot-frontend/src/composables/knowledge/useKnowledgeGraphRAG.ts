// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useKnowledgeGraphRAG
 *
 * Encapsulates all HTTP fetching for the GraphRAGQuery component (#6050):
 *   - searchGraph()  — POST /graph-rag/search with query parameters
 *   - checkHealth()  — GET  /graph-rag/health
 *
 * All calls use apiClient (Pattern B) inside useLoadingState.wrap() so
 * authentication, retries, and error serialisation are handled centrally.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeGraphRAG')

// ============================================================================
// Types
// ============================================================================

export interface GraphRAGSearchResult {
  content: string
  metadata?: Record<string, unknown>
  semantic_score?: number
  keyword_score?: number
  hybrid_score?: number
  relevance_rank?: number
  source_path?: string
}

export interface GraphRAGSearchMetrics {
  total_time?: number
  graph_traversal_time?: number
  semantic_search_time?: number
  reranking_time?: number
}

export interface GraphRAGSearchResponse {
  success: boolean
  results: GraphRAGSearchResult[]
  metrics: GraphRAGSearchMetrics
  request_id: string
}

export interface GraphRAGHealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unavailable'
  components: Record<string, string>
  timestamp: string
}

export interface GraphRAGSearchParams {
  query: string
  start_entity?: string | null
  max_depth?: number
  max_results?: number
  enable_reranking?: boolean
}

// ============================================================================
// Composable
// ============================================================================

export interface UseKnowledgeGraphRAGReturn {
  /** Current search results, or null if no search has been performed. */
  searchResults: Ref<GraphRAGSearchResponse | null>
  /** Current health status from the last health check, or null. */
  healthStatus: Ref<GraphRAGHealthStatus | null>
  /** True while a search request is in-flight. */
  isSearching: Readonly<Ref<boolean>>
  /** True while a health check request is in-flight. */
  isCheckingHealth: Readonly<Ref<boolean>>
  /** Last error message, or empty string. */
  errorMessage: Ref<string>
  /** Execute a Graph-RAG search and update searchResults. */
  searchGraph: (params: GraphRAGSearchParams) => Promise<void>
  /** Fetch health status and update healthStatus. */
  checkHealth: () => Promise<void>
}

export function useKnowledgeGraphRAG(): UseKnowledgeGraphRAGReturn {
  const searchResults = ref<GraphRAGSearchResponse | null>(null)
  const healthStatus = ref<GraphRAGHealthStatus | null>(null)
  const errorMessage = ref('')

  const { isLoading: isSearching, wrap: wrapSearch } = useLoadingState()
  const { isLoading: isCheckingHealth, wrap: wrapHealth } = useLoadingState()

  // --------------------------------------------------------------------------
  // Public actions
  // --------------------------------------------------------------------------

  /**
   * POST /graph-rag/search with the provided parameters and update searchResults.
   */
  async function searchGraph(params: GraphRAGSearchParams): Promise<void> {
    errorMessage.value = ''
    searchResults.value = null

    await wrapSearch(async () => {
      logger.info(`Executing Graph-RAG search: "${params.query.substring(0, 50)}..."`)

      const parsed = await apiClient.post<Record<string, unknown>>(
        `${getApiBase()}/graph-rag/search`,
        {
          query: params.query,
          start_entity: params.start_entity ?? null,
          max_depth: params.max_depth ?? 2,
          max_results: params.max_results ?? 10,
          enable_reranking: params.enable_reranking ?? true,
        },
      )

      searchResults.value = ((parsed as Record<string, unknown>)?.data ?? parsed) as unknown as GraphRAGSearchResponse

      logger.info(`Search complete: ${searchResults.value?.results?.length ?? 0} results`)
    })
  }

  /**
   * GET /graph-rag/health and update healthStatus.
   * On error, falls back to an unhealthy status object so the UI always
   * has a value to display.
   */
  async function checkHealth(): Promise<void> {
    await wrapHealth(async () => {
      try {
        const parsed = await apiClient.get<Record<string, unknown>>(
          `${getApiBase()}/graph-rag/health`,
          { maxRetries: 1 },
        )
        healthStatus.value = ((parsed as Record<string, unknown>)?.data ?? parsed) as unknown as GraphRAGHealthStatus
        logger.info(`Health check: ${healthStatus.value?.status}`)
      } catch (error) {
        // #10011: a 503 means the service is legitimately unavailable — treat it
        // as a calm degraded state (no retry spam, no red "unhealthy" alarm).
        if (error instanceof Error && error.message.includes('HTTP 503')) {
          logger.info('Graph-RAG service unavailable (503) — degraded mode')
          healthStatus.value = {
            status: 'unavailable',
            components: {},
            timestamp: new Date().toISOString(),
          }
        } else {
          logger.error('Health check failed:', error)
          healthStatus.value = {
            status: 'unhealthy',
            components: {},
            timestamp: new Date().toISOString(),
          }
        }
      }
    })
  }

  // --------------------------------------------------------------------------
  // Return
  // --------------------------------------------------------------------------

  return {
    searchResults,
    healthStatus,
    isSearching: readonly(isSearching),
    isCheckingHealth: readonly(isCheckingHealth),
    errorMessage,
    searchGraph,
    checkHealth,
  }
}
