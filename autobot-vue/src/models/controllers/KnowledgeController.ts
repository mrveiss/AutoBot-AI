import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useAppStore } from '@/stores/useAppStore'
import { knowledgeRepository } from '@/models/repositories'
import type { KnowledgeDocument, SearchResult, SearchFilters } from '@/stores/useKnowledgeStore'
import { generateCategoryId, generateDocumentId } from '@/utils/ChatIdGenerator'

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

      const results = await knowledgeRepository.searchKnowledge({
        query: searchQuery,
        limit: 20,
        filters: {
          categories: this.knowledgeStore.filters.categories,
          tags: this.knowledgeStore.filters.tags,
          types: this.knowledgeStore.filters.types
        }
      })

      this.knowledgeStore.updateSearchResults(results)

      // Update search suggestions based on results
      if (results.length > 0) {
        const suggestions = results.slice(0, 5).map(result => 
          this.extractKeywords(result.document.title || result.document.content)
        ).flat().slice(0, 8)
        
        this.knowledgeStore.setSearchSuggestions([...new Set(suggestions)])
      }

    } catch (error: any) {
      this.appStore.setGlobalError(`Search failed: ${error.message}`)
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
      console.warn('Failed to get search suggestions:', error)
    }
  }

  clearSearch(): void {
    this.knowledgeStore.clearSearch()
  }

  // Document operations
  async addTextDocument(content: string, title?: string, category?: string, tags?: string[]): Promise<string> {
    try {
      this.knowledgeStore.setLoading(true)

      const result = await knowledgeRepository.addTextToKnowledge({
        text: content,
        title: title || this.generateTitleFromContent(content),
        source: 'Manual Entry',
        category: category || 'General',
        tags: tags || []
      })

      // Add to local store
      const documentId = this.knowledgeStore.addDocument({
        title: title || this.generateTitleFromContent(content),
        content,
        source: 'Manual Entry',
        type: 'document',
        category: category || 'General',
        tags: tags || []
      })

      await this.refreshStats()
      return documentId

    } catch (error: any) {
      this.appStore.setGlobalError(`Failed to add document: ${error.message}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  async addUrlDocument(url: string, category?: string, tags?: string[]): Promise<string> {
    try {
      this.knowledgeStore.setLoading(true)

      const result = await knowledgeRepository.addUrlToKnowledge({
        url,
        method: 'fetch',
        category: category || 'Web Content',
        tags: tags || []
      })

      // Add to local store (backend response should include processed content)
      const documentId = this.knowledgeStore.addDocument({
        title: result.title || url,
        content: result.content || '',
        source: url,
        type: 'webpage',
        category: category || 'Web Content',
        tags: tags || []
      })

      await this.refreshStats()
      return documentId

    } catch (error: any) {
      this.appStore.setGlobalError(`Failed to add URL: ${error.message}`)
      throw error
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  async addFileDocument(file: File, category?: string, tags?: string[]): Promise<string> {
    try {
      this.knowledgeStore.setLoading(true)

      const result = await knowledgeRepository.addFileToKnowledge(file, {
        category: category || 'Uploads',
        tags: tags || []
      })

      // Add to local store
      const documentId = this.knowledgeStore.addDocument({
        title: file.name,
        content: result.content || '',
        source: file.name,
        type: 'upload',
        category: category || 'Uploads',
        tags: tags || [],
        metadata: {
          fileSize: file.size,
          wordCount: result.word_count
        }
      })

      await this.refreshStats()
      return documentId

    } catch (error: any) {
      this.appStore.setGlobalError(`Failed to upload file: ${error.message}`)
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

    } catch (error: any) {
      this.appStore.setGlobalError(`Failed to update document: ${error.message}`)
      throw error
    }
  }

  async deleteDocument(documentId: string): Promise<void> {
    try {
      this.knowledgeStore.setLoading(true)

      await knowledgeRepository.deleteDocument(documentId)
      this.knowledgeStore.deleteDocument(documentId)
      
      await this.refreshStats()

    } catch (error: any) {
      this.appStore.setGlobalError(`Failed to delete document: ${error.message}`)
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

    } catch (error: any) {
      this.appStore.setGlobalError(`Failed to delete documents: ${error.message}`)
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
      const categories = stats.categories.map(cat => ({
        id: generateCategoryId(),
        name: cat.name,
        description: `Documents related to ${cat.name}`,
        documentCount: cat.document_count,
        updatedAt: new Date()
      }))

      this.knowledgeStore.categories = categories

    } catch (error: any) {
      console.warn('Failed to load categories:', error)
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
      stats.categories.forEach(catStat => {
        const category = this.knowledgeStore.categories.find(c => c.name === catStat.name)
        if (category) {
          category.documentCount = catStat.document_count
        }
      })

    } catch (error) {
      console.warn('Failed to refresh stats:', error)
    }
  }

  // Load all documents
  async loadAllDocuments(): Promise<void> {
    try {
      this.knowledgeStore.setLoading(true)
      
      const response = await knowledgeRepository.getAllEntries()
      console.log('Knowledge entries response:', response)
      
      if (response.success && response.entries) {
        // Clear existing documents
        this.knowledgeStore.documents = []
        
        // Convert backend entries to frontend document format
        const documents = response.entries.map((entry: any) => {
          const metadata = entry.metadata || {}
          return {
            id: entry.id || entry.fact_id || generateDocumentId(),
            title: metadata.title || entry.fact || 'Untitled',
            content: entry.fact || entry.content || '',
            source: metadata.source || metadata.url || 'Unknown',
            type: this.determineDocumentType(metadata),
            tags: metadata.tags || [],
            category: metadata.category || 'General',
            createdAt: metadata.created_at ? new Date(metadata.created_at) : new Date(entry.created_at || Date.now()),
            updatedAt: metadata.updated_at ? new Date(metadata.updated_at) : new Date(entry.updated_at || Date.now()),
            metadata: {
              wordCount: metadata.word_count,
              fileSize: metadata.file_size,
              language: metadata.language,
              author: metadata.author
            }
          }
        })
        
        // Add documents to store
        this.knowledgeStore.documents = documents
        
        // Update categories based on documents
        await this.refreshStats()
      }
      
    } catch (error: any) {
      console.error('Failed to load documents:', error)
      this.appStore.setGlobalError(`Failed to load documents: ${error.message}`)
    } finally {
      this.knowledgeStore.setLoading(false)
    }
  }

  // Helper to determine document type from metadata
  private determineDocumentType(metadata: any): 'document' | 'webpage' | 'api' | 'upload' {
    if (metadata.content_type === 'url' || metadata.type === 'url_reference') {
      return 'webpage'
    }
    if (metadata.filename || metadata.content_type?.includes('multipart')) {
      return 'upload'
    }
    if (metadata.source?.toLowerCase().includes('api')) {
      return 'api'
    }
    return 'document'
  }

  async getDetailedStats(): Promise<any> {
    try {
      return await knowledgeRepository.getDetailedKnowledgeStats()
    } catch (error: any) {
      this.appStore.setGlobalError(`Failed to get statistics: ${error.message}`)
      throw error
    }
  }

  async exportKnowledgeBase(): Promise<Blob> {
    try {
      this.appStore.setLoading(true, 'Exporting knowledge base...')
      return await knowledgeRepository.exportKnowledge()
    } catch (error: any) {
      this.appStore.setGlobalError(`Export failed: ${error.message}`)
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

    } catch (error: any) {
      this.appStore.setGlobalError(`Cleanup failed: ${error.message}`)
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

    } catch (error: any) {
      this.appStore.setGlobalError(`Reindexing failed: ${error.message}`)
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
    const stopWords = ['the', 'and', 'but', 'for', 'with', 'from', 'this', 'that', 'will', 'have', 'been', 'are']
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

      const results = await knowledgeRepository.searchKnowledge({
        query: params.query,
        limit: 50,
        filters: {
          categories: params.categories,
          tags: params.tags,
          types: params.types
        }
      })

      // Filter by similarity threshold if provided
      const filteredResults = params.similarityThreshold 
        ? results.filter(result => result.score >= params.similarityThreshold!)
        : results

      this.knowledgeStore.updateSearchResults(filteredResults)

    } catch (error: any) {
      this.appStore.setGlobalError(`Advanced search failed: ${error.message}`)
      throw error
    } finally {
      this.knowledgeStore.setSearching(false)
    }
  }

  // Get similar documents
  async getSimilarDocuments(documentId: string): Promise<SearchResult[]> {
    try {
      return await knowledgeRepository.getSimilarDocuments(documentId, 5)
    } catch (error: any) {
      console.warn('Failed to get similar documents:', error)
      return []
    }
  }
}