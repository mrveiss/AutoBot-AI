// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * KnowledgeRepository - Consolidated Knowledge Base API Repository
 *
 * This is the SINGLE SOURCE OF TRUTH for all knowledge base API interactions.
 * Do NOT create duplicate repository implementations elsewhere.
 *
 * @author mrveiss
 */
import { ApiRepository } from './ApiRepository'
import type { KnowledgeDocument, SearchResult } from '@/stores/useKnowledgeStore'
import type {
  VerificationConfig,
  PendingSource,
  ConnectorConfig,
  ConnectorStatus,
  SyncResult
} from '@/types/knowledgeBase'
// Issue #5209: canonical request types generated from backend OpenAPI schema.
// Prefer these over hand-written duplicates for wire-format types.
// Issue #5248: KB stats + category response types now also come from
// backend Pydantic schemas via the same OpenAPI pipeline.
import type {
  CreateConnectorRequest,
  UpdateConnectorRequest,
  KnowledgeStatsBasic,
  KnowledgeCategoryEntry as ApiKnowledgeCategoryEntry,
  DetailedKnowledgeStats as ApiDetailedKnowledgeStats
} from '@/types/api-contract'
import { getApiBase } from '@/config/ssot-config'

// Re-export types for convenience
export type { KnowledgeDocument, SearchResult }

/**
 * Search request parameters for knowledge base queries
 */
export interface SearchKnowledgeRequest {
  query: string
  limit?: number
  /** Category filter (single category) */
  category?: string
  /** Type filter (single type) */
  type?: string
  /** Advanced filters object */
  filters?: {
    categories?: string[]
    tags?: string[]
    types?: string[]
  }
  use_rag?: boolean
  enable_reranking?: boolean
}

/**
 * RAG-enhanced search request parameters
 */
export interface RagSearchRequest {
  query: string
  top_k?: number
  limit?: number
  reformulate_query?: boolean
}

/**
 * RAG search response with synthesized AI response
 */
export interface RagSearchResponse {
  status: string
  synthesized_response: string
  results: SearchResult[]
  query: string
  reformulated_query?: string
  rag_analysis?: {
    relevance_score: number
    confidence: number
    sources_used: number
    synthesis_quality: string
    query_reformulated?: boolean
    context_used?: string[]
  }
  total_results?: number
  mode?: string
  message?: string
}

/**
 * Request to add text content to knowledge base
 * Supports both 'text' and 'content' fields for backward compatibility
 * Issue #685: Added hierarchical access level fields
 */
export interface AddTextRequest {
  /** Text content to add (primary field) */
  text?: string
  /** Content to add (alias for text, used by some callers) */
  content?: string
  title?: string
  source?: string
  category?: string
  tags?: string[]
  // Issue #685: Hierarchical access fields
  access_level?: string
  visibility?: string
  owner_id?: string
  organization_id?: string
  group_ids?: string[]
  shared_with?: string[]
}

/**
 * Request to add URL content to knowledge base
 */
export interface AddUrlRequest {
  url: string
  title?: string
  method?: string
  category?: string
  tags?: string[]
}

/**
 * Options for adding file to knowledge base
 */
export interface AddFileOptions {
  title?: string
  category?: string
  tags?: string[]
}

/**
 * Basic knowledge base statistics as returned by `/api/knowledge_base/stats/basic`.
 *
 * Issue #5248: aliased to the backend-generated `KnowledgeStatsBasic` Pydantic
 * schema (in `autobot-backend/knowledge/schemas/stats.py`) via OpenAPI type-gen.
 * The #5215 hand-written duplicate has been replaced with this alias so drift
 * between Python and TS is structurally impossible.
 */
export type KnowledgeStats = KnowledgeStatsBasic

/**
 * Size-breakdown block inside `DetailedKnowledgeStats`.
 *
 * Issue #5248: kept as a hand-written interface (not in OpenAPI) because it's
 * referenced directly from callers that want to construct a zero-default
 * fallback without importing the nested schema.
 */
