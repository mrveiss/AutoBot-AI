// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useKnowledgeGraph
 *
 * Encapsulates all HTTP fetching for the KnowledgeGraph component (#6040):
 *   - fetchGraphData()  — parallel GET for unified graph + memory entities
 *   - fetchMemoryRelations() — parallel per-entity GET for relations
 *   - createGraphEntity()   — POST to create a new memory entity
 *
 * All calls use apiClient (Pattern B) inside useLoadingState.wrap() so
 * authentication, retries, and error serialisation are handled centrally.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeGraph')

// ============================================================================
// Types
// ============================================================================

export interface GraphEntity {
  id: string
  name: string
  type: string
  created_at?: number
  updated_at?: number
  observations: string[]
  metadata?: Record<string, unknown>
}

export interface GraphRelation {
  from: string
  to: string
  type: string
  strength?: number
}

export interface NewEntityPayload {
  name: string
  type: string
  observations: string
}

export interface GraphData {
  entities: GraphEntity[]
  relations: GraphRelation[]
}

// ============================================================================
// Composable
// ============================================================================

export interface UseKnowledgeGraphReturn {
  /** Current entity list (merged from unified KB + memory endpoints). */
  entities: Readonly<Ref<GraphEntity[]>>
  /** Current relation list (deduplicated). */
  relations: Readonly<Ref<GraphRelation[]>>
  /** True while a load or create operation is in-flight. */
  isLoading: Readonly<Ref<boolean>>
  /** Last error message, or empty string. */
  errorMessage: Ref<string>
  /** Fetch all graph data and update `entities`/`relations`. */
  fetchGraphData: () => Promise<void>
  /**
   * Create a new memory entity, push it into `entities`, and return the
   * created entity (or null if the response shape is unexpected).
   */
  createGraphEntity: (payload: NewEntityPayload) => Promise<GraphEntity | null>
}

export function useKnowledgeGraph(): UseKnowledgeGraphReturn {
  const entities = ref<GraphEntity[]>([])
  const relations = ref<GraphRelation[]>([])
  const errorMessage = ref('')
  const { isLoading, wrap } = useLoadingState()

  // --------------------------------------------------------------------------
  // Internal helpers
  // --------------------------------------------------------------------------

  /**
   * Fetch per-entity relations for a set of memory entities using parallel
   * requests. Deduplicates the merged result before storing.
   */
  async function _fetchMemoryRelations(memoryEntities: GraphEntity[]): Promise<void> {
    const allRelations: GraphRelation[] = [...relations.value]

    const results = await Promise.allSettled(
      memoryEntities.map(async (entity) => {
        const parsed = await apiClient.get<Record<string, unknown>>(
          `${getApiBase()}/memory/entities/${entity.id}/relations`,
        )
        return { entity, parsed }
      }),
    )

    for (const result of results) {
      if (result.status === 'rejected') continue

      const { entity, parsed } = result.value
      const data = (parsed as Record<string, unknown>)?.data ?? parsed

      if ((data as Record<string, unknown>)?.related_entities) {
        const related = (data as Record<string, unknown>).related_entities as Record<string, unknown>[]
        for (const rel of related) {
          allRelations.push({
            from: entity.id,
            to: (rel.entity as Record<string, unknown>)?.id as string ?? rel.id as string,
            type: rel.relation_type as string ?? rel.type as string ?? 'relates_to',
            strength: rel.strength as number ?? 1.0,
          })
        }
      } else if ((data as Record<string, unknown>)?.relations) {
        const rels = (data as Record<string, unknown>).relations as GraphRelation[]
        allRelations.push(...rels)
      }
    }

    // Deduplicate relations using a Set for O(1) lookups
    const seen = new Set<string>()
    relations.value = allRelations.filter((r) => {
      const key = `${r.from}-${r.to}-${r.type}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }

  // --------------------------------------------------------------------------
  // Public actions
  // --------------------------------------------------------------------------

  /**
   * Fetch the unified KB graph and memory entities in parallel, merge them
   * (deduplicating by entity ID), then resolve relations.
   */
  async function fetchGraphData(): Promise<void> {
    errorMessage.value = ''
    await wrap(async () => {
      try {
        const [unifiedData, memoryData] = await Promise.all([
          apiClient.get<Record<string, unknown>>(
            `${getApiBase()}/knowledge_base/unified/graph?max_facts=100&include_categories=true`,
          ),
          apiClient.get<Record<string, unknown>>(
            `${getApiBase()}/memory/entities/all`,
          ),
        ])

        const unifiedBody = (unifiedData as Record<string, unknown>)?.data as Record<string, unknown> | undefined
        const memoryBody = (memoryData as Record<string, unknown>)?.data as Record<string, unknown> | undefined

        const unifiedEntities: GraphEntity[] =
          (unifiedBody?.entities as GraphEntity[] | undefined) ?? []
        const memoryEntities: GraphEntity[] =
          (memoryBody?.entities as GraphEntity[] | undefined)
          ?? ((memoryData as Record<string, unknown>)?.entities as GraphEntity[] | undefined)
          ?? []

        // Merge entities, avoiding duplicates by ID
        const entityMap = new Map<string, GraphEntity>()
        for (const entity of [...unifiedEntities, ...memoryEntities]) {
          if (entity.id && !entityMap.has(entity.id)) {
            entityMap.set(entity.id, entity)
          }
        }
        entities.value = Array.from(entityMap.values())

        // Seed relations from the unified endpoint
        relations.value = (unifiedBody?.relations as GraphRelation[] | undefined) ?? []

        // Augment with per-entity memory relations when memory has entries
        if (memoryEntities.length > 0) {
          await _fetchMemoryRelations(memoryEntities)
        }

        logger.info(
          `Loaded graph: ${entities.value.length} entities, ${relations.value.length} relations`,
        )
      } catch (error) {
        logger.error('Failed to fetch graph data:', error)
        errorMessage.value =
          error instanceof Error ? error.message : 'Failed to load graph'
        throw error
      }
    })
  }

  /**
   * POST a new entity to /memory/entities, push it into the local entity list,
   * and return the created entity.
   */
  async function createGraphEntity(
    payload: NewEntityPayload,
  ): Promise<GraphEntity | null> {
    const observations = payload.observations
      .split('\n')
      .map((o) => o.trim())
      .filter((o) => o.length > 0)

    const parsed = await apiClient.post<Record<string, unknown>>(
      `${getApiBase()}/memory/entities`,
      {
        name: payload.name,
        entity_type: payload.type,
        observations,
      },
    )

    const data = (parsed as Record<string, unknown>)?.data ?? parsed
    let created: GraphEntity | null = null

    if ((data as GraphEntity)?.id && (data as GraphEntity)?.name) {
      created = data as GraphEntity
    } else if ((data as Record<string, unknown>)?.entity) {
      created = (data as Record<string, unknown>).entity as GraphEntity
    }

    if (created) {
      entities.value = [...entities.value, created]
    }

    return created
  }

  // --------------------------------------------------------------------------
  // Return
  // --------------------------------------------------------------------------

  return {
    entities: readonly(entities) as Readonly<Ref<GraphEntity[]>>,
    relations: readonly(relations) as Readonly<Ref<GraphRelation[]>>,
    isLoading: readonly(isLoading),
    errorMessage,
    fetchGraphData,
    createGraphEntity,
  }
}
