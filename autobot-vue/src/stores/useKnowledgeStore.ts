import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

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
}

export interface SearchFilters {
  categories: string[]
  tags: string[]
  types: string[]
  dateRange?: {
    start: Date
    end: Date
  }
}

export const useKnowledgeStore = defineStore('knowledge', () => {
  // State
  const documents = ref<KnowledgeDocument[]>([])
  const categories = ref<KnowledgeCategory[]>([])
  const searchQuery = ref('')
  const searchResults = ref<SearchResult[]>([])
  const selectedDocument = ref<KnowledgeDocument | null>(null)
  const activeTab = ref<'search' | 'manage' | 'upload' | 'categories' | 'entries'>('search')
  const isLoading = ref(false)
  const filters = ref<SearchFilters>({
    categories: [],
    tags: [],
    types: []
  })

  // Search and UI state
  const showAdvancedSearch = ref(false)
  const searchSuggestions = ref<string[]>([])
  const showSuggestions = ref(false)
  const searching = ref(false)

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
  function setActiveTab(tab: 'search' | 'manage' | 'upload' | 'categories' | 'entries') {
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
    showSuggestions.value = false
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

  function updateCategory(categoryId: string, updates: Partial<KnowledgeCategory>) {
    const catIndex = categories.value.findIndex(cat => cat.id === categoryId)
    if (catIndex !== -1) {
      categories.value[catIndex] = {
        ...categories.value[catIndex],
        ...updates,
        updatedAt: new Date()
      }
    }
  }

  function deleteCategory(categoryId: string) {
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
    selectedDocument,
    activeTab,
    isLoading,
    filters,
    showAdvancedSearch,
    searchSuggestions,
    showSuggestions,
    searching,

    // Computed
    documentCount,
    categoryCount,
    allTags,
    documentsByCategory,
    hasSearchResults,
    filteredDocuments,

    // Actions
    setActiveTab,
    updateSearchQuery,
    toggleAdvancedSearch,
    clearSearch,
    addDocument,
    updateDocument,
    deleteDocument,
    selectDocument,
    addCategory,
    updateCategory,
    deleteCategory,
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
