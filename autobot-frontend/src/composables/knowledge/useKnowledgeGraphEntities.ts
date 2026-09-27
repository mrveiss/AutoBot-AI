// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useKnowledgeGraphEntities
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

const logger = createLogger('useKnowledgeGraphEntities')

// ============================================================================
// Types
// ============================================================================

/**
 * What the last load got from one of the stores the graph is assembled from.
 *
 * #17612: without this, `entities.length === 0` was the only thing the view
 * could ask, and it cannot tell "both stores were read and hold nothing" from
 * "a store could not be read". Those need opposite words on screen -- one
 * invites you to create an entity, the other is a failure to report -- and the
 * old code showed the invitation for both.
 */
export interface GraphSourceOutcome {
  /** Stable key naming the store; the view maps it to a translated label. */
  key: 'unified' | 'memory'
  /** True when this store was read. A read that returned nothing is still ok. */
  ok: boolean
  /** Entities this store contributed. Meaningful only when `ok`. */
  count: number
  /** Why the read failed, or '' when it did not. */
  error: string
}

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

export interface UseKnowledgeGraphEntitiesReturn {
  /** Current entity list (merged from unified KB + memory endpoints). */
  entities: Readonly<Ref<GraphEntity[]>>
  /** Current relation list (deduplicated). */
  relations: Readonly<Ref<GraphRelation[]>>
  /** True while a load or create operation is in-flight. */
  isLoading: Readonly<Ref<boolean>>
  /** Last error message, or empty string. */
  errorMessage: Ref<string>
  /**
   * Per-store outcome of the last load, empty before the first one.
   *
   * This is the state a view needs to say something true about an empty
   * graph; `entities.length` alone cannot (#17612).
   */
  sources: Readonly<Ref<GraphSourceOutcome[]>>
  /**
   * Fetch all graph data and update `entities`/`relations`/`sources`.
   *
   * Does not reject. A store that cannot be read is reported in `sources`,
   * not thrown: the old rejection also aborted the caller's Cytoscape
   * initialisation and arrived unhandled from `onMounted` (#17612).
   */
  fetchGraphData: () => Promise<void>
  /**
   * Create a new memory entity, push it into `entities`, and return the
   * created entity (or null if the response shape is unexpected).
   */
  createGraphEntity: (payload: NewEntityPayload) => Promise<GraphEntity | null>
}

export function useKnowledgeGraphEntities(): UseKnowledgeGraphEntitiesReturn {
  const entities = ref<GraphEntity[]>([])
  const relations = ref<GraphRelation[]>([])
  const errorMessage = ref('')
  const sources = ref<GraphSourceOutcome[]>([])
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
            // #13452: 'related_to' is the canonical spelling; 'relates_to' was
            // the knowledge-base-only variant and is not a memory-graph type.
            type: rel.relation_type as string ?? rel.type as string ?? 'related_to',
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
  /**
   * Why a store could not be read, or '' when the failure carried no message.
   *
   * '' rather than a phrase: the words a reader sees are the view's job, and a
   * composable that invents them puts untranslatable English on screen. The
   * first version here returned `String(error)`, which for `new Error('')` is
   * the literal "Error" -- a reason-shaped string carrying no reason.
   */
  function _reason(error: unknown): string {
    if (error instanceof Error) return error.message.trim()
    return String(error ?? '').trim()
  }

  /** Entities under `.data.entities`, or `.entities` for the flatter shape. */
  function _entitiesOf(payload: unknown): GraphEntity[] {
    const body = payload as Record<string, unknown> | undefined
    const nested = body?.data as Record<string, unknown> | undefined
    return (
      (nested?.entities as GraphEntity[] | undefined)
      ?? (body?.entities as GraphEntity[] | undefined)
      ?? []
    )
  }

  async function fetchGraphData(): Promise<void> {
    errorMessage.value = ''
    await wrap(async () => {
      // allSettled, not all: the graph is assembled from two independent
      // stores, and `Promise.all` threw away a healthy store's entities
      // whenever the other one failed -- then left the view showing "no
      // entities found", which is a claim about the data rather than about
      // the request (#17612). `_fetchMemoryRelations` below already settled
      // its per-entity reads for the same reason; this call did not.
      const [unified, memory] = await Promise.allSettled([
        apiClient.get<Record<string, unknown>>(
          `${getApiBase()}/knowledge_base/multi-source/graph?max_facts=100&include_categories=true`,
        ),
        apiClient.get<Record<string, unknown>>(`${getApiBase()}/memory/entities/all`),
      ])

      const unifiedEntities = unified.status === 'fulfilled' ? _entitiesOf(unified.value) : []
      const memoryEntities = memory.status === 'fulfilled' ? _entitiesOf(memory.value) : []

      sources.value = [
        {
          key: 'unified',
          ok: unified.status === 'fulfilled',
          count: unifiedEntities.length,
          error: unified.status === 'rejected' ? _reason(unified.reason) : '',
        },
        {
          key: 'memory',
          ok: memory.status === 'fulfilled',
          count: memoryEntities.length,
          error: memory.status === 'rejected' ? _reason(memory.reason) : '',
        },
      ]

      // Merge entities, avoiding duplicates by ID
      const entityMap = new Map<string, GraphEntity>()
      for (const entity of [...unifiedEntities, ...memoryEntities]) {
        if (entity.id && !entityMap.has(entity.id)) {
          entityMap.set(entity.id, entity)
        }
      }
      entities.value = Array.from(entityMap.values())

      // Seed relations from the unified endpoint
      const unifiedBody = unified.status === 'fulfilled'
        ? ((unified.value as Record<string, unknown>)?.data as Record<string, unknown> | undefined)
        : undefined
      relations.value = (unifiedBody?.relations as GraphRelation[] | undefined) ?? []

      // Augment with per-entity memory relations when memory has entries
      if (memoryEntities.length > 0) {
        await _fetchMemoryRelations(memoryEntities)
      }

      const failed = sources.value.filter((source) => !source.ok)
      if (failed.length > 0) {
        // Still reported, so the transient banner keeps firing; the durable
        // statement is `sources`, because this message is cleared after five
        // seconds and the screen underneath has to stay true after that.
        errorMessage.value = failed.map((source) => `${source.key}: ${source.error}`).join('; ')
        logger.error('Graph sources failed:', errorMessage.value)
      }

      logger.info(
        `Loaded graph: ${entities.value.length} entities, ${relations.value.length} relations`
        + ` (${sources.value.filter((source) => source.ok).length}/${sources.value.length} stores read)`,
      )
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
    sources: readonly(sources) as Readonly<Ref<GraphSourceOutcome[]>>,
    fetchGraphData,
    createGraphEntity,
  }
}
