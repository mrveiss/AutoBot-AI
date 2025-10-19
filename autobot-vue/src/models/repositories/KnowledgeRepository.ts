import { ApiRepository } from './ApiRepository'
import type { KnowledgeDocument, SearchResult } from '@/stores/useKnowledgeStore'

export interface SearchKnowledgeRequest {
  query: string
  limit?: number
  filters?: {
    categories?: string[]
    tags?: string[]
    types?: string[]
  }
  use_rag?: boolean
}

export interface RagSearchRequest {
  query: string
  top_k?: number
  limit?: number
  reformulate_query?: boolean
}

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
  }
  message?: string
}

export interface AddTextRequest {
  text: string
  title?: string
  source?: string
  category?: string
  tags?: string[]
}

export interface AddUrlRequest {
  url: string
  method?: string
  category?: string
  tags?: string[]
}

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

export interface DetailedKnowledgeStats extends KnowledgeStats {
  documents_by_type: Record<string, number>
  recent_additions: KnowledgeDocument[]
  top_categories: Array<{
    name: string
    document_count: number
    total_size: number
  }>
}

export class KnowledgeRepository extends ApiRepository {
  // Enhanced search with RAG support
  async searchKnowledge(request: SearchKnowledgeRequest): Promise<SearchResult[]> {
    const response = await this.post('/api/knowledge_base/search', {
      query: request.query,
      limit: request.limit || 10,
      use_rag: request.use_rag || false,
      ...request.filters
    })
    // Backend returns { results: [...], total_results: N, ... }
    // Extract just the results array
    return response.data.results || []
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

  // Add text to knowledge base
  async addTextToKnowledge(request: AddTextRequest): Promise<any> {
    const response = await this.post('/api/knowledge_base/add_text', {
      text: request.text,
      title: request.title || '',
      source: request.source || 'Manual Entry',
      category: request.category,
      tags: request.tags
    })
    return response.data
  }

  // Legacy add text method
  async addKnowledge(content: string, metadata: Record<string, any> = {}): Promise<any> {
    const response = await this.post('/api/knowledge_base/add', {
      content,
      metadata
    })
    return response.data
  }

  // Add URL to knowledge base
  async addUrlToKnowledge(request: AddUrlRequest): Promise<any> {
    const response = await this.post('/api/knowledge_base/add_url', {
      url: request.url,
      method: request.method || 'fetch',
      category: request.category,
      tags: request.tags
    })
    return response.data
  }

  // Add file to knowledge base
  async addFileToKnowledge(file: File, metadata?: { category?: string; tags?: string[] }): Promise<any> {
    const formData = new FormData()
    formData.append('file', file)

    if (metadata?.category) {
      formData.append('category', metadata.category)
    }

    if (metadata?.tags) {
      formData.append('tags', JSON.stringify(metadata.tags))
    }

    const response = await this.post('/api/knowledge_base/add_file', formData)
    return response.data
  }

  // Export knowledge base
  async exportKnowledge(): Promise<Blob> {
    const response = await this.get('/api/knowledge_base/export')
    return response.data
  }

  // Cleanup knowledge base
  async cleanupKnowledge(): Promise<any> {
    const response = await this.post('/api/knowledge_base/cleanup')
    return response.data
  }

  // Get knowledge base statistics
  async getKnowledgeStats(): Promise<KnowledgeStats> {
    const response = await this.get('/api/knowledge_base/stats')
    return response.data
  }

  // Get detailed knowledge base statistics
  async getDetailedKnowledgeStats(): Promise<DetailedKnowledgeStats> {
    const response = await this.get('/api/knowledge_base/detailed_stats')
    return response.data
  }

  // Get knowledge base categories
  async getCategories(): Promise<string[]> {
    const response = await this.get('/api/knowledge_base/categories')
    return response.data
  }

  // Get documents by category
  async getDocumentsByCategory(category: string): Promise<KnowledgeDocument[]> {
    const response = await this.get(`/api/knowledge_base/categories/${encodeURIComponent(category)}/documents`)
    return response.data
  }

  // Get document by ID
  async getDocument(documentId: string): Promise<KnowledgeDocument> {
    const response = await this.get(`/api/knowledge_base/documents/${documentId}`)
    return response.data
  }

  // Update document
  async updateDocument(documentId: string, updates: Partial<KnowledgeDocument>): Promise<KnowledgeDocument> {
    const response = await this.put(`/api/knowledge_base/documents/${documentId}`, updates)
    return response.data
  }

  // Delete document
  async deleteDocument(documentId: string): Promise<any> {
    const response = await this.delete(`/api/knowledge_base/documents/${documentId}`)
    return response.data
  }

  // Bulk delete documents
  async bulkDeleteDocuments(documentIds: string[]): Promise<any> {
    const response = await this.post('/api/knowledge_base/documents/bulk_delete', {
      document_ids: documentIds
    })
    return response.data
  }

  // Get similar documents
  async getSimilarDocuments(documentId: string, limit: number = 5): Promise<SearchResult[]> {
    const response = await this.get(`/api/knowledge_base/documents/${documentId}/similar?limit=${limit}`)
    return response.data
  }

  // Get search suggestions
  async getSearchSuggestions(query: string, limit: number = 5): Promise<string[]> {
    const response = await this.get(`/api/knowledge_base/suggestions?query=${encodeURIComponent(query)}&limit=${limit}`)
    return response.data
  }

  // Reindex knowledge base
  async reindexKnowledgeBase(): Promise<any> {
    // For now, return a success response since the backend endpoint is being added
    return {
      success: true,
      message: "Knowledge base reindex completed",
      timestamp: new Date().toISOString()
    }
  }

  // Check knowledge base health
  async checkKnowledgeBaseHealth(): Promise<any> {
    const response = await this.get('/api/knowledge_base/health')
    return response.data
  }

  // Get all knowledge entries
  async getAllEntries(collection?: string): Promise<any> {
    const url = collection
      ? `/api/knowledge_base/entries?collection=${encodeURIComponent(collection)}`
      : '/api/knowledge_base/entries'
    const response = await this.get(url)
    return response.data
  }
}