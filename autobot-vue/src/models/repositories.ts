/**
 * Repository layer for API communication
 * Provides type-safe access to backend services
 *
 * IMPORTANT: This file re-exports from the consolidated repository implementations.
 * Do NOT define duplicate repository classes here.
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */

// Re-export ChatRepository
export { chatRepository } from './repositories/ChatRepository'

// Re-export KnowledgeRepository (SINGLE SOURCE OF TRUTH)
export {
  // Singleton instance
  knowledgeRepository,
  // Class for typing/extension
  KnowledgeRepository,
  // Types
  type KnowledgeDocument,
  type SearchResult,
  type SearchKnowledgeRequest,
  type RagSearchRequest,
  type RagSearchResponse,
  type AddTextRequest,
  type AddUrlRequest,
  type AddFileOptions,
  type KnowledgeStats,
  type DetailedKnowledgeStats,
  type BackendSearchResult
} from './repositories/KnowledgeRepository'

// Legacy type aliases for backward compatibility
// These map to the store's types which are used throughout the app

/**
 * @deprecated Use SearchKnowledgeRequest instead
 */
export type SearchParams = {
  query: string
  limit?: number
  category?: string
  type?: string
  use_rag?: boolean
  enable_reranking?: boolean
  filters?: {
    categories?: string[]
    tags?: string[]
    types?: string[]
  }
}

/**
 * @deprecated Use RagSearchRequest instead
 */
export type RagSearchParams = {
  query: string
  limit?: number
  reformulate_query?: boolean
}

/**
 * RAG analysis result structure
 */
export interface RagAnalysis {
  confidence: number
  sources_used: number
  query_reformulated: boolean
  context_used: string[]
}