export interface DetailedKnowledgeSizeMetrics {
  total_content_size: number
  average_fact_size: number
  median_fact_size: number
  largest_fact_size: number
  smallest_fact_size: number
}

/**
 * Detailed knowledge base statistics as returned by
 * `/api/knowledge_base/detailed_stats`.
 *
 * Issue #5248: aliased to the backend-generated `DetailedKnowledgeStats`
 * Pydantic schema via OpenAPI type-gen. Kept as a local `type` (not re-export)
 * so existing consumers keep importing `DetailedKnowledgeStats` from this
 * module unchanged.
 */
export type DetailedKnowledgeStats = ApiDetailedKnowledgeStats

/**
 * A single category row from `/api/knowledge_base/categories`.
 *
 * Issue #5248: aliased to the backend-generated `KnowledgeCategoryEntry`
 * Pydantic schema via OpenAPI type-gen.
 */
export type KnowledgeCategoryEntry = ApiKnowledgeCategoryEntry

/**
 * Raw backend search result (before transformation)
 */
export interface BackendSearchResult {
  content: string
  score: number
  metadata: {
    title: string
    source: string
    category: string
    type: string
    file_path?: string
    fact_id: string
    stored_at?: string
    [key: string]: unknown
  }
  node_id: string
}

/**
 * KnowledgeRepository - Consolidated Knowledge Base API Repository
 *
 * Extends ApiRepository to provide caching, timeout handling, and error management.
 */
export class KnowledgeRepository extends ApiRepository {
  /**
   * Search knowledge base documents
   * Supports both simple and advanced filtering
   */
  async searchKnowledge(request: SearchKnowledgeRequest): Promise<SearchResult[]> {
    const response = await this.post<{ results: BackendSearchResult[] }>(`${getApiBase()}/knowledge_base/search`, {
      query: request.query,
      limit: request.limit || 20,
      category: request.category,
      type: request.type,
      use_rag: request.use_rag || false,
      enable_reranking: request.enable_reranking || false,
      // Spread filters if provided
      ...(request.filters?.categories && { categories: request.filters.categories }),
      ...(request.filters?.tags && { tags: request.filters.tags }),
      ...(request.filters?.types && { types: request.filters.types })
    })

    // Backend returns { results: [...], total_results: N, ... }
    // Transform results to match expected SearchResult format
    const results = response.data.results || []
    return results.map((result: BackendSearchResult) => ({
      document: {
        id: result.metadata?.fact_id || result.node_id,
        title: result.metadata?.title || 'Untitled',
        content: result.content,
        type: result.metadata?.type || 'document',
        category: result.metadata?.category || 'General',
        source: result.metadata?.source || 'Unknown',
        tags: [],
        createdAt: new Date(),
        updatedAt: result.metadata?.stored_at ? new Date(result.metadata.stored_at) : new Date()
      } as KnowledgeDocument,
      score: result.score,
      highlights: [result.content?.substring(0, 200) + '...' || '']
    }))
  }

  // RAG-enhanced search using dedicated endpoint
  async ragSearch(request: RagSearchRequest): Promise<RagSearchResponse> {
    const response = await this.post<RagSearchResponse>(`${getApiBase()}/knowledge_base/rag_search`, {
      query: request.query,
      top_k: request.top_k || 10,
      limit: request.limit || 10,
      reformulate_query: request.reformulate_query !== false
    })
    return response.data
  }

  // Legacy search method for backward compatibility
  async searchKnowledgeBase(query: string, limit: number = 5): Promise<SearchResult[]> {
    const response = await this.post<{ results: SearchResult[] }>(`${getApiBase()}/knowledge_base/search`, {
      query,
      n_results: limit
    })
    // Backend returns { results: [...], total_results: N, ... }
    // Extract just the results array
    return response.data.results || []
  }

