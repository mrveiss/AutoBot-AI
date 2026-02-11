// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeGraph Composable (Issue #759)
 *
 * Provides reactive state and API methods for the Knowledge Graph Pipeline.
 * Handles entity search, relationship exploration, temporal events,
 * hierarchical summaries, and pipeline execution.
 */

import { ref, reactive } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeGraph')

// ============================================================================
// Types
// ============================================================================

export interface Entity {
  id: string
  name: string
  type: string
  description: string
  properties: Record<string, unknown>
  confidence: number
  source_document_ids: string[]
}

export interface Relationship {
  id: string
  source_entity: string
  source_type: string
  target_entity: string
  target_type: string
  relationship_type: string
  description: string
  confidence: number
  properties: Record<string, unknown>
}

export interface TemporalEvent {
  id: string
  name: string
  description: string
  event_type: string
  timestamp: string | null
  temporal_expression: string | null
  participants: string[]
  entity_name: string
  causal_links: string[]
}

export interface Summary {
  id: string
  content: string
  level: 'chunk' | 'section' | 'document'
  key_topics: string[]
  score: number
  document_id: string
  parent_id: string | null
  children_ids: string[]
}

export interface PipelineResult {
  pipeline_id: string
  status: string
  document_id: string
  stats: {
    chunks_processed: number
    entities_extracted: number
    relationships_created: number
    events_detected: number
    summaries_generated: number
  }
  duration_seconds: number
}

export interface DocumentOverview {
  document_id: string
  title: string
  document_summary: Summary | null
  section_summaries: Summary[]
  entity_count: number
  event_count: number
  key_topics: string[]
}

export interface DrillDownResult {
  summary: Summary
  parent: Summary | null
  children: Summary[]
  breadcrumb: Array<{ id: string; level: string; label: string }>
  source_chunks: Array<{ id: string; content: string }>
}

export interface EntitySearchParams {
  query: string
  entity_types?: string[]
  limit?: number
}

export interface EventSearchParams {
  start_date?: string
  end_date?: string
  event_types?: string[]
  entity_name?: string
}

export interface SummarySearchParams {
  query: string
  level?: 'chunk' | 'section' | 'document' | ''
  top_k?: number
}

export interface PipelineConfig {
  document_id: string
  pipeline_name: string
  config?: Record<string, unknown>
}

// ============================================================================
// Composable
// ============================================================================

