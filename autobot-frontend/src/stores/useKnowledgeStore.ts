import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import ApiClient from '@/utils/ApiClient'
import type {
  KnowledgeStats,
  VerificationConfig,
  PendingSource
} from '@/types/knowledgeBase'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeStore')

export interface KnowledgeDocument {
  id: string
  title: string
  content: string
  source: string
  type: 'document' | 'webpage' | 'api' | 'upload'
  tags: string[]
  category: string
  createdAt: Date
  updatedAt: Date
  metadata?: {
    wordCount?: number
    fileSize?: number
    language?: string
    author?: string
  }
}

export interface KnowledgeCategory {
  id: string
  name: string
  description: string
  documentCount: number
  color?: string
  updatedAt: Date
}

export interface SearchResult {
  document: KnowledgeDocument
  score: number
  highlights: string[]
  rerank_score?: number  // Neural reranking score (when enable_reranking=true)
}

export interface RagSearchResult {
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
  status: string
  message?: string
}

// KnowledgeStats imported from @/types/knowledgeBase (consolidated type definition)

export interface SearchFilters {
  categories: string[]
  tags: string[]
  types: string[]
  dateRange?: {
    start: Date
    end: Date
  }
}

// New interfaces for Issue #747

export interface SystemDoc {
  id: string
  title: string
  path: string
  content: string
  type: string
  collection: string
  updated_at?: string
  metadata?: Record<string, unknown>
}

export interface Prompt {
  id: string
  name: string
  type: 'system' | 'agent' | 'template'
  path: string
  content: string
  full_content_available: boolean
}

export interface Category {
  id: string
  name: string
  description?: string
  icon?: string
  color?: string
  parent_id?: string | null
  fact_count?: number
  children?: Category[]
}