  /**
   * Add text content to knowledge base
   * Supports both 'text' and 'content' fields for backward compatibility
   */
  async addTextToKnowledge(request: AddTextRequest): Promise<{
    success: boolean
    document_id?: string
    title?: string
    content?: string
    message?: string
  }> {
    // Support both 'text' and 'content' fields
    const textContent = request.text || request.content || ''
    const response = await this.post<{ success: boolean; document_id?: string; title?: string; content?: string; message?: string }>(`${getApiBase()}/knowledge_base/facts`, {
      content: textContent,
      title: request.title || '',
      source: request.source || 'Manual Entry',
      category: request.category,
      tags: request.tags
    })
    return response.data
  }

  // Legacy add text method
  // Issue #552: Fixed path - backend uses /api/knowledge_base/add_text
  async addKnowledge(content: string, metadata: Record<string, any> = {}): Promise<any> {
    const response = await this.post<Record<string, unknown>>(`${getApiBase()}/knowledge_base/add_text`, {
      content,
      metadata
    })
    return response.data
  }

  /**
   * Add URL content to knowledge base
   * Fetches and processes content from the URL
   */
  async addUrlToKnowledge(request: AddUrlRequest): Promise<{
    success: boolean
    document_id?: string
    title?: string
    content?: string
    message?: string
  }> {
    const response = await this.post<{ success: boolean; document_id?: string; title?: string; content?: string; message?: string }>(`${getApiBase()}/knowledge_base/url`, {
      url: request.url,
      title: request.title,
      method: request.method || 'fetch',
      category: request.category,
      tags: request.tags
    })
    return response.data
  }

  /**
   * Add file to knowledge base
   * Uploads and processes file content
   */
  async addFileToKnowledge(file: File, options?: AddFileOptions): Promise<{
    success: boolean
    document_id?: string
    title?: string
    content?: string
    word_count?: number
    message?: string
  }> {
    const formData = new FormData()
    formData.append('file', file)

    if (options?.title) {
      formData.append('title', options.title)
    }

    if (options?.category) {
      formData.append('category', options.category)
    }

    if (options?.tags) {
      formData.append('tags', JSON.stringify(options.tags))
    }

    const response = await this.post<{ success: boolean; document_id?: string; title?: string; content?: string; word_count?: number; message?: string }>(`${getApiBase()}/knowledge_base/upload`, formData)
    return response.data
  }

  /**
   * Export knowledge base as downloadable file
   */
  async exportKnowledge(): Promise<Blob> {
    // Issue #552: Fixed path - backend uses /api/knowledge-maintenance/*
    const response = await this.post<Blob>(`${getApiBase()}/knowledge-maintenance/export`)
    return response.data
  }

  /**
   * Cleanup knowledge base - removes orphaned entries
   */
  async cleanupKnowledge(): Promise<{ success: boolean; message: string; removed_count?: number }> {
    // Issue #552: Fixed path - backend uses /api/knowledge-maintenance/*
    const response = await this.post<{ success: boolean; message: string; removed_count?: number }>(`${getApiBase()}/knowledge-maintenance/cleanup`)
    return response.data
  }

  /**
   * Get basic knowledge base statistics from `/api/knowledge_base/stats/basic`.
   *
   * Issue #5215 (#5207 audit): the previous declaration was a lie — it
   * promised `total_documents` / `total_categories` / `total_size` /
   * `last_updated` and a structured `categories` list, none of which the
   * backend returns. Nulls in the envelope collapse to a safe empty default
   * rather than propagating `undefined` into render code.
   */
  async getKnowledgeStats(): Promise<KnowledgeStats> {
    const response = await this.get<KnowledgeStats>(`${getApiBase()}/knowledge_base/stats/basic`)
    const data = response?.data
    return {
      total_facts: data?.total_facts ?? 0,
      total_vectors: data?.total_vectors ?? 0,
      categories: Array.isArray(data?.categories) ? data.categories : [],
      status: data?.status ?? 'unknown'
    }
  }