export function useKnowledgeGraph() {
  // Reactive state
  const entities = ref<Entity[]>([])
  const relationships = ref<Relationship[]>([])
  const events = ref<TemporalEvent[]>([])
  const summaries = ref<Summary[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Quick stats
  const stats = reactive({
    entityCount: 0,
    eventCount: 0,
    summaryCount: 0,
  })

  const API_BASE = '/api/knowledge-graph'

  // --------------------------------------------------------------------
  // Helpers
  // --------------------------------------------------------------------

  function clearError(): void {
    error.value = null
  }

  function setError(err: unknown): void {
    error.value = err instanceof Error ? err.message : String(err)
    logger.error('Knowledge Graph error:', error.value)
  }

  function buildQueryString(params: Record<string, unknown>): string {
    const qs = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue
      if (Array.isArray(value)) {
        value.forEach(v => qs.append(key, String(v)))
      } else {
        qs.append(key, String(value))
      }
    }
    const result = qs.toString()
    return result ? `?${result}` : ''
  }

  // --------------------------------------------------------------------
  // Pipeline
  // --------------------------------------------------------------------

  async function runPipeline(
    config: PipelineConfig
  ): Promise<PipelineResult | null> {
    loading.value = true
    clearError()
    try {
      const data = await apiClient.post(
        `${API_BASE}/pipeline/run`, config
      )
      logger.info('Pipeline completed:', data?.pipeline_id)
      return data as PipelineResult
    } catch (err) {
      setError(err)
      return null
    } finally {
      loading.value = false
    }
  }

  // --------------------------------------------------------------------
  // Entities
  // --------------------------------------------------------------------

  async function searchEntities(
    params: EntitySearchParams
  ): Promise<void> {
    loading.value = true
    clearError()
    try {
      const qs = buildQueryString({
        query: params.query,
        entity_types: params.entity_types,
        limit: params.limit ?? 50,
      })
      const data = await apiClient.get(`${API_BASE}/entities${qs}`)
      entities.value = (
        data?.entities ?? data ?? []
      ) as Entity[]
      stats.entityCount = entities.value.length
    } catch (err) {
      setError(err)
      entities.value = []
    } finally {
      loading.value = false
    }
  }

  async function getRelationships(entityId: string): Promise<void> {
    loading.value = true
    clearError()
    try {
      const data = await apiClient.get(
        `${API_BASE}/entities/` +
        `${encodeURIComponent(entityId)}/relationships`
      )
      relationships.value = (
        data?.relationships ?? data ?? []
      ) as Relationship[]
    } catch (err) {
      setError(err)
      relationships.value = []
    } finally {
      loading.value = false
    }
  }

  // --------------------------------------------------------------------
  // Temporal Events
  // --------------------------------------------------------------------

  async function searchEvents(
    params: EventSearchParams
  ): Promise<void> {
    loading.value = true
    clearError()
    try {
      const qs = buildQueryString({
        start_date: params.start_date,
        end_date: params.end_date,
        event_types: params.event_types,
      })
      const data = await apiClient.get(`${API_BASE}/events${qs}`)
      events.value = (
        data?.events ?? data ?? []
      ) as TemporalEvent[]
      stats.eventCount = events.value.length
    } catch (err) {
      setError(err)
      events.value = []
    } finally {
      loading.value = false
    }
  }

  async function getTimeline(
    entityName: string
  ): Promise<TemporalEvent[]> {
    loading.value = true
    clearError()
    try {
      const data = await apiClient.get(
        `${API_BASE}/events/` +
        `${encodeURIComponent(entityName)}/timeline`
      )
      const timeline = (
        data?.events ?? data ?? []
      ) as TemporalEvent[]
      return timeline
    } catch (err) {
      setError(err)
      return []
    } finally {
      loading.value = false
    }
  }

  // --------------------------------------------------------------------
  // Summaries
  // --------------------------------------------------------------------

  async function searchSummaries(
    params: SummarySearchParams
  ): Promise<void> {
    loading.value = true
    clearError()
    try {
      const qs = buildQueryString({
        query: params.query,
        level: params.level,
        top_k: params.top_k ?? 10,
      })
      const data = await apiClient.get(
        `${API_BASE}/summaries/search${qs}`
      )
      summaries.value = (
        data?.summaries ?? data ?? []
      ) as Summary[]
      stats.summaryCount = summaries.value.length
    } catch (err) {
      setError(err)
      summaries.value = []
    } finally {
      loading.value = false
    }
  }

  async function getOverview(
    documentId: string
  ): Promise<DocumentOverview | null> {
    loading.value = true
    clearError()
    try {
      const data = await apiClient.get(
        `${API_BASE}/documents/` +
        `${encodeURIComponent(documentId)}/overview`
      )
      return data as DocumentOverview
    } catch (err) {
      setError(err)
      return null
    } finally {
      loading.value = false
    }
  }

  async function drillDown(
    summaryId: string
  ): Promise<DrillDownResult | null> {
    loading.value = true
    clearError()
    try {
      const data = await apiClient.get(
        `${API_BASE}/summaries/` +
        `${encodeURIComponent(summaryId)}/drill-down`
      )
      return data as DrillDownResult
    } catch (err) {
      setError(err)
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    // State
    entities,
    relationships,
    events,
    summaries,
    loading,
    error,
    stats,
    // Methods
    runPipeline,
    searchEntities,
    getRelationships,
    searchEvents,
    getTimeline,
    searchSummaries,
    getOverview,
    drillDown,
    clearError,
  }
}
