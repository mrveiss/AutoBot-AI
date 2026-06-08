// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeEntityGraph
 *
 * Encapsulates all HTTP fetching for the EntityGraphManager component (#6046):
 *   - fetchGraphStats()       — GET unified graph summary for entity/relation counts
 *   - fetchExtractionHealth() — GET entity extraction service health
 *   - fetchGraphRagHealth()   — GET graph-rag service health
 *   - refreshStats()          — Runs all three in parallel under a single loading flag
 *
 * All calls use apiClient (Pattern B GET) inside useLoadingState.wrap() so
 * authentication, retries, and error serialisation are handled centrally.
 */

import { ref, reactive, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeEntityGraph')

// ============================================================================
// Types
// ============================================================================

export interface EntityGraphStats {
  entityCount: number
  relationCount: number
  entityTypes: number
  relationTypes: number
}

export interface EntityGraphHealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown'
  components: Record<string, string>
}

// ============================================================================
// Composable return type
// ============================================================================

export interface UseKnowledgeEntityGraphReturn {
  /** Current graph statistics. */
  graphStats: EntityGraphStats
  /** Health status for the entity extraction service. */
  extractionHealth: EntityGraphHealthStatus
  /** Health status for the graph-rag service. */
  graphRagHealth: EntityGraphHealthStatus
  /** True while any fetch is in-flight. */
  isLoading: Readonly<Ref<boolean>>
  /** Last error message, or empty string. */
  statsError: Ref<string>
  /** Fetch all stats + health data in parallel and update reactive state. */
  refreshStats: () => Promise<void>
}

// ============================================================================
// Composable
// ============================================================================

export function useKnowledgeEntityGraph(): UseKnowledgeEntityGraphReturn {
  const graphStats = reactive<EntityGraphStats>({
    entityCount: 0,
    relationCount: 0,
    entityTypes: 0,
    relationTypes: 0,
  })

  const extractionHealth = reactive<EntityGraphHealthStatus>({
    status: 'unknown',
    components: {},
  })

  const graphRagHealth = reactive<EntityGraphHealthStatus>({
    status: 'unknown',
    components: {},
  })

  const statsError = ref('')
  const { isLoading, wrap } = useLoadingState()

  // --------------------------------------------------------------------------
  // Internal fetch helpers
  // --------------------------------------------------------------------------

  async function _fetchGraphStats(): Promise<void> {
    try {
      const data = await apiClient.get<Record<string, unknown>>(
        `${getApiBase()}/knowledge_base/unified/graph?max_facts=0`,
      )
      const graphData = (data as Record<string, unknown>)?.data ?? data

      if ((graphData as Record<string, unknown>)?.entities) {
        const entities = (graphData as Record<string, unknown>).entities as { type: string }[]
        graphStats.entityCount = entities.length
        graphStats.entityTypes = new Set(entities.map((e) => e.type)).size
      }

      if ((graphData as Record<string, unknown>)?.relations) {
        const relations = (graphData as Record<string, unknown>).relations as { type: string }[]
        graphStats.relationCount = relations.length
        graphStats.relationTypes = new Set(relations.map((r) => r.type)).size
      }
    } catch (error) {
      logger.warn('Could not fetch graph stats:', error)
    }
  }

  async function _fetchExtractionHealth(): Promise<void> {
    try {
      const data = await apiClient.get<Record<string, unknown>>(
        `${getApiBase()}/entities/extract/health`,
      )
      const healthData = (data as Record<string, unknown>)?.data ?? data

      extractionHealth.status =
        ((healthData as Record<string, unknown>)?.status as EntityGraphHealthStatus['status']) ??
        'unknown'
      extractionHealth.components =
        ((healthData as Record<string, unknown>)?.components as Record<string, string>) ?? {}
    } catch (error) {
      logger.warn('Could not fetch extraction health:', error)
      extractionHealth.status = 'unhealthy'
      extractionHealth.components = {}
    }
  }

  async function _fetchGraphRagHealth(): Promise<void> {
    try {
      const data = await apiClient.get<Record<string, unknown>>(
        `${getApiBase()}/graph-rag/health`,
      )
      const healthData = (data as Record<string, unknown>)?.data ?? data

      graphRagHealth.status =
        ((healthData as Record<string, unknown>)?.status as EntityGraphHealthStatus['status']) ??
        'unknown'
      graphRagHealth.components =
        ((healthData as Record<string, unknown>)?.components as Record<string, string>) ?? {}
    } catch (error) {
      logger.warn('Could not fetch graph-rag health:', error)
      graphRagHealth.status = 'unhealthy'
      graphRagHealth.components = {}
    }
  }

  // --------------------------------------------------------------------------
  // Public action
  // --------------------------------------------------------------------------

  async function refreshStats(): Promise<void> {
    statsError.value = ''
    await wrap(async () => {
      try {
        await Promise.all([
          _fetchGraphStats(),
          _fetchExtractionHealth(),
          _fetchGraphRagHealth(),
        ])
        logger.info('Entity graph stats refreshed successfully')
      } catch (error) {
        logger.error('Failed to refresh entity graph stats:', error)
        statsError.value =
          error instanceof Error ? error.message : 'Failed to load statistics'
        throw error
      }
    })
  }

  // --------------------------------------------------------------------------
  // Return
  // --------------------------------------------------------------------------

  return {
    graphStats,
    extractionHealth,
    graphRagHealth,
    isLoading: readonly(isLoading),
    statsError,
    refreshStats,
  }
}