  /**
   * Get detailed knowledge base statistics from
   * `/api/knowledge_base/detailed_stats`.
   *
   * Issue #5215 (#5207 audit): the backend returns a nested envelope
   * (`basic_stats`, `category_breakdown`, `source_breakdown`,
   * `type_breakdown`, `size_metrics`, `rag_available`). The previous type
   * claimed a flat shape with `documents_by_type` / `recent_additions` /
   * `top_categories` that the backend never emits.
   */
  async getDetailedKnowledgeStats(): Promise<DetailedKnowledgeStats> {
    const response = await this.get<DetailedKnowledgeStats>(`${getApiBase()}/knowledge_base/detailed_stats`)
    const data = response?.data
    return {
      status: data?.status ?? 'unknown',
      basic_stats: data?.basic_stats ?? {
        total_documents: 0,
        total_chunks: 0,
        total_facts: 0,
        total_vectors: 0,
        db_size: 0,
        categories: [],
        status: 'unknown'
      },
      category_breakdown: data?.category_breakdown ?? {},
      source_breakdown: data?.source_breakdown ?? {},
      type_breakdown: data?.type_breakdown ?? {},
      size_metrics: data?.size_metrics ?? {
        total_content_size: 0,
        average_fact_size: 0,
        median_fact_size: 0,
        largest_fact_size: 0,
        smallest_fact_size: 0
      },
      rag_available: data?.rag_available ?? false
    }
  }

  /**
   * Get all categories in knowledge base from `/api/knowledge_base/categories`.
   *
   * Issue #5215: backend returns `{categories: KnowledgeCategoryEntry[], total}`;
   * the previous declaration promised `string[]`. We unwrap the envelope so
   * callers (e.g. `KnowledgeController.loadCategories`) receive real
   * `{name, count, id}` rows instead of having to probe the unexpected shape.
   */
  async getCategories(): Promise<KnowledgeCategoryEntry[]> {
    const response = await this.get<{
      categories: KnowledgeCategoryEntry[]
      total: number
    }>(`${getApiBase()}/knowledge_base/categories`)
    const list = response?.data?.categories
    return Array.isArray(list) ? list : []
  }

  /**
   * Get documents by category
   */
  async getDocumentsByCategory(category: string): Promise<KnowledgeDocument[]> {
    const response = await this.get<KnowledgeDocument[]>(`${getApiBase()}/knowledge_base/categories/${encodeURIComponent(category)}/documents`)
    return response.data
  }

  /**
   * Get document by ID
   */
  async getDocument(documentId: string): Promise<KnowledgeDocument> {
    const response = await this.get<KnowledgeDocument>(`${getApiBase()}/knowledge_base/documents/${documentId}`)
    return response.data
  }

  /**
   * Update document by ID
   */
  async updateDocument(documentId: string, updates: Partial<KnowledgeDocument>): Promise<KnowledgeDocument> {
    // Use facts endpoint for consistency with backend
    const response = await this.put<KnowledgeDocument>(`${getApiBase()}/knowledge_base/facts/${documentId}`, updates)
    return response.data
  }

  /**
   * Delete document by ID
   */
  async deleteDocument(documentId: string): Promise<{ success: boolean; message: string }> {
    // Use facts endpoint for consistency with backend
    const response = await this.delete<{ success: boolean; message: string }>(`${getApiBase()}/knowledge_base/facts/${documentId}`)
    return response.data
  }

  /**
   * Bulk delete multiple documents
   * Issue #552: Note - Backend uses collection-based bulk delete at
   * POST /api/knowledge_base/collections/{collection_id}/bulk-delete
   * This endpoint may need adjustment based on collection context
   */
  async bulkDeleteDocuments(documentIds: string[], collectionId: string = 'default'): Promise<{ success: boolean; deleted_count: number }> {
    const response = await this.post<{ success: boolean; deleted_count: number }>(`${getApiBase()}/knowledge_base/collections/${collectionId}/bulk-delete`, {
      fact_ids: documentIds
    })
    return response.data
  }

