// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeFacts Composable
 *
 * Search (basic + advanced) and direct-fact management for the knowledge base.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 *
 * Reactive refs layer (#5195, follow-up to #5149): the composable now owns
 * loading/error state via `ref`s and exposes managed `search`/`runAdvancedSearch`/
 * `submitFact` actions. The bare imperative functions remain exported at module
 * scope so non-reactive consumers (and the `useKnowledgeBase` BC shim) keep
 * working unchanged.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import type {
  SearchResponse,
  AddFactResponse,
} from '@/types/knowledgeBase'

/**
 * Advanced search options (Issue #555).
 *
 * Uses the consolidated search endpoint with all available features:
 * - mode: 'semantic' | 'keyword' | 'hybrid' | 'auto'
 * - enable_rag: Enable RAG synthesis for responses
 * - enable_reranking: Enable cross-encoder reranking
 * - tags: Filter by tags
 * - min_score: Minimum similarity threshold
 * - category: Filter by category
 */
export interface AdvancedSearchOptions {
  query: string
  top_k?: number
  mode?: 'semantic' | 'keyword' | 'hybrid' | 'auto'
  enable_rag?: boolean
  enable_reranking?: boolean
  reformulate_query?: boolean
  tags?: string[]
  tags_match_any?: boolean
  min_score?: number
  category?: string
  offset?: number
}

export interface AddFactInput {
  content: string
  category: string
  metadata?: Record<string, unknown>
}

// ==================== Bare imperative API ====================

/**
 * Search knowledge base (basic).
 * Issue #552: Backend expects POST for search.
 */
export const searchKnowledge = (query: string): Promise<SearchResponse> =>
  apiClient.post<SearchResponse>(`${getApiBase()}/knowledge_base/search`, { query })

/**
 * Advanced search with full options (Issue #555).
 */
export const advancedSearch = (options: AdvancedSearchOptions): Promise<SearchResponse> =>
  apiClient.post<SearchResponse>(`${getApiBase()}/knowledge_base/search`, options)

/**
 * Add new fact to knowledge base.
 */
export const addFact = (fact: AddFactInput): Promise<AddFactResponse> =>
  apiClient.post<AddFactResponse>(`${getApiBase()}/knowledge_base/facts`, fact)

// ==================== Reactive composable ====================

export interface UseKnowledgeFactsReturn {
  /** Latest search result (basic or advanced). */
  searchResults: Readonly<Ref<SearchResponse | null>>
  /** Latest add-fact response. */
  lastAddedFact: Readonly<Ref<AddFactResponse | null>>
  /** True while a search (basic or advanced) is in-flight. */
  isSearching: Readonly<Ref<boolean>>
  /** True while addFact is in-flight. */
  isAdding: Readonly<Ref<boolean>>
  /** Last error raised by a managed action; cleared on the next call. */
  error: Readonly<Ref<Error | null>>
  /** Run a basic search, update `searchResults` + state refs, return the payload. */
  search: (query: string) => Promise<SearchResponse>
  /** Run an advanced search, update `searchResults` + state refs. */
  runAdvancedSearch: (options: AdvancedSearchOptions) => Promise<SearchResponse>
  /** Add a fact, update `lastAddedFact` + state refs. */
  submitFact: (fact: AddFactInput) => Promise<AddFactResponse>
  // Imperative passthroughs — BC with pre-#5195 callers
  searchKnowledge: typeof searchKnowledge
  advancedSearch: typeof advancedSearch
  addFact: typeof addFact
}

export function useKnowledgeFacts(): UseKnowledgeFactsReturn {
  const searchResults = ref<SearchResponse | null>(null)
  const lastAddedFact = ref<AddFactResponse | null>(null)
  const isSearching = ref(false)
  const isAdding = ref(false)
  const error = ref<Error | null>(null)

  const search = async (query: string): Promise<SearchResponse> => {
    isSearching.value = true
    error.value = null
    try {
      const data = await searchKnowledge(query)
      searchResults.value = data
      return data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
      throw err
    } finally {
      isSearching.value = false
    }
  }

  const runAdvancedSearch = async (
    options: AdvancedSearchOptions
  ): Promise<SearchResponse> => {
    isSearching.value = true
    error.value = null
    try {
      const data = await advancedSearch(options)
      searchResults.value = data
      return data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
      throw err
    } finally {
      isSearching.value = false
    }
  }

  const submitFact = async (fact: AddFactInput): Promise<AddFactResponse> => {
    isAdding.value = true
    error.value = null
    try {
      const data = await addFact(fact)
      lastAddedFact.value = data
      return data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
      throw err
    } finally {
      isAdding.value = false
    }
  }

  return {
    searchResults: readonly(searchResults) as Readonly<Ref<SearchResponse | null>>,
    lastAddedFact: readonly(lastAddedFact) as Readonly<Ref<AddFactResponse | null>>,
    isSearching: readonly(isSearching),
    isAdding: readonly(isAdding),
    error: readonly(error),
    search,
    runAdvancedSearch,
    submitFact,
    searchKnowledge,
    advancedSearch,
    addFact,
  }
}
