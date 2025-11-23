/**
 * Repository layer for API communication
 * Provides type-safe access to backend services
 */

import { NetworkConstants } from '@/constants/network'
import type { SearchResult } from '@/stores/useKnowledgeStore'

const API_BASE = `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}/api`

// Re-export chatRepository from its dedicated file
export { chatRepository } from './repositories/ChatRepository'

// Re-export SearchResult from store for convenience
export type { SearchResult }

// Response Types
export interface KnowledgeDocument {
  id: string
  title: string
  content: string
  type: string
  category: string
  updatedAt?: string
  tags?: string[]
}

// Raw backend search result (before transformation)
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
    [key: string]: any
  }
  node_id: string
}

export interface RagAnalysis {
  confidence: number
  sources_used: number
  query_reformulated: boolean
  context_used: string[]
}

export interface RagSearchResponse {
  results: SearchResult[]
  synthesized_response: string
  query: string
  reformulated_query?: string
  rag_analysis: RagAnalysis
  total_results: number
  mode: string
}

export interface SearchParams {
  query: string
  limit?: number
  use_rag?: boolean
  category?: string
  type?: string
  enable_reranking?: boolean
  filters?: {
    categories?: string[]
    tags?: string[]
    types?: string[]
  }
}

export interface RagSearchParams {
  query: string
  limit?: number
  reformulate_query?: boolean
}

/**
 * Knowledge Base Repository
 * Handles all knowledge base API interactions
 */
export class KnowledgeRepository {
  private baseUrl: string

  constructor(baseUrl = `${API_BASE}/knowledge_base`) {
    this.baseUrl = baseUrl
  }

  /**
   * Get search suggestions based on query
   */
  async getSearchSuggestions(query: string, limit: number = 8): Promise<string[]> {
    // Placeholder - implement when backend endpoint is available
    return []
  }

