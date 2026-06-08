// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeEntities Composable
 *
 * Entity extraction API calls for knowledge graph population.
 * Extracted from EntityExtractor.vue (#6054) to follow the
 * same composable pattern as useKnowledgeStats / useKnowledgeFacts.
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'

// ============================================================================
// Types
// ============================================================================

export interface EntityMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface EntityExtractionRequest {
  conversation_id: string
  messages: EntityMessage[]
}

export interface EntityExtractionResult {
  success: boolean
  conversation_id: string
  facts_analyzed: number
  entities_created: number
  relations_created: number
  processing_time: number
  errors: string[]
  request_id: string
  timestamp?: number
}

// ============================================================================
// Bare imperative API
// ============================================================================

/**
 * Extract entities and relationships from a list of conversation messages.
 */
export const extractEntities = (
  request: EntityExtractionRequest
): Promise<EntityExtractionResult> =>
  apiClient.post<EntityExtractionResult>(`${getApiBase()}/entities/extract`, request)