  /**
   * Get similar documents to a given document
   */
  async getSimilarDocuments(documentId: string, limit: number = 5): Promise<SearchResult[]> {
    const response = await this.get<{ results: BackendSearchResult[] }>(`${getApiBase()}/knowledge_base/documents/${documentId}/similar?limit=${limit}`)

    // Transform results to match SearchResult format
    const results = (response.data as any).results || response.data || []
    return results.map((result: BackendSearchResult) => ({
      document: {
        id: result.metadata?.fact_id || result.node_id,
        title: result.metadata?.title || 'Untitled',
        content: result.content,
        type: result.metadata?.type || 'document',
        category: result.metadata?.category || 'General',
        source: result.metadata?.source || 'Unknown',
        tags: [],
        createdAt: new Date(),
        updatedAt: result.metadata?.stored_at ? new Date(result.metadata.stored_at) : new Date()
      } as KnowledgeDocument,
      score: result.score || 0,
      highlights: [result.content?.substring(0, 200) + '...' || '']
    }))
  }

  /**
   * Get search suggestions based on query prefix
   */
  async getSearchSuggestions(query: string, limit: number = 8): Promise<string[]> {
    try {
      const response = await this.get<string[]>(`${getApiBase()}/knowledge_base/suggestions?query=${encodeURIComponent(query)}&limit=${limit}`)
      return (response.data as any) || []
    } catch {
      // Return empty array if suggestions endpoint not available
      return []
    }
  }

  /**
   * Reindex knowledge base for improved search performance
   * Issue #552: Note - Backend uses /api/rebuild_index for global reindex
   * Consider using vectorize_facts/background for knowledge base specific reindex
   */
  async reindexKnowledgeBase(): Promise<{ success: boolean; message: string }> {
    const response = await this.post<{ success: boolean; message: string }>(`${getApiBase()}/rebuild_index`)
    return response.data
  }

  /**
   * Check knowledge base health status
   */
  async checkKnowledgeBaseHealth(): Promise<{ healthy: boolean; message: string }> {
    const response = await this.get<{ healthy: boolean; message: string }>(`${getApiBase()}/knowledge_base/health`)
    return response.data
  }

  // ==========================================================================
  // Source Verification & Provenance (Issue #1253)
  // ==========================================================================

  /**
   * Get paginated list of sources pending verification.
   *
   * Backend (api/knowledge_verification.py) returns
   * `{status, pending, total, limit, offset, has_more}` — the array field is
   * `pending` (not `sources`) and pagination is `offset`-based (not `page`).
   * Unpacked here into the caller-friendly `{sources, total, page}` shape
   * to preserve the existing component/store API. (#5207 audit)
   */
  async getPendingVerifications(
    page = 1,
    pageSize = 20
  ): Promise<{ sources: PendingSource[]; total: number; page: number }> {
    const offset = Math.max(0, (page - 1) * pageSize)
    const response = await this.get<{
      status?: string
      pending?: PendingSource[]
      total?: number
      limit?: number
      offset?: number
      has_more?: boolean
    }>(
      `${getApiBase()}/knowledge_base/verification/pending?limit=${pageSize}&offset=${offset}`,
      { skipCache: true }
    )
    const raw = response.data ?? {}
    return {
      sources: raw.pending ?? [],
      total: raw.total ?? 0,
      page
    }
  }

  /**
   * Approve a pending source by fact_id
   */
  async approveSource(
    factId: string,
    user: string
  ): Promise<{ status: string; message: string }> {
    const response = await this.post(
      `${getApiBase()}/knowledge_base/verification/${encodeURIComponent(factId)}/approve`,
      { user, delete_on_reject: false }
    )
    return response.data as { status: string; message: string }
  }