export const useKnowledgeStore = defineStore('knowledge', () => {
  // State
  const documents = ref<KnowledgeDocument[]>([])
  const categories = ref<KnowledgeCategory[]>([])
  const searchQuery = ref('')
  const searchResults = ref<SearchResult[]>([])
  const ragSearchResult = ref<RagSearchResult | null>(null)
  const selectedDocument = ref<KnowledgeDocument | null>(null)
  const activeTab = ref<'search' | 'manage' | 'upload' | 'categories' | 'entries' | 'stats' | 'advanced'>('search')
  const isLoading = ref(false)
  const filters = ref<SearchFilters>({
    categories: [],
    tags: [],
    types: []
  })

  // Stats state
  const stats = ref<KnowledgeStats>({
    total_documents: 0,
    total_chunks: 0,
    total_facts: 0,
    total_vectors: 0,
    categories: [],
    db_size: 0,
    status: 'offline',
    last_updated: null,
    redis_db: null,
    index_name: null,
    initialized: false,
    rag_available: false
  })

  // Search and UI state
  const showAdvancedSearch = ref(false)
  const searchSuggestions = ref<string[]>([])
  const showSuggestions = ref(false)
  const searching = ref(false)
  const useRagSearch = ref(false)
  const ragOptions = ref({
    reformulateQuery: true,
    limit: 10,
    top_k: 10
  })

  // RAG-specific state
  const ragAvailable = ref(true)
  const ragError = ref<string | null>(null)
  const lastRagQuery = ref('')

  // System Docs state (Issue #747)
  const systemDocs = ref<SystemDoc[]>([])
  const systemDocsLoading = ref(false)
  const selectedDocumentId = ref<string | null>(null)

  // Prompts state (Issue #747)
  const prompts = ref<Prompt[]>([])
  const promptsLoading = ref(false)
  const selectedPromptId = ref<string | null>(null)

  // Category edit modal state (Issue #747)
  const categoryEditModal = ref<{
    open: boolean
    category: Category | null
    mode: 'edit' | 'delete'
  }>({
    open: false,
    category: null,
    mode: 'edit'
  })

  // Source preview panel state (Issue #747)
  const sourcePanel = ref<{
    open: boolean
    document: SystemDoc | null
  }>({
    open: false,
    document: null
  })

  // Verification state (Issue #1253)
  const pendingVerifications = ref<PendingSource[]>([])
  const pendingVerificationsTotal = ref(0)
  const verificationConfig = ref<VerificationConfig>({
    mode: 'autonomous',
    quality_threshold: 0.7
  })
  const verificationLoading = ref(false)

  // Computed
  const documentCount = computed(() => documents.value.length)

  const categoryCount = computed(() => categories.value.length)

  const allTags = computed(() => {
    const tagSet = new Set<string>()
    documents.value.forEach(doc => {
      doc.tags.forEach(tag => tagSet.add(tag))
    })
    return Array.from(tagSet).sort()
  })

  const documentsByCategory = computed(() => {
    const grouped = new Map<string, KnowledgeDocument[]>()
    documents.value.forEach(doc => {
      if (!grouped.has(doc.category)) {
        grouped.set(doc.category, [])
      }
      grouped.get(doc.category)!.push(doc)
    })
    return grouped
  })

  const hasSearchResults = computed(() => searchResults.value.length > 0)

  const hasRagResults = computed(() => ragSearchResult.value !== null)

  const filteredDocuments = computed(() => {
    let filtered = documents.value

    if (filters.value.categories.length > 0) {
      filtered = filtered.filter(doc => filters.value.categories.includes(doc.category))
    }

    if (filters.value.tags.length > 0) {
      filtered = filtered.filter(doc =>
        doc.tags.some(tag => filters.value.tags.includes(tag))
      )
    }

    if (filters.value.types.length > 0) {
      filtered = filtered.filter(doc => filters.value.types.includes(doc.type))
    }

    if (filters.value.dateRange) {
      filtered = filtered.filter(doc =>
        doc.createdAt >= filters.value.dateRange!.start &&
        doc.createdAt <= filters.value.dateRange!.end
      )
    }

    return filtered
  })

  // Actions
  function setActiveTab(tab: 'search' | 'manage' | 'upload' | 'categories' | 'entries' | 'stats' | 'advanced') {
    activeTab.value = tab
  }

  function updateSearchQuery(query: string) {
    searchQuery.value = query
  }

  function toggleAdvancedSearch() {
    showAdvancedSearch.value = !showAdvancedSearch.value
  }

  function clearSearch() {
    searchQuery.value = ''
    searchResults.value = []
    ragSearchResult.value = null
    ragError.value = null
    showSuggestions.value = false
  }

  function setRagMode(enabled: boolean) {
    useRagSearch.value = enabled
    if (!enabled) {
      ragSearchResult.value = null
      ragError.value = null
    }
  }

  function updateRagOptions(options: Partial<typeof ragOptions.value>) {
    ragOptions.value = { ...ragOptions.value, ...options }
  }

  function setRagAvailable(available: boolean) {
    ragAvailable.value = available
  }

  function setRagError(error: string | null) {
    ragError.value = error
  }

  function updateRagSearchResult(result: RagSearchResult | null) {
    ragSearchResult.value = result
    if (result) {
      lastRagQuery.value = result.query
      if (result.results) {
        searchResults.value = result.results
      }
    }
  }

  // Stats actions
  async function refreshStats() {
    try {
      isLoading.value = true
      const response = await ApiClient.get('/api/knowledge_base/stats')
      stats.value = await response.json()
    } catch (error) {
      logger.error('Failed to refresh stats:', error)
      // Issue #820: Preserve previous stats on error instead of resetting to zeros.
      // Only update the status field to indicate the error state.
      stats.value = {
        ...stats.value,
        status: 'error'
      }
    } finally {
      isLoading.value = false
    }
  }

  function updateStats(newStats: Partial<KnowledgeStats>) {
    stats.value = { ...stats.value, ...newStats }
  }

  function addDocument(document: Omit<KnowledgeDocument, 'id' | 'createdAt' | 'updatedAt'>) {
    const newDocument: KnowledgeDocument = {
      id: `doc-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      createdAt: new Date(),
      updatedAt: new Date(),
      ...document
    }

    documents.value.push(newDocument)
    updateCategoryCount(document.category)

    return newDocument.id
  }

  function updateDocument(documentId: string, updates: Partial<KnowledgeDocument>) {
    const docIndex = documents.value.findIndex(doc => doc.id === documentId)
    if (docIndex !== -1) {
      const oldCategory = documents.value[docIndex].category
      documents.value[docIndex] = {
        ...documents.value[docIndex],
        ...updates,
        updatedAt: new Date()
      }

      // Update category counts if category changed
      if (updates.category && updates.category !== oldCategory) {
        updateCategoryCount(oldCategory, -1)
        updateCategoryCount(updates.category, 1)
      }
    }
  }

  function deleteDocument(documentId: string) {
    const docIndex = documents.value.findIndex(doc => doc.id === documentId)
    if (docIndex !== -1) {
      const category = documents.value[docIndex].category
      documents.value.splice(docIndex, 1)
      updateCategoryCount(category, -1)

      // Clear selection if deleted document was selected
      if (selectedDocument.value?.id === documentId) {
        selectedDocument.value = null
      }
    }
  }

  function selectDocument(document: KnowledgeDocument) {
    selectedDocument.value = document
  }

  function addCategory(category: Omit<KnowledgeCategory, 'id' | 'documentCount' | 'updatedAt'>) {
    const newCategory: KnowledgeCategory = {
      id: `cat-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      documentCount: 0,
      updatedAt: new Date(),
      ...category
    }

    categories.value.push(newCategory)
    return newCategory.id
  }

  // Legacy local category update (for KnowledgeCategory)
  function updateCategoryLocal(categoryId: string, updates: Partial<KnowledgeCategory>) {
    const catIndex = categories.value.findIndex(cat => cat.id === categoryId)
    if (catIndex !== -1) {
      categories.value[catIndex] = {
        ...categories.value[catIndex],
        ...updates,
        updatedAt: new Date()
      }
    }
  }

  // Legacy local category delete (for KnowledgeCategory)
  function deleteCategoryLocal(categoryId: string) {
    const catIndex = categories.value.findIndex(cat => cat.id === categoryId)
    if (catIndex !== -1) {
      const categoryName = categories.value[catIndex].name

      // Move documents to "Uncategorized"
      documents.value.forEach(doc => {
        if (doc.category === categoryName) {
          doc.category = 'Uncategorized'
        }
      })

      categories.value.splice(catIndex, 1)
    }
  }

  // API-based category update (Issue #747)
  async function updateCategory(id: string, data: Partial<Category>) {
    try {
      const response = await ApiClient.put(`/api/knowledge_base/categories/${id}`, data)
      const result = await response.json()
      if (result.status === 'success') {
        logger.info('Category updated successfully: %s', id)
        return result.category
      } else {
        throw new Error(result.message || 'Failed to update category')
      }
    } catch (error) {
      logger.error('Failed to update category: %s', error)
      throw error
    }
  }

  // API-based category delete (Issue #747)
  async function deleteCategory(id: string) {
    try {
      const response = await ApiClient.delete(`/api/knowledge_base/categories/${id}`)
      const result = await response.json()
      if (result.status === 'success') {
        logger.info('Category deleted successfully: %s', id)
        return result
      } else {
        throw new Error(result.message || 'Failed to delete category')
      }
    } catch (error) {
      logger.error('Failed to delete category: %s', error)
      throw error
    }
  }

  // Category edit modal actions (Issue #747)
  function openCategoryEditModal(category: Category, mode: 'edit' | 'delete') {
    categoryEditModal.value = {
      open: true,
      category,
      mode
    }
  }

  function closeCategoryEditModal() {
    categoryEditModal.value = {
      open: false,
      category: null,
      mode: 'edit'
    }
  }

  // System Docs actions (Issue #747)
  async function loadSystemDocs() {
    try {
      systemDocsLoading.value = true
      const response = await ApiClient.get(
        '/api/knowledge_base/entries?collection=autobot-documentation'
      )
      const result = await response.json()
      systemDocs.value = result.entries || result.documents || []
      logger.info('Loaded %d system docs', systemDocs.value.length)
    } catch (error) {
      logger.error('Failed to load system docs: %s', error)
      systemDocs.value = []
    } finally {
      systemDocsLoading.value = false
    }
  }

  function setSelectedDocument(id: string | null) {
    selectedDocumentId.value = id
  }

  // Prompts actions (Issue #747)
  async function loadPrompts() {
    try {
      promptsLoading.value = true
      const response = await ApiClient.get('/api/prompts')
      const result = await response.json()
      prompts.value = result.prompts || []
      logger.info('Loaded %d prompts', prompts.value.length)
    } catch (error) {
      logger.error('Failed to load prompts: %s', error)
      prompts.value = []
    } finally {
      promptsLoading.value = false
    }
  }

  async function updatePrompt(id: string, content: string) {
    try {
      const response = await ApiClient.put(`/api/prompts/${id}`, { content })
      const result = await response.json()
      // Update the prompt in local state
      const promptIndex = prompts.value.findIndex(p => p.id === id)
      if (promptIndex !== -1) {
        prompts.value[promptIndex] = {
          ...prompts.value[promptIndex],
          content: content.slice(0, 1000),
          full_content_available: content.length > 1000
        }
      }
      logger.info('Prompt updated successfully: %s', id)
      return result
    } catch (error) {
      logger.error('Failed to update prompt: %s', error)
      throw error
    }
  }

  async function revertPrompt(id: string) {
    try {
      const response = await ApiClient.post(`/api/prompts/${id}/revert`, {})
      const result = await response.json()
      // Update the prompt in local state
      const promptIndex = prompts.value.findIndex(p => p.id === id)
      if (promptIndex !== -1 && result.content) {
        prompts.value[promptIndex] = {
          ...prompts.value[promptIndex],
          content: result.content.slice(0, 1000),
          full_content_available: result.content.length > 1000
        }
      }
      logger.info('Prompt reverted successfully: %s', id)
      return result
    } catch (error) {
      logger.error('Failed to revert prompt: %s', error)
      throw error
    }
  }

  function setSelectedPrompt(id: string | null) {
    selectedPromptId.value = id
  }

  // Verification actions (Issue #1253)
  function setPendingVerifications(
    sources: PendingSource[],
    total: number
  ) {
    pendingVerifications.value = sources
    pendingVerificationsTotal.value = total
  }

  function removePendingSource(factId: string) {
    pendingVerifications.value =
      pendingVerifications.value.filter(s => s.fact_id !== factId)
    pendingVerificationsTotal.value = Math.max(
      0,
      pendingVerificationsTotal.value - 1
    )
  }

  function setVerificationConfig(config: VerificationConfig) {
    verificationConfig.value = config
  }

  function setVerificationLoading(loading: boolean) {
    verificationLoading.value = loading
  }

  // Source panel actions (Issue #747)
  function openSourcePanel(document: SystemDoc) {
    sourcePanel.value = {
      open: true,
      document
    }
  }

  function closeSourcePanel() {
    sourcePanel.value = {
      open: false,
      document: null
    }
  }

  function updateFilters(newFilters: Partial<SearchFilters>) {
    filters.value = { ...filters.value, ...newFilters }
  }

  function clearFilters() {
    filters.value = {
      categories: [],
      tags: [],
      types: []
    }
  }

  function updateSearchResults(results: SearchResult[]) {
    searchResults.value = results
  }

  function setSearchSuggestions(suggestions: string[]) {
    searchSuggestions.value = suggestions
    showSuggestions.value = suggestions.length > 0
  }

  function setLoading(loading: boolean) {
    isLoading.value = loading
  }

  function setSearching(searching_state: boolean) {
    searching.value = searching_state
  }

  // Helper function to update category document counts
  function updateCategoryCount(categoryName: string, delta = 0) {
    const category = categories.value.find(cat => cat.name === categoryName)
    if (category) {
      if (delta === 0) {
        // Recalculate from scratch
        category.documentCount = documents.value.filter(doc => doc.category === categoryName).length
      } else {
        category.documentCount += delta
      }
    }
  }

  // Batch operations
  function bulkDeleteDocuments(documentIds: string[]) {
    const categories = new Set<string>()

    documentIds.forEach(id => {
      const docIndex = documents.value.findIndex(doc => doc.id === id)
      if (docIndex !== -1) {
        categories.add(documents.value[docIndex].category)
        documents.value.splice(docIndex, 1)
      }
    })

    // Update category counts
    categories.forEach(category => updateCategoryCount(category))

    // Clear selection if any deleted document was selected
    if (selectedDocument.value && documentIds.includes(selectedDocument.value.id)) {
      selectedDocument.value = null
    }
  }

  function bulkUpdateDocuments(documentIds: string[], updates: Partial<KnowledgeDocument>) {
    documentIds.forEach(id => updateDocument(id, updates))
  }

  return {
    // State
    documents,
    categories,
    searchQuery,
    searchResults,
    ragSearchResult,
    selectedDocument,
    activeTab,
    isLoading,
    filters,
    stats,

    // Search and UI state
    showAdvancedSearch,
    searchSuggestions,
    showSuggestions,
    searching,
    useRagSearch,
    ragOptions,
    ragAvailable,
    ragError,
    lastRagQuery,

    // System Docs state (Issue #747)
    systemDocs,
    systemDocsLoading,
    selectedDocumentId,

    // Prompts state (Issue #747)
    prompts,
    promptsLoading,
    selectedPromptId,

    // Category edit modal state (Issue #747)
    categoryEditModal,

    // Source preview panel state (Issue #747)
    sourcePanel,

    // Verification state (Issue #1253)
    pendingVerifications,
    pendingVerificationsTotal,
    verificationConfig,
    verificationLoading,

    // Computed
    documentCount,
    categoryCount,
    allTags,
    documentsByCategory,
    hasSearchResults,
    hasRagResults,
    filteredDocuments,

    // Actions
    setActiveTab,
    updateSearchQuery,
    toggleAdvancedSearch,
    clearSearch,
    setRagMode,
    updateRagOptions,
    setRagAvailable,
    setRagError,
    updateRagSearchResult,
    refreshStats,
    updateStats,
    addDocument,
    updateDocument,
    deleteDocument,
    selectDocument,
    addCategory,
    updateCategoryLocal,
    deleteCategoryLocal,
    updateCategory,
    deleteCategory,
    openCategoryEditModal,
    closeCategoryEditModal,
    loadSystemDocs,
    setSelectedDocument,
    loadPrompts,
    updatePrompt,
    revertPrompt,
    setSelectedPrompt,
    openSourcePanel,
    closeSourcePanel,
    setPendingVerifications,
    removePendingSource,
    setVerificationConfig,
    setVerificationLoading,
    updateFilters,
    clearFilters,
    updateSearchResults,
    setSearchSuggestions,
    setLoading,
    setSearching,
    bulkDeleteDocuments,
    bulkUpdateDocuments
  }
})