  /**
   * Add text content to knowledge base
   */
  async addTextToKnowledge(data: { content: string; title?: string; category?: string }): Promise<any> {
    const response = await fetch(`${this.baseUrl}/facts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
    return response.json()
  }

  /**
   * Add URL content to knowledge base
   */
  async addUrlToKnowledge(data: { url: string; title?: string; category?: string }): Promise<any> {
    const response = await fetch(`${this.baseUrl}/url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
    return response.json()
  }

  /**
   * Add file to knowledge base
   */
  async addFileToKnowledge(file: File, options: { title?: string; category?: string }): Promise<any> {
    const formData = new FormData()
    formData.append('file', file)
    if (options.title) formData.append('title', options.title)
    if (options.category) formData.append('category', options.category)

    const response = await fetch(`${this.baseUrl}/upload`, {
      method: 'POST',
      body: formData
    })
    return response.json()
  }

  /**
   * Update a knowledge base document
   */
  async updateDocument(documentId: string, updates: Partial<KnowledgeDocument>): Promise<any> {
    const response = await fetch(`${this.baseUrl}/facts/${documentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates)
    })
    return response.json()
  }

  /**
   * Delete a knowledge base document
   */
  async deleteDocument(documentId: string): Promise<any> {
    const response = await fetch(`${this.baseUrl}/facts/${documentId}`, {
      method: 'DELETE'
    })
    return response.json()
  }

  /**
   * Bulk delete documents
   */
  async bulkDeleteDocuments(documentIds: string[]): Promise<any> {
    const response = await fetch(`${this.baseUrl}/facts/bulk_delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_ids: documentIds })
    })
    return response.json()
  }

  /**
   * Get knowledge base statistics
   */
  async getKnowledgeStats(): Promise<any> {
    const response = await fetch(`${this.baseUrl}/stats/basic`)
    return response.json()
  }

  /**
   * Search knowledge base documents
   * Traditional semantic search without RAG enhancement
   */
  async searchKnowledge(params: SearchParams): Promise<SearchResult[]> {
    const response = await fetch(`${this.baseUrl}/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        query: params.query,
        limit: params.limit || 20,
        category: params.category,
        type: params.type
      })
    })

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`)
    }

    const data = await response.json()

    // Transform results to match expected format
    return data.results.map((result: any) => ({
      document: {
        id: result.metadata.fact_id,
        title: result.metadata.title || 'Untitled',
        content: result.content,
        type: result.metadata.type || 'text',
        category: result.metadata.category || 'general',
        updatedAt: result.metadata.stored_at
      },
      score: result.score,
      highlights: [result.content.substring(0, 200) + '...']
    }))
  }

  /**
   * RAG-enhanced search
   * Returns synthesized AI response with source documents
   */
  async ragSearch(params: RagSearchParams): Promise<RagSearchResponse> {
    const response = await fetch(`${this.baseUrl}/rag_search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        query: params.query,
        limit: params.limit || 10,
        reformulate_query: params.reformulate_query !== false
      })
    })

    if (!response.ok) {
      throw new Error(`RAG search failed: ${response.statusText}`)
    }

    const data = await response.json()

    // Transform results to match component expectations
    return {
      results: data.results.map((result: any) => ({
        document: {
          id: result.metadata.fact_id,
          title: result.metadata.title || 'Untitled',
          content: result.content,
          type: result.metadata.type || 'text',
          category: result.metadata.category || 'general'
        },
        score: result.score,
        highlights: [result.content.substring(0, 200) + '...']
      })),
      synthesized_response: data.synthesized_response || '',
      query: data.query,
      reformulated_query: data.reformulated_query,
      rag_analysis: data.rag_analysis || {
        confidence: 0.8,
        sources_used: data.results.length,
        query_reformulated: !!data.reformulated_query,
        context_used: []
      },
      total_results: data.total_results || data.results.length,
      mode: data.mode || 'rag'
    }
  }

  /**
   * Get all knowledge entries
   * Returns list of all knowledge base entries
   */
  async getAllEntries(collection?: string): Promise<any> {
    const url = collection
      ? `${this.baseUrl}/entries?collection=${encodeURIComponent(collection)}`
      : `${this.baseUrl}/entries`
    const response = await fetch(url)

    if (!response.ok) {
      throw new Error(`Failed to get entries: ${response.statusText}`)
    }

    const data = await response.json()
    return {
      success: true,
      entries: data.entries || [],
      total: data.total || data.entries?.length || 0
    }
  }

  /**
   * Get detailed knowledge base statistics
   * Returns comprehensive stats including documents by type and recent additions
   */
  async getDetailedKnowledgeStats(): Promise<any> {
    const response = await fetch(`${this.baseUrl}/detailed_stats`)

    if (!response.ok) {
      throw new Error(`Failed to get detailed stats: ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Export knowledge base
   * Returns knowledge base data as a downloadable file
   */
  async exportKnowledge(): Promise<Blob> {
    const response = await fetch(`${this.baseUrl}/export`)

    if (!response.ok) {
      throw new Error(`Export failed: ${response.statusText}`)
    }

    return response.blob()
  }

  /**
   * Cleanup knowledge base
   * Removes orphaned entries and optimizes storage
   */
  async cleanupKnowledge(): Promise<any> {
    const response = await fetch(`${this.baseUrl}/cleanup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })

    if (!response.ok) {
      throw new Error(`Cleanup failed: ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Reindex knowledge base
   * Rebuilds search indexes for improved performance
   */
  async reindexKnowledgeBase(): Promise<any> {
    const response = await fetch(`${this.baseUrl}/reindex`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })

    if (!response.ok) {
      throw new Error(`Reindex failed: ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Get similar documents
   * Finds documents similar to the specified document
   */
  async getSimilarDocuments(documentId: string, limit: number = 5): Promise<SearchResult[]> {
    const response = await fetch(`${this.baseUrl}/documents/${documentId}/similar?limit=${limit}`)

    if (!response.ok) {
      throw new Error(`Failed to get similar documents: ${response.statusText}`)
    }

    const data = await response.json()

    // Transform results to match expected format
    return data.results?.map((result: any) => ({
      document: {
        id: result.metadata?.fact_id || result.id,
        title: result.metadata?.title || 'Untitled',
        content: result.content,
        type: result.metadata?.type || 'text',
        category: result.metadata?.category || 'general',
        updatedAt: result.metadata?.stored_at
      },
      score: result.score || 0,
      highlights: [result.content?.substring(0, 200) + '...' || '']
    })) || []
  }

  /**
   * Get document by ID
   * Retrieves a specific knowledge document
   */
  async getDocument(documentId: string): Promise<KnowledgeDocument> {
    const response = await fetch(`${this.baseUrl}/documents/${documentId}`)

    if (!response.ok) {
      throw new Error(`Failed to get document: ${response.statusText}`)
    }

    return response.json()
  }
}

// Export singleton instance
export const knowledgeRepository = new KnowledgeRepository()
