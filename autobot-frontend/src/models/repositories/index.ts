// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// Repository exports - Unified API layer for AutoBot
// Canonical barrel for `@/models/repositories` (issue #11678: the shadowing
// `models/repositories.ts` file barrel was collapsed into this directory index).
export { ApiRepository } from './ApiRepository'
export { ChatRepository } from './ChatRepository'
export { KnowledgeRepository } from './KnowledgeRepository'
export { SystemRepository } from './SystemRepository'

// Repository instances (singletons) - Import directly for better initialization
import { ApiRepository } from './ApiRepository'
import type { ApiConfig } from './ApiRepository'
import { ChatRepository } from './ChatRepository'
import { KnowledgeRepository } from './KnowledgeRepository'
import { SystemRepository } from './SystemRepository'

export const apiRepository = new ApiRepository()
// Issue #11640: chat/knowledge singletons live in their class files — re-export
// them instead of constructing SECOND instances here.
export { chatRepository } from './ChatRepository'
export { knowledgeRepository } from './KnowledgeRepository'
export const systemRepository = new SystemRepository()

// Repository factory for creating instances with custom config
export class RepositoryFactory {
  static createChatRepository(baseUrl?: string) {
    return new ChatRepository(baseUrl)
  }

  static createKnowledgeRepository(config?: Partial<ApiConfig>) {
    return new KnowledgeRepository(config)
  }

  static createSystemRepository(config?: Partial<ApiConfig>) {
    return new SystemRepository(config)
  }
}

// Type exports for repository interfaces
export type {
  ApiConfig,
  CacheEntry
} from './ApiRepository'

export type {
  ChatMessage,
  ChatSession,
  ChatStreamResponse,
  SendMessageOptions,
  SendMessageResponse
} from './ChatRepository'

export type {
  KnowledgeDocument,
  SearchResult,
  SearchKnowledgeRequest,
  RagSearchRequest,
  RagSearchResponse,
  AddTextRequest,
  AddUrlRequest,
  AddFileOptions,
  KnowledgeStats,
  DetailedKnowledgeStats,
  DetailedKnowledgeSizeMetrics,
  KnowledgeCategoryEntry,
  BackendSearchResult
} from './KnowledgeRepository'

export type {
  HealthCheckResponse,
  SystemInfoResponse,
  ExecuteCommandRequest,
  CommandExecutionResponse
} from './SystemRepository'

// Legacy type aliases for backward compatibility (merged from the removed
// `models/repositories.ts` file barrel — issue #11678)

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