  /**
   * Reject a pending source by fact_id
   */
  async rejectSource(
    factId: string,
    user: string,
    deleteOnReject = false
  ): Promise<{ status: string; message: string }> {
    const response = await this.post(
      `${getApiBase()}/knowledge_base/verification/${encodeURIComponent(factId)}/reject`,
      { user, delete_on_reject: deleteOnReject }
    )
    return response.data as { status: string; message: string }
  }

  /**
   * Get current verification configuration.
   *
   * Backend returns `{status, config}`; we extract `.config` so callers get a
   * flat `VerificationConfig` matching the declared return type. (#5207 audit)
   */
  async getVerificationConfig(): Promise<VerificationConfig> {
    const response = await this.get<{
      status?: string
      config: VerificationConfig
    }>(
      `${getApiBase()}/knowledge_base/verification/config`,
      { skipCache: true }
    )
    return response.data.config
  }

  /**
   * Update verification configuration
   */
  async updateVerificationConfig(
    config: VerificationConfig
  ): Promise<{ status: string; config: VerificationConfig }> {
    const response = await this.put(
      `${getApiBase()}/knowledge_base/verification/config`,
      config
    )
    return response.data as { status: string; config: VerificationConfig }
  }

  // ==========================================================================
  // Connector Management (Issue #1255)
  // ==========================================================================

  /**
   * List all connectors with their statuses.
   *
   * Backend returns `{connectors: [{config, status}, ...], total}` — an array
   * of wrapped pairs. Here we unpack into two parallel structures so the
   * store and components can key status lookups by `connector_id` (#5200).
   */
  async listConnectors(): Promise<{
    connectors: ConnectorConfig[]
    statuses: Record<string, ConnectorStatus>
  }> {
    const response = await this.get<{
      connectors: Array<{ config: ConnectorConfig; status: ConnectorStatus }>
      total: number
    }>(`${getApiBase()}/knowledge_base/connectors`, { skipCache: true })

    const configs: ConnectorConfig[] = []
    const statuses: Record<string, ConnectorStatus> = {}
    for (const entry of response.data?.connectors ?? []) {
      if (!entry?.config?.connector_id) continue
      configs.push(entry.config)
      statuses[entry.config.connector_id] = entry.status
    }
    return { connectors: configs, statuses }
  }

  /**
   * Create a new connector.
   *
   * Backend returns `{connector_id, config}`; we extract `.config` so callers
   * get a flat `ConnectorConfig` matching the declared return type (#5200).
   *
   * Body type aligns with backend `CreateConnectorRequest` Pydantic schema
   * (generated — see `@/types/api-contract`).
   */
  async createConnector(
    config: Partial<ConnectorConfig> | CreateConnectorRequest
  ): Promise<ConnectorConfig> {
    const response = await this.post<{
      connector_id: string
      config: ConnectorConfig
    }>(`${getApiBase()}/knowledge_base/connectors`, config)
    return response.data.config
  }

  /**
   * Get a single connector with its status
   */
  async getConnector(
    id: string
  ): Promise<{ config: ConnectorConfig; status: ConnectorStatus }> {
    const response = await this.get(
      `${getApiBase()}/knowledge_base/connectors/${encodeURIComponent(id)}`,
      { skipCache: true }
    )
    return response.data as { config: ConnectorConfig; status: ConnectorStatus }
  }

  /**
   * Update connector configuration.
   *
   * Backend returns `{connector_id, config}`; we extract `.config` so callers
   * get a flat `ConnectorConfig` matching the declared return type (#5200).
   *
   * Body type aligns with backend `UpdateConnectorRequest` Pydantic schema
   * (generated — see `@/types/api-contract`).
   */
  async updateConnector(
    id: string,
    updates: Partial<ConnectorConfig> | UpdateConnectorRequest
  ): Promise<ConnectorConfig> {
    const response = await this.put<{
      connector_id: string
      config: ConnectorConfig
    }>(
      `${getApiBase()}/knowledge_base/connectors/${encodeURIComponent(id)}`,
      updates
    )
    return response.data.config
  }

