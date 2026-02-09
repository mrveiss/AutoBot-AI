/**
 * KnowledgeController - Manages knowledge base operations
 *
 * Provides a unified interface for knowledge base operations,
 * bridging the Pinia store with the KnowledgeRepository API layer.
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useAppStore } from '@/stores/useAppStore'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'
import type {
  SearchKnowledgeRequest,
  AddTextRequest,
  AddUrlRequest,
  AddFileOptions
} from '@/models/repositories/KnowledgeRepository'
import type { KnowledgeDocument, SearchResult, SearchFilters } from '@/stores/useKnowledgeStore'
import { generateCategoryId, generateDocumentId } from '@/utils/ChatIdGenerator'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for KnowledgeController
const logger = createLogger('KnowledgeController')

export class KnowledgeController {
  // FIXED: Lazy initialization - stores only created when accessed, not at module load
  // This prevents "composables can only be called in setup()" error
  private _knowledgeStore?: ReturnType<typeof useKnowledgeStore>
  private _appStore?: ReturnType<typeof useAppStore>

  private get knowledgeStore() {
    if (!this._knowledgeStore) {
      this._knowledgeStore = useKnowledgeStore()
    }
    return this._knowledgeStore
  }

  private get appStore() {
    if (!this._appStore) {
      this._appStore = useAppStore()
    }
    return this._appStore
  }

  // Search operations
  async performSearch(query?: string): Promise<void> {
    const searchQuery = query || this.knowledgeStore.searchQuery
    if (!searchQuery.trim()) return

    try {
      this.knowledgeStore.setSearching(true)
      this.knowledgeStore.updateSearchQuery(searchQuery)

      // Build search request with proper typing
      const searchRequest: SearchKnowledgeRequest = {
        query: searchQuery,
        limit: 20
      }

      const results = await knowledgeRepository.searchKnowledge(searchRequest)
      this.knowledgeStore.updateSearchResults(results)

      // Update search suggestions based on results
      if (results.length > 0) {
        const suggestions = results.slice(0, 5).map(result =>
          this.extractKeywords(result.document.title || result.document.content)
        ).flat().slice(0, 8)

        this.knowledgeStore.setSearchSuggestions([...new Set(suggestions)])
      }

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Search failed: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setSearching(false)
    }
  }

  async getSearchSuggestions(query: string): Promise<void> {
    try {
      const suggestions = await knowledgeRepository.getSearchSuggestions(query, 8)
      this.knowledgeStore.setSearchSuggestions(suggestions)
    } catch (error) {
      logger.warn('Failed to get search suggestions:', error)
    }
  }

  clearSearch(): void {
    this.knowledgeStore.clearSearch()
  }

  // Document operations
  async addTextDocument(content: string, title?: string, category?: string, tags?: string[]): Promise<string> {
    try {
      this.knowledgeStore.setLoading(true)

      // Build request with proper typing
      const request: AddTextRequest = {
        content,
        title: title || this.generateTitleFromContent(content),
        category: category || 'General',
        tags: tags || []
      }

      await knowledgeRepository.addTextToKnowledge(request)

      // Add to local store
      const documentId = this.knowledgeStore.addDocument({
        title: request.title || this.generateTitleFromContent(content),
        content,
        source: 'Manual Entry',
        type: 'document',
        category: request.category || 'General',
        tags: request.tags || []
      })

      await this.refreshStats()
      return documentId

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to add document: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  async addUrlDocument(url: string, category?: string, tags?: string[]): Promise<string> {
    try {
      this.knowledgeStore.setLoading(true)

      // Build request with proper typing
      const request: AddUrlRequest = {
        url,
        category: category || 'Web Content',
        tags: tags || []
      }

      const result = await knowledgeRepository.addUrlToKnowledge(request)

      // Add to local store (backend response should include processed content)
      const documentId = this.knowledgeStore.addDocument({
        title: result.title || url,
        content: result.content || '',
        source: url,
        type: 'webpage',
        category: request.category || 'Web Content',
        tags: request.tags || []
      })

      await this.refreshStats()
      return documentId

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to add URL: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  async addFileDocument(file: File, category?: string, tags?: string[]): Promise<string> {
    try {
      this.knowledgeStore.setLoading(true)

      // Build options with proper typing
      const options: AddFileOptions = {
        category: category || 'Uploads',
        tags: tags || []
      }

      const result = await knowledgeRepository.addFileToKnowledge(file, options)

      // Add to local store
      const documentId = this.knowledgeStore.addDocument({
        title: file.name,
        content: result.content || '',
        source: file.name,
        type: 'upload',
        category: options.category || 'Uploads',
        tags: options.tags || [],
        metadata: {
          fileSize: file.size,
          wordCount: result.word_count
        }
      })

      await this.refreshStats()
      return documentId

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to upload file: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  async updateDocument(documentId: string, updates: Partial<KnowledgeDocument>): Promise<void> {
    try {
      await knowledgeRepository.updateDocument(documentId, updates)
      this.knowledgeStore.updateDocument(documentId, updates)

      if (updates.category) {
        await this.refreshStats()
      }

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to update document: ${errorMessage}`)
      throw error
    }
  }

  async deleteDocument(documentId: string): Promise<void> {
    try {
      this.knowledgeStore.setLoading(true)

      await knowledgeRepository.deleteDocument(documentId)
      this.knowledgeStore.deleteDocument(documentId)

      await this.refreshStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to delete document: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  async bulkDeleteDocuments(documentIds: string[]): Promise<void> {
    try {
      this.knowledgeStore.setLoading(true)

      await knowledgeRepository.bulkDeleteDocuments(documentIds)
      this.knowledgeStore.bulkDeleteDocuments(documentIds)

      await this.refreshStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to delete documents: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  // Issue #747: Bulk update operations
  async bulkUpdateCategory(documentIds: string[], category: string): Promise<void> {
    try {
      this.knowledgeStore.setLoading(true)

      // Issue #821: Use allSettled so one failure doesn't abort remaining updates
      const results = await Promise.allSettled(
        documentIds.map(id => knowledgeRepository.updateDocument(id, { category }))
      )

      // Update local store only for successful updates
      const failed: string[] = []
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          this.knowledgeStore.updateDocument(documentIds[index], { category })
        } else {
          failed.push(documentIds[index])
        }
      })

      if (failed.length > 0) {
        logger.warn(`${failed.length}/${documentIds.length} category updates failed`)
        this.appStore.setGlobalError(`${failed.length} of ${documentIds.length} updates failed`)
      }

      await this.refreshStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to update categories: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  async bulkAddTags(documentIds: string[], tagsToAdd: string[]): Promise<void> {
    try {
      this.knowledgeStore.setLoading(true)

      // Get current documents and add new tags
      const updates = documentIds.map(id => {
        const doc = this.knowledgeStore.documents.find(d => d.id === id)
        if (!doc) return null

        const currentTags = doc.tags || []
        const newTags = [...new Set([...currentTags, ...tagsToAdd])]

        return { id, tags: newTags }
      }).filter(Boolean) as Array<{ id: string; tags: string[] }>

      // Update each document
      await Promise.all(
        updates.map(({ id, tags }) => knowledgeRepository.updateDocument(id, { tags }))
      )

      // Update local store
      updates.forEach(({ id, tags }) => {
        this.knowledgeStore.updateDocument(id, { tags })
      })

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to add tags: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  async bulkRemoveTags(documentIds: string[], tagsToRemove: string[]): Promise<void> {
    try {
      this.knowledgeStore.setLoading(true)

      // Get current documents and remove specified tags
      const updates = documentIds.map(id => {
        const doc = this.knowledgeStore.documents.find(d => d.id === id)
        if (!doc) return null

        const currentTags = doc.tags || []
        const newTags = currentTags.filter(tag => !tagsToRemove.includes(tag))

        return { id, tags: newTags }
      }).filter(Boolean) as Array<{ id: string; tags: string[] }>

      // Update each document
      await Promise.all(
        updates.map(({ id, tags }) => knowledgeRepository.updateDocument(id, { tags }))
      )

      // Update local store
      updates.forEach(({ id, tags }) => {
        this.knowledgeStore.updateDocument(id, { tags })
      })

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to remove tags: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  // Category operations
  async loadCategories(): Promise<void> {
    try {
      const stats = await knowledgeRepository.getKnowledgeStats()

      // Update categories in store
      const categories = stats.categories.map((cat: { name: string; document_count: number }) => ({
        id: generateCategoryId(),
        name: cat.name,
        description: `Documents related to ${cat.name}`,
        documentCount: cat.document_count,
        updatedAt: new Date()
      }))

      this.knowledgeStore.categories = categories

    } catch (error: unknown) {
      logger.warn('Failed to load categories:', error)
    }
  }

  addCategory(name: string, description?: string): void {
    this.knowledgeStore.addCategory({
      name,
      description: description || `Documents related to ${name}`
    })
  }

  // Filter operations
  updateFilters(filters: Partial<SearchFilters>): void {
    this.knowledgeStore.updateFilters(filters)
  }

  clearFilters(): void {
    this.knowledgeStore.clearFilters()
  }

  toggleAdvancedSearch(): void {
    this.knowledgeStore.toggleAdvancedSearch()
  }

  // Tab operations
  setActiveTab(tab: 'search' | 'manage' | 'upload' | 'categories'): void {
    this.knowledgeStore.setActiveTab(tab)
  }

  // Statistics and maintenance
  async refreshStats(): Promise<void> {
    try {
      const stats = await knowledgeRepository.getKnowledgeStats()

      // Update local categories with counts
      stats.categories.forEach((catStat: { name: string; document_count: number }) => {
        const category = this.knowledgeStore.categories.find(c => c.name === catStat.name)
        if (category) {
          category.documentCount = catStat.document_count
        }
      })

    } catch (error) {
      logger.warn('Failed to refresh stats:', error)
    }
  }

  // Load all documents
  async loadAllDocuments(): Promise<void> {
    try {
      this.knowledgeStore.setLoading(true)

      const response = await knowledgeRepository.getAllEntries()
      logger.debug('Knowledge entries response:', response)

      if (response.success && response.entries) {
        // Clear existing documents
        this.knowledgeStore.documents = []

        // Convert backend entries to frontend document format
        const documents = response.entries.map((entry) => {
          const metadata = entry.metadata || {}
          return {
            id: entry.id || entry.fact_id || generateDocumentId(),
            title: (metadata.title as string) || entry.fact || 'Untitled',
            content: entry.fact || entry.content || '',
            source: (metadata.source as string) || (metadata.url as string) || 'Unknown',
            type: this.determineDocumentType(metadata),
            tags: (metadata.tags as string[]) || [],
            category: (metadata.category as string) || 'General',
            createdAt: metadata.created_at ? new Date(metadata.created_at as string) : new Date(entry.created_at || Date.now()),
            updatedAt: metadata.updated_at ? new Date(metadata.updated_at as string) : new Date(entry.updated_at || Date.now()),
            metadata: {
              wordCount: metadata.word_count as number | undefined,
              fileSize: metadata.file_size as number | undefined,
              language: metadata.language as string | undefined,
              author: metadata.author as string | undefined
            }
          }
        })

        // Add documents to store
        this.knowledgeStore.documents = documents

        // Update categories based on documents
        await this.refreshStats()
      }

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      logger.error('Failed to load documents:', error)
      this.appStore.setGlobalError(`Failed to load documents: ${errorMessage}`)
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  // Helper to determine document type from metadata
  private determineDocumentType(metadata: Record<string, unknown>): 'document' | 'webpage' | 'api' | 'upload' {
    if (metadata.content_type === 'url' || metadata.type === 'url_reference') {
      return 'webpage'
    }
    if (metadata.filename || (typeof metadata.content_type === 'string' && metadata.content_type.includes('multipart'))) {
      return 'upload'
    }
    if (typeof metadata.source === 'string' && metadata.source.toLowerCase().includes('api')) {
      return 'api'
    }
    return 'document'
  }

  async getDetailedStats(): Promise<unknown> {
    try {
      return await knowledgeRepository.getDetailedKnowledgeStats()
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Failed to get statistics: ${errorMessage}`)
      throw error
    }
  }

  async exportKnowledgeBase(): Promise<Blob> {
    try {
      this.appStore.setLoading(true, 'Exporting knowledge base...')
      return await knowledgeRepository.exportKnowledge()
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Export failed: ${errorMessage}`)
      throw error
    } finally {
      this.appStore.setLoading(false)
    }
  }

  async cleanupKnowledgeBase(): Promise<void> {
    try {
      this.appStore.setLoading(true, 'Cleaning up knowledge base...')

      await knowledgeRepository.cleanupKnowledge()
      await this.refreshStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Cleanup failed: ${errorMessage}`)
      throw error
    } finally {
      this.appStore.setLoading(false)
    }
  }

  async reindexKnowledgeBase(): Promise<void> {
    try {
      this.appStore.setLoading(true, 'Reindexing knowledge base...')

      await knowledgeRepository.reindexKnowledgeBase()
      await this.refreshStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Reindexing failed: ${errorMessage}`)
      throw error
    } finally {
      this.appStore.setLoading(false)
    }
  }

  // Helper methods
  private generateTitleFromContent(content: string): string {
    // Extract first sentence or first 50 characters
    const firstSentence = content.split(/[.!?]/)[0]
    if (firstSentence.length > 3 && firstSentence.length <= 50) {
      return firstSentence.trim()
    }

    return content.substring(0, 50).trim() + (content.length > 50 ? '...' : '')
  }

  private extractKeywords(text: string): string[] {
    // Simple keyword extraction (could be enhanced with NLP)
    const words = text.toLowerCase()
      .replace(/[^\w\s]/g, ' ')
      .split(/\s+/)
      .filter(word => word.length > 3)
      .filter(word => !this.isStopWord(word))

    // Return most frequent words
    const wordCount = new Map<string, number>()
    words.forEach(word => {
      wordCount.set(word, (wordCount.get(word) || 0) + 1)
    })

    return Array.from(wordCount.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([word]) => word)
  }

  private isStopWord(word: string): boolean {
    // Issue #821: Expanded stop word list to improve keyword quality
    const stopWords = [
      'the', 'and', 'but', 'for', 'with', 'from', 'this', 'that', 'will', 'have', 'been', 'are',
      'was', 'were', 'has', 'had', 'does', 'did', 'can', 'could', 'would', 'should', 'shall',
      'not', 'than', 'then', 'when', 'where', 'which', 'what', 'who', 'whom', 'how', 'why',
      'into', 'about', 'over', 'after', 'before', 'between', 'under', 'also', 'only', 'very',
      'just', 'being', 'more', 'most', 'some', 'such', 'each', 'other', 'their', 'there',
      'here', 'they', 'them', 'these', 'those', 'your', 'your', 'make', 'like', 'many'
    ]
    return stopWords.includes(word)
  }

  // Validation
  validateDocument(document: Partial<KnowledgeDocument>): { valid: boolean; errors: string[] } {
    const errors: string[] = []

    if (!document.content?.trim()) {
      errors.push('Content is required')
    }

    if (document.content && document.content.length < 10) {
      errors.push('Content must be at least 10 characters')
    }

    if (document.title && document.title.length > 200) {
      errors.push('Title must be less than 200 characters')
    }

    if (document.tags && document.tags.length > 20) {
      errors.push('Maximum 20 tags allowed')
    }

    return {
      valid: errors.length === 0,
      errors
    }
  }

  // Advanced search with suggestions
  async performAdvancedSearch(params: {
    query: string
    categories?: string[]
    tags?: string[]
    types?: string[]
    similarityThreshold?: number
  }): Promise<void> {
    try {
      this.knowledgeStore.setSearching(true)

      const searchRequest: SearchKnowledgeRequest = {
        query: params.query,
        limit: 50,
        filters: {
          categories: params.categories,
          tags: params.tags,
          types: params.types
        }
      }

      const results = await knowledgeRepository.searchKnowledge(searchRequest)

      // Filter by similarity threshold if provided
      const filteredResults = params.similarityThreshold
        ? results.filter(result => result.score >= params.similarityThreshold!)
        : results

      this.knowledgeStore.updateSearchResults(filteredResults)

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      this.appStore.setGlobalError(`Advanced search failed: ${errorMessage}`)
      throw error
    } finally {
      this.knowledgeStore.setSearching(false)
    }
  }

  // Get similar documents
  async getSimilarDocuments(documentId: string): Promise<SearchResult[]> {
    try {
      return await knowledgeRepository.getSimilarDocuments(documentId, 5)
    } catch (error: unknown) {
      logger.warn('Failed to get similar documents:', error)
      return []
    }
  }
}
