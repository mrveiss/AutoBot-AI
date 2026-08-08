// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useKnowledgeGraphRAG
 *
 * Encapsulates all HTTP fetching for the GraphRAGQuery component (#6050):
 *   - searchGraph()  — POST /graph-rag/search with query parameters
 *   - findPath()     — POST /graph-rag/path, shortest connection path (#13474)
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

/** Mirrors the backend default in GraphRAGPathRequest (#13474). */
const DEFAULT_PATH_MAX_DEPTH = 6

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

// --- Connection path (#13474) ---------------------------------------------

export type GraphPathDirection = 'outgoing' | 'incoming' | 'both'

/** Why no path was returned. `null` when one was found. */
export type GraphPathReason = 'no_path' | 'entity_not_found' | 'not_in_graph' | null

export interface GraphPathEntity {
  id?: string
  name?: string
  type?: string
}

export interface GraphPathHop {
  relation?: string
  /** How this edge was crossed — 'incoming' means against its stored direction. */
  direction?: GraphPathDirection
  edge_id?: string
  from?: string
  to?: string
  node: GraphPathEntity
}

export interface GraphPathResponse {
  success: boolean
  found: boolean
  reason: GraphPathReason
  from_entity: GraphPathEntity | null
  to_entity: GraphPathEntity | null
  missing_entities: string[]
  hops: number
  path: GraphPathHop[]
  query?: Record<string, unknown>
  traversal_time?: number
  request_id?: string
}

export interface GraphPathParams {
  from_entity: string
  to_entity: string
  relation?: string | null
  max_depth?: number
  direction?: GraphPathDirection
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Pull `missing_entities` out of a 404 body, tolerating either the
 * `{detail: {...}}` envelope FastAPI produces or a bare object. (#13474)
 *
 * Returns `null` when the body is not recognisably this endpoint's
 * entity-not-found response, so the caller can raise instead of misreporting an
 * unrelated 404 as bad user input.
 */
async function readMissingEntities(response: Response): Promise<string[] | null> {
  try {
    const body = (await response.json()) as Record<string, unknown>
    const detail = (body?.detail ?? body) as Record<string, unknown>
    if (detail === null || typeof detail !== 'object') return null
    const missing = detail.missing_entities
    if (Array.isArray(missing)) return missing.map(String)
    // Only a body that actually identifies itself as this error may be shaped
    // into "your entity names are wrong". A bare FastAPI 404 (route missing on
    // an older backend, stale proxy) must stay an error — telling the user
    // their data is bad when the endpoint is not deployed is a false negative.
    return detail.error === 'entity_not_found' ? [] : null
  } catch {
    logger.warn('Could not parse the 404 body from /graph-rag/path')
    return null
  }
}

/** Shape a 404 into the same result contract a 200 uses, so the UI has one path. */
function buildMissingEntitiesResult(
  missing: string[],
  params: GraphPathParams,
): GraphPathResponse {
  return {
    success: true,
    found: false,
    reason: 'entity_not_found',
    from_entity: null,
    to_entity: null,
    // An unparseable body still names both candidates rather than neither.
    missing_entities: missing.length > 0 ? missing : [params.from_entity, params.to_entity],
    hops: 0,
    path: [],
  }
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
  /** Result of the last connection-path query, or null. (#13474) */
  pathResult: Ref<GraphPathResponse | null>
  /** True while a connection-path request is in-flight. */
  isFindingPath: Readonly<Ref<boolean>>
  /** Find the shortest connection path between two entities. (#13474) */
  findPath: (params: GraphPathParams) => Promise<void>
}

export function useKnowledgeGraphRAG(): UseKnowledgeGraphRAGReturn {
  const searchResults = ref<GraphRAGSearchResponse | null>(null)
  const healthStatus = ref<GraphRAGHealthStatus | null>(null)
  const pathResult = ref<GraphPathResponse | null>(null)
  const errorMessage = ref('')

  const { isLoading: isSearching, wrap: wrapSearch } = useLoadingState()
  const { isLoading: isCheckingHealth, wrap: wrapHealth } = useLoadingState()
  const { isLoading: isFindingPath, wrap: wrapPath } = useLoadingState()

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
   * POST /graph-rag/path and update pathResult. (#13474)
   *
   * Three outcomes must stay distinguishable in the UI, so none of them is
   * collapsed into a generic error:
   *   - a path was found           -> found: true
   *   - both entities exist, no link -> 200, found: false, reason 'no_path'
   *   - a name did not resolve      -> 404, reason 'entity_not_found'
   *
   * The 404 body carries `missing_entities`, so it is read from the raw
   * Response rather than the thrown Error — apiClient.post() would flatten the
   * structured detail into a message string and the UI could not name which
   * entity was wrong.
   */
  async function findPath(params: GraphPathParams): Promise<void> {
    errorMessage.value = ''
    pathResult.value = null

    await wrapPath(async () => {
      const response = await apiClient.rawRequest(`${getApiBase()}/graph-rag/path`, {
        method: 'POST',
        body: {
          from_entity: params.from_entity,
          to_entity: params.to_entity,
          relation: params.relation ?? null,
          max_depth: params.max_depth ?? DEFAULT_PATH_MAX_DEPTH,
          direction: params.direction ?? 'both',
        },
      })

      if (response.ok) {
        pathResult.value = (await response.json()) as GraphPathResponse
        logger.info(
          `Connection path: found=${pathResult.value?.found} hops=${pathResult.value?.hops}`,
        )
        return
      }

      if (response.status === 404) {
        const missing = await readMissingEntities(response)
        if (missing !== null) {
          pathResult.value = buildMissingEntitiesResult(missing, params)
          logger.info(`Connection path: unresolved entities ${pathResult.value.missing_entities}`)
          return
        }
        throw new Error('HTTP 404: /graph-rag/path is not available on this backend')
      }

      throw new Error(`HTTP ${response.status}: ${response.statusText || 'Request failed'}`)
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
    pathResult,
    isFindingPath: readonly(isFindingPath),
    findPath,
  }
}
