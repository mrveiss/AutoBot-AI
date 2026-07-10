// Copyright (c) 2026 mrveiss
/**
 * useKnowledgeSearch — search state + execution for the knowledge browser.
 * Extracted from KnowledgeSearch.vue during the /knowledge/browser
 * consolidation. The category scope is injected (driven by the browser's
 * selected tree category) rather than owned here.
 */
import { ref, type Ref } from 'vue'
import { knowledgeRepository, type RagSearchResponse } from '@/models/repositories'
import type { SearchResult } from '@/stores/useKnowledgeStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeSearch')

interface AccessLevelDoc {
  access_level?: string
  metadata?: { access_level?: string }
}

export function useKnowledgeSearch(selectedCategory: Ref<string | null>) {
  const searchQuery = ref('')
  const searchResults = ref<SearchResult[]>([])
  const ragResponse = ref<RagSearchResponse | null>(null)
  const ragError = ref<string | null>(null)
  const isSearching = ref(false)
  const searchPerformed = ref(false)
  const lastSearchQuery = ref('')
  const useRagSearch = ref(false)
  const selectedAccessLevel = ref<string>('')
  const ragOptions = ref({ reformulateQuery: true, enableReranking: true, limit: 10 })

  const buildCategoryFilter = () =>
    selectedCategory.value ? { categories: [selectedCategory.value] } : undefined

  const matchesAccessLevel = (r: SearchResult) => {
    const doc = r.document as AccessLevelDoc | undefined
    return doc?.access_level === selectedAccessLevel.value ||
      doc?.metadata?.access_level === selectedAccessLevel.value
  }

  const handleSearch = async () => {
    if (!searchQuery.value.trim()) return

    isSearching.value = true
    ragError.value = null
    ragResponse.value = null

    // Build filters including category
    const categoryFilter = buildCategoryFilter()

    try {
      if (useRagSearch.value) {
        // Use RAG-enhanced search
        try {
          ragResponse.value = await knowledgeRepository.ragSearch({
            query: searchQuery.value,
            limit: ragOptions.value.limit,
            reformulate_query: ragOptions.value.reformulateQuery
          })

          if (ragResponse.value.results) {
            // Filter results by category client-side for RAG (backend doesn't support category filter)
            let results = ragResponse.value.results
            if (selectedCategory.value) {
              results = results.filter(r => {
                const docCategory = r.document?.category
                // Safe metadata category extraction with runtime validation
                let metaCategory: unknown = undefined
                const metadata = r.document?.metadata
                if (metadata && typeof metadata === 'object' && 'category' in metadata) {
                  metaCategory = (metadata as { category?: unknown }).category
                }
                return docCategory === selectedCategory.value ||
                  (typeof metaCategory === 'string' && metaCategory === selectedCategory.value)
              })
            }
            // Issue #685: Filter by access level client-side
            if (selectedAccessLevel.value) {
              results = results.filter(matchesAccessLevel)
            }
            searchResults.value = results
          }
        } catch (ragErr: unknown) {
          const errorMessage = ragErr instanceof Error ? ragErr.message : 'RAG functionality is currently unavailable'
          ragError.value = errorMessage

          // Fallback to traditional search with reranking if enabled
          const results = await knowledgeRepository.searchKnowledge({
            query: searchQuery.value,
            limit: ragOptions.value.limit,
            use_rag: false,
            enable_reranking: ragOptions.value.enableReranking,
            filters: categoryFilter
          })
          searchResults.value = results
        }
      } else {
        // Use traditional search (without reranking in non-RAG mode)
        let results = await knowledgeRepository.searchKnowledge({
          query: searchQuery.value,
          limit: 20,
          use_rag: false,
          enable_reranking: false,
          filters: categoryFilter
        })
        // Issue #685: Filter by access level client-side
        if (selectedAccessLevel.value) {
          results = results.filter(matchesAccessLevel)
        }
        searchResults.value = results
      }
    } catch (error) {
      logger.error('Knowledge search failed:', error)
      searchResults.value = []
      if (useRagSearch.value) {
        ragError.value = 'Search failed - backend may be unavailable'
      }
    } finally {
      isSearching.value = false
      searchPerformed.value = true
      lastSearchQuery.value = searchQuery.value
    }
  }

  const toggleAccessLevel = async (level: string) => {
    selectedAccessLevel.value = selectedAccessLevel.value === level ? '' : level
    if (searchPerformed.value && searchQuery.value.trim()) await handleSearch()
  }

  const clearAccessLevelFilter = async () => {
    selectedAccessLevel.value = ''
    if (searchPerformed.value && searchQuery.value.trim()) await handleSearch()
  }

  const clearResults = () => {
    searchResults.value = []
    searchPerformed.value = false
    ragResponse.value = null
    ragError.value = null
  }

  return {
    searchQuery, searchResults, ragResponse, ragError, isSearching,
    searchPerformed, lastSearchQuery, useRagSearch, selectedAccessLevel,
    ragOptions, handleSearch, clearResults, clearAccessLevelFilter,
    toggleAccessLevel,
  }
}
