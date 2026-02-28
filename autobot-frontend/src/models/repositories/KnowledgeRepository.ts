/**
 * KnowledgeRepository - Consolidated Knowledge Base API Repository
 *
 * This is the SINGLE SOURCE OF TRUTH for all knowledge base API interactions.
 * Do NOT create duplicate repository implementations elsewhere.
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */
import { ApiRepository } from './ApiRepository'
import type { KnowledgeDocument, SearchResult } from '@/stores/useKnowledgeStore'
import type {
  VerificationConfig,
  PendingSource
} from '@/types/knowledgeBase'

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
 * Basic knowledge base statistics
 */
export interface KnowledgeStats {
  total_documents: number
  total_categories: number
  total_size: number
  last_updated: string
  categories: Array<{
    name: string
    document_count: number
  }>
}

/**
 * Detailed knowledge base statistics with additional metrics
 */
export interface DetailedKnowledgeStats extends KnowledgeStats {
  documents_by_type: Record<string, number>
  recent_additions: KnowledgeDocument[]
  top_categories: Array<{
    name: string
    document_count: number
    total_size: number
  }>
}

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
    const response = await this.post('/api/knowledge_base/search', {
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
    const response = await this.post('/api/knowledge_base/rag_search', {
      query: request.query,
      top_k: request.top_k || 10,
      limit: request.limit || 10,
      reformulate_query: request.reformulate_query !== false
    })
    return response.data
  }

  // Legacy search method for backward compatibility
  async searchKnowledgeBase(query: string, limit: number = 5): Promise<SearchResult[]> {
    const response = await this.post('/api/knowledge_base/search', {
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
    const response = await this.post('/api/knowledge_base/facts', {
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
    const response = await this.post('/api/knowledge_base/add_text', {
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
    const response = await this.post('/api/knowledge_base/url', {
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

    const response = await this.post('/api/knowledge_base/upload', formData)
    return response.data
  }

  /**
   * Export knowledge base as downloadable file
   */
  async exportKnowledge(): Promise<Blob> {
    // Issue #552: Fixed path - backend uses /api/knowledge-maintenance/*
    const response = await this.post('/api/knowledge-maintenance/export')
    return response.data
  }

  /**
   * Cleanup knowledge base - removes orphaned entries
   */
  async cleanupKnowledge(): Promise<{ success: boolean; message: string; removed_count?: number }> {
    // Issue #552: Fixed path - backend uses /api/knowledge-maintenance/*
    const response = await this.post('/api/knowledge-maintenance/cleanup')
    return response.data
  }

  /**
   * Get basic knowledge base statistics
   */
  async getKnowledgeStats(): Promise<KnowledgeStats> {
    const response = await this.get('/api/knowledge_base/stats/basic')
    return response.data
  }

  /**
   * Get detailed knowledge base statistics
   */
  async getDetailedKnowledgeStats(): Promise<DetailedKnowledgeStats> {
    const response = await this.get('/api/knowledge_base/detailed_stats')
    return response.data
  }

  /**
   * Get all categories in knowledge base
   */
  async getCategories(): Promise<string[]> {
    const response = await this.get('/api/knowledge_base/categories')
    return response.data
  }

  /**
   * Get documents by category
   */
  async getDocumentsByCategory(category: string): Promise<KnowledgeDocument[]> {
    const response = await this.get(`/api/knowledge_base/categories/${encodeURIComponent(category)}/documents`)
    return response.data
  }

  /**
   * Get document by ID
   */
  async getDocument(documentId: string): Promise<KnowledgeDocument> {
    const response = await this.get(`/api/knowledge_base/documents/${documentId}`)
    return response.data
  }

  /**
   * Update document by ID
   */
  async updateDocument(documentId: string, updates: Partial<KnowledgeDocument>): Promise<KnowledgeDocument> {
    // Use facts endpoint for consistency with backend
    const response = await this.put(`/api/knowledge_base/facts/${documentId}`, updates)
    return response.data
  }

  /**
   * Delete document by ID
   */
  async deleteDocument(documentId: string): Promise<{ success: boolean; message: string }> {
    // Use facts endpoint for consistency with backend
    const response = await this.delete(`/api/knowledge_base/facts/${documentId}`)
    return response.data
  }

  /**
   * Bulk delete multiple documents
   * Issue #552: Note - Backend uses collection-based bulk delete at
   * POST /api/knowledge_base/collections/{collection_id}/bulk-delete
   * This endpoint may need adjustment based on collection context
   */
  async bulkDeleteDocuments(documentIds: string[], collectionId: string = 'default'): Promise<{ success: boolean; deleted_count: number }> {
    const response = await this.post(`/api/knowledge_base/collections/${collectionId}/bulk-delete`, {
      fact_ids: documentIds
    })
    return response.data
  }

  /**
   * Get similar documents to a given document
   */
  async getSimilarDocuments(documentId: string, limit: number = 5): Promise<SearchResult[]> {
    const response = await this.get(`/api/knowledge_base/documents/${documentId}/similar?limit=${limit}`)

    // Transform results to match SearchResult format
    const results = response.data.results || response.data || []
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
      const response = await this.get(`/api/knowledge_base/suggestions?query=${encodeURIComponent(query)}&limit=${limit}`)
      return response.data || []
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
    const response = await this.post('/api/rebuild_index')
    return response.data
  }

  /**
   * Check knowledge base health status
   */
  async checkKnowledgeBaseHealth(): Promise<{ healthy: boolean; message: string }> {
    const response = await this.get('/api/knowledge_base/health')
    return response.data
  }

  // ==========================================================================
  // Source Verification & Provenance (Issue #1253)
  // ==========================================================================

  /**
   * Get paginated list of sources pending verification
   */
  async getPendingVerifications(
    page = 1,
    pageSize = 20
  ): Promise<{ sources: PendingSource[]; total: number; page: number }> {
    const response = await this.get(
      `/api/knowledge_base/verification/pending?page=${page}&page_size=${pageSize}`,
      { skipCache: true }
    )
    return response.data
  }

  /**
   * Approve a pending source by fact_id
   */
  async approveSource(
    factId: string,
    user: string
  ): Promise<{ status: string; message: string }> {
    const response = await this.post(
      `/api/knowledge_base/verification/${encodeURIComponent(factId)}/approve`,
      { user, delete_on_reject: false }
    )
    return response.data
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
      `/api/knowledge_base/verification/${encodeURIComponent(factId)}/reject`,
      { user, delete_on_reject: deleteOnReject }
    )
    return response.data
  }

  /**
   * Get current verification configuration
   */
  async getVerificationConfig(): Promise<VerificationConfig> {
    const response = await this.get(
      '/api/knowledge_base/verification/config',
      { skipCache: true }
    )
    return response.data
  }

  /**
   * Update verification configuration
   */
  async updateVerificationConfig(
    config: VerificationConfig
  ): Promise<{ status: string; config: VerificationConfig }> {
    const response = await this.put(
      '/api/knowledge_base/verification/config',
      config
    )
    return response.data
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
      ? `/api/knowledge_base/entries?collection=${encodeURIComponent(collection)}`
      : '/api/knowledge_base/entries'
    const response = await this.get(url)

    // Normalize response format
    const data = response.data
    return {
      success: true,
      entries: data.entries || [],
      total: data.total || data.entries?.length || 0
    }
  }
}

// Create and export singleton instance
export const knowledgeRepository = new KnowledgeRepository()
