// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * useDocumentationSearch Composable
 *
 * Encapsulates all API calls for the Documentation Search Sidebar:
 * - Hybrid knowledge-base search (POST /knowledge_base/search)
 * - Paginated document browse (POST /knowledge_base/docs/browse)
 * - Category listing (GET /knowledge_base/docs/categories)
 *
 * Extracted from DocumentationSearchSidebar.vue (#6076).
 */

import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useApiClient } from '@/plugins/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useDocumentationSearch')

// ---- Shared types ----

export interface DocResult {
  id?: string
  contentHash?: string
  title: string
  content: string
  category: string
  section?: string
  filePath: string
  score?: number
}

export interface DocCategory {
  id: string
  name: string
  description?: string
  count: number
}

// ---- Internal response shapes ----

interface SearchResultItem {
  node_id?: string
  doc_id?: string
  content?: string
  score?: number
  rrf_score?: number
  metadata?: {
    content_hash?: string
    title?: string
    category?: string
    section?: string
    file_path?: string
  }
}

interface SearchResponse {
  results?: SearchResultItem[]
}

interface BrowseDocument {
  content_hash?: string
  title?: string
  category?: string
  file_path?: string
}

interface BrowseResponse {
  documents?: BrowseDocument[]
}

interface CategoriesResponse {
  categories?: DocCategory[]
}

// ---- GET /api/knowledge_base/docs/categories via useFetchEndpoint ----

const categoriesEndpoint = useFetchEndpoint<CategoriesResponse, DocCategory[]>({
  path: '/api/knowledge_base/docs/categories',
  label: 'fetchDocCategories',
  pickData: (raw) => raw.categories ?? null,
  onError: (message) => {
    logger.error('fetchCategories error:', message)
  },
})

// ---- Public composable ----

export interface UseDocumentationSearchReturn {
  searchDocs: (query: string, categories: string[], topK?: number) => Promise<DocResult[]>
  browseMore: (query: string, category: string | null, page: number, pageSize?: number) => Promise<DocResult[]>
  fetchCategories: () => Promise<DocCategory[]>
}

export function useDocumentationSearch(): UseDocumentationSearchReturn {
  const api = useApiClient()

  /**
   * Execute a hybrid knowledge-base search.
   * Returns mapped DocResult array; throws on API error.
   */
  const searchDocs = async (
    query: string,
    categories: string[],
    topK = 20
  ): Promise<DocResult[]> => {
    const data = await api.post<SearchResponse>(`${getApiBase()}/knowledge_base/search`, {
      query: query || '*',
      top_k: topK,
      filters: categories.length > 0 ? { category: categories } : undefined,
    })

    if (!data?.results) {
      return []
    }

    return data.results.map((r) => ({
      id: r.node_id || r.doc_id,
      contentHash: r.metadata?.content_hash,
      title: r.metadata?.title || 'Untitled',
      content: r.content || '',
      category: r.metadata?.category || 'general',
      section: r.metadata?.section,
      filePath: r.metadata?.file_path || '',
      score: r.score || r.rrf_score,
    }))
  }

  /**
   * Browse paginated documents (used for "load more").
   * Returns mapped DocResult array; throws on API error.
   */
  const browseMore = async (
    query: string,
    category: string | null,
    page: number,
    pageSize = 20
  ): Promise<DocResult[]> => {
    const data = await api.post<BrowseResponse>(
      `${getApiBase()}/knowledge_base/docs/browse`,
      {
        search_query: query,
        category: category || null,
        page,
        page_size: pageSize,
      }
    )

    if (!data?.documents) {
      return []
    }

    return data.documents.map((d) => ({
      id: d.content_hash,
      title: d.title || 'Untitled',
      content: '',
      category: d.category || 'general',
      filePath: d.file_path || '',
    }))
  }

  /**
   * Fetch available documentation categories via useFetchEndpoint (GET).
   * Returns array of DocCategory; throws on API error.
   */
  const fetchCategories = async (): Promise<DocCategory[]> => {
    await categoriesEndpoint.load()
    return categoriesEndpoint.data.value ?? []
  }

  return { searchDocs, browseMore, fetchCategories }
}
