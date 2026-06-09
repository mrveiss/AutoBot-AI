// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// Repository exports - Unified API layer for AutoBot
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
export const chatRepository = new ChatRepository()
export const knowledgeRepository = new KnowledgeRepository()
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
  SearchKnowledgeRequest,
  RagSearchRequest,
  RagSearchResponse,
  AddTextRequest,
  AddUrlRequest,
  KnowledgeStats,
  DetailedKnowledgeStats,
  DetailedKnowledgeSizeMetrics,
  KnowledgeCategoryEntry
} from './KnowledgeRepository'

export type {
  HealthCheckResponse,
  SystemInfoResponse,
  ExecuteCommandRequest,
  CommandExecutionResponse
} from './SystemRepository'