  /**
   * Delete a connector
   */
  async deleteConnector(id: string): Promise<void> {
    await this.delete(
      `${getApiBase()}/knowledge_base/connectors/${encodeURIComponent(id)}`
    )
  }

  /**
   * Test a connector's connection.
   *
   * Backend returns `{connector_id, healthy}`; we normalise into the
   * `{success, message}` shape the UI expects. Message is synthesised from
   * `healthy` because the backend does not currently expose a diagnostic
   * string. (#5203, #5207 audit)
   */
  async testConnector(
    id: string
  ): Promise<{ success: boolean; message: string }> {
    const response = await this.post<{
      connector_id?: string
      healthy?: boolean
    }>(
      `${getApiBase()}/knowledge_base/connectors/${encodeURIComponent(id)}/test`
    )
    const healthy = response.data?.healthy === true
    return {
      success: healthy,
      message: healthy ? 'Connection OK' : 'Connection failed',
    }
  }

  /**
   * Trigger a sync for a connector.
   *
   * The POST endpoint only _starts_ a background sync and returns
   * `{connector_id, status: "sync_started", incremental}` — it does NOT
   * return a completed `SyncResult`. Callers that want the actual result
   * must poll `getConnectorHistory(id)` after sync completes.
   *
   * Previously declared `Promise<SyncResult>` which made callers read
   * `.added/.updated/.deleted` that never existed. (#5204, #5207 audit)
   */
  async syncConnector(
    id: string,
    incremental = true
  ): Promise<{
    connector_id: string
    status: string
    incremental: boolean
  }> {
    const response = await this.post<{
      connector_id?: string
      status?: string
      incremental?: boolean
    }>(
      `${getApiBase()}/knowledge_base/connectors/${encodeURIComponent(id)}/sync?incremental=${incremental}`
    )
    return {
      connector_id: response.data?.connector_id ?? id,
      status: response.data?.status ?? 'unknown',
      incremental: response.data?.incremental ?? incremental
    }
  }

  /**
   * Get sync history for a connector.
   *
   * Backend returns `{connector_id, history, total}`; we extract `.history`
   * so callers get a flat `SyncResult[]` matching the declared return type.
   * Previously cast the whole envelope to `SyncResult[]`, which silently
   * became a non-iterable object. (#5207 audit)
   */
  async getConnectorHistory(
    id: string,
    limit = 20
  ): Promise<SyncResult[]> {
    const response = await this.get<{
      connector_id?: string
      history?: SyncResult[]
      total?: number
    }>(
      `${getApiBase()}/knowledge_base/connectors/${encodeURIComponent(id)}/history?limit=${limit}`,
      { skipCache: true }
    )
    return response.data?.history ?? []
  }


  /**
   * Get all knowledge entries with optional collection filter
   */
  async getAllEntries(collection?: string): Promise<{
    success: boolean
    entries: Array<{
      id: string
      fact_id?: string
      fact?: string
      content?: string
      metadata?: Record<string, unknown>
      created_at?: string
      updated_at?: string
    }>
    total: number
  }> {
    const url = collection
      ? `${getApiBase()}/knowledge_base/entries?collection=${encodeURIComponent(collection)}`
      : `${getApiBase()}/knowledge_base/entries`
    const response = await this.get(url)

    // Normalize response format
    const data = response.data as {
      entries?: Array<{
        id: string; fact_id?: string; fact?: string; content?: string
        metadata?: Record<string, unknown>; created_at?: string; updated_at?: string
      }>
      total?: number
    }
    return {
      success: true,
      entries: data.entries || [],
      total: data.total || data.entries?.length || 0
    }
  }
}

// Create and export singleton instance
export const knowledgeRepository = new KnowledgeRepository()
