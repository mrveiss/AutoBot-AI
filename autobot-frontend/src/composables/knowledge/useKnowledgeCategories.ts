// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeCategories Composable
 *
 * Knowledge base category listing, per-category browsing, categorized-fact
 * retrieval, and UI filter-option building.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 * Structural validation (Array.isArray / typeof) preserved — it is real
 * business logic, not error-hiding.
 *
 * Reactive refs layer (#5149): the composable now owns loading/error state
 * for `refresh` (categories list) and `refreshCategorizedFacts`. The bare
 * imperative functions remain exported at module scope for the
 * `useKnowledgeBase` BC shim and non-reactive consumers.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { formatCategoryName as formatCategoryHelper } from '@/utils/formatHelpers'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '../useLoadingState'
import type {
  CategoryResponse,
  CategoriesListResponse,
  KnowledgeCategoryItem,
  CategorizedFactsResponse,
  CategoryFilterOption,
} from '@/types/knowledgeBase'

const logger = createLogger('useKnowledgeCategories')

/**
 * Get icon for category (re-exported so consumers + category-option builder
 * share the same mapping without depending on useKnowledgeBase.ts).
 */
export function getCategoryIcon(category: string): string {
  const categoryLower = category.toLowerCase()

  if (categoryLower.includes('architecture') || categoryLower.includes('design')) {
    return 'fas fa-drafting-compass'
  }
  if (categoryLower.includes('implementation') || categoryLower.includes('code')) {
    return 'fas fa-code'
  }
  if (categoryLower.includes('security')) {
    return 'fas fa-shield-alt'
  }
  if (categoryLower.includes('operations') || categoryLower.includes('devops')) {
    return 'fas fa-cogs'
  }
  if (categoryLower.includes('research') || categoryLower.includes('analysis')) {
    return 'fas fa-flask'
  }
  if (categoryLower.includes('reports') || categoryLower.includes('documentation')) {
    return 'fas fa-file-alt'
  }
  if (categoryLower.includes('archives') || categoryLower.includes('history')) {
    return 'fas fa-archive'
  }
  if (categoryLower.includes('project') || categoryLower.includes('planning')) {
    return 'fas fa-project-diagram'
  }

  return 'fas fa-folder'
}

// ==================== Bare imperative API ====================

/**
 * Fetch fact count for a single category (used by CategoryEditModal delete-warning).
 * Hits GET /api/knowledge_base/categories/:id/facts?limit=1 and returns total_count.
 */
export const fetchCategoryFactCount = async (categoryId: string): Promise<number> => {
  const data = await apiClient.get<Record<string, unknown>>(
    `${getApiBase()}/knowledge_base/categories/${encodeURIComponent(categoryId)}/facts?limit=1`
  )
  return typeof data?.total_count === 'number' ? data.total_count : 0
}

/**
 * Update a category's name, description, icon, and/or color.
 * Returns the raw API response (status + message).
 */
export const updateCategory = async (
  categoryId: string,
  payload: { name?: string; description?: string; icon?: string; color?: string }
): Promise<Record<string, unknown>> =>
  apiClient.put<Record<string, unknown>>(
    `${getApiBase()}/knowledge_base/categories/${encodeURIComponent(categoryId)}`,
    payload
  )

/**
 * Delete a category by ID.
 * Returns the raw API response (status + message).
 */
export const deleteKnowledgeCategory = async (
  categoryId: string
): Promise<Record<string, unknown>> =>
  apiClient.delete<Record<string, unknown>>(
    `${getApiBase()}/knowledge_base/categories/${encodeURIComponent(categoryId)}`
  )

/**
 * Fetch all categories with counts.
 * Returns list of categories with document counts for filtering.
 */
export const fetchCategories = async (): Promise<KnowledgeCategoryItem[]> => {
  const data = await apiClient.get<CategoriesListResponse>(`${getApiBase()}/knowledge_base/categories`)

  // Structural validation — real business logic, not error hiding
  if (!data || !Array.isArray(data.categories)) {
    throw new Error('Invalid categories response format')
  }

  return data.categories
}

/**
 * Fetch knowledge by category.
 */
export const fetchCategory = (category: string): Promise<CategoryResponse> =>
  apiClient.get<CategoryResponse>(`${getApiBase()}/knowledge_base/category/${category}`)

/**
 * Fetch facts grouped by category for browsing.
 * Uses GET /api/knowledge_base/facts/by_category endpoint.
 * @param category - Optional category filter (null for all categories)
 * @param limit - Maximum number of facts per category (default: 100)
 */
export const getCategorizedFacts = async (
  category: string | null = null,
  limit: number = 100
): Promise<CategorizedFactsResponse> => {
  const params = new URLSearchParams()
  if (category) {
    params.append('category', category)
  }
  params.append('limit', String(limit))

  const url = `${getApiBase()}/knowledge_base/facts/by_category?${params.toString()}`
  const data = await apiClient.get<CategorizedFactsResponse>(url)

  // Structural validation
  if (!data || typeof data.categories !== 'object') {
    throw new Error('Invalid categorized facts response format')
  }

  logger.debug(
    `Fetched categorized facts: ${data.total_facts} total facts across ${Object.keys(data.categories).length} categories`
  )

  return data
}

/**
 * Build category filter options from categorized facts.
 * Pure helper — does not fetch, no state needed.
 */
export const buildCategoryFilterOptions = (
  categorizedFacts: CategorizedFactsResponse
): CategoryFilterOption[] => {
  const options: CategoryFilterOption[] = [
    {
      value: null,
      label: 'All Categories',
      icon: 'fas fa-th-large',
      count: categorizedFacts.total_facts,
    },
  ]

  for (const [categoryName, facts] of Object.entries(categorizedFacts.categories)) {
    options.push({
      value: categoryName,
      label: formatCategoryHelper(categoryName),
      icon: getCategoryIcon(categoryName),
      count: facts.length,
    })
  }

  // Sort by count (descending), keeping "All" at the top
  options.sort((a, b) => {
    if (a.value === null) return -1
    if (b.value === null) return 1
    return b.count - a.count
  })

  return options
}

// ==================== Reactive composable ====================

export interface MainCategoryItem {
  id: string
  name: string
  description: string
  examples: string
  icon: string
  color: string
  count: number
  [key: string]: unknown
}

export interface CategoryDocumentsResponse {
  documents: Record<string, unknown>[]
  [key: string]: unknown
}

/**
 * Fetch the main category cards shown on the KnowledgeCategories landing page.
 * Returns the validated categories array or throws.
 */
export const fetchMainCategories = async (): Promise<MainCategoryItem[]> => {
  const data = await apiClient.get<Record<string, unknown>>(`${getApiBase()}/knowledge_base/categories/main`)
  if (!data?.categories || !Array.isArray(data.categories)) {
    throw new Error('Invalid main categories response format')
  }
  return data.categories as MainCategoryItem[]
}

/**
 * Fetch all documents for a specific category path.
 */
export const fetchCategoryDocuments = async (
  categoryPath: string
): Promise<Record<string, unknown>[]> => {
  const data = await apiClient.get<CategoryDocumentsResponse>(
    `${getApiBase()}/knowledge_base/categories/${encodeURIComponent(categoryPath)}`
  )
  return data?.documents ?? []
}

export interface UseKnowledgeCategoriesReturn {
  /** Latest categories list. */
  categories: Readonly<Ref<KnowledgeCategoryItem[]>>
  /** Latest categorized-facts result. */
  categorizedFacts: Readonly<Ref<CategorizedFactsResponse | null>>
  /** True while a refresh is in-flight. */
  isLoading: Readonly<Ref<boolean>>
  /** Last error raised by a refresh, cleared on the next call. */
  error: Readonly<Ref<Error | null>>
  /** Fetch the categories list, update `categories` + state refs. */
  refresh: () => Promise<KnowledgeCategoryItem[]>
  /** Fetch categorized facts, update `categorizedFacts` + state refs. */
  refreshCategorizedFacts: (
    category?: string | null,
    limit?: number
  ) => Promise<CategorizedFactsResponse>
  // Imperative passthroughs — BC with pre-#5149 callers
  fetchCategories: typeof fetchCategories
  fetchCategory: typeof fetchCategory
  fetchMainCategories: typeof fetchMainCategories
  fetchCategoryDocuments: typeof fetchCategoryDocuments
  getCategorizedFacts: typeof getCategorizedFacts
  buildCategoryFilterOptions: typeof buildCategoryFilterOptions
  getCategoryIcon: typeof getCategoryIcon
  // Category CRUD — migrated from CategoryEditModal (#6044)
  fetchCategoryFactCount: typeof fetchCategoryFactCount
  updateCategory: typeof updateCategory
  deleteKnowledgeCategory: typeof deleteKnowledgeCategory
}

export function useKnowledgeCategories(): UseKnowledgeCategoriesReturn {
  const categories = ref<KnowledgeCategoryItem[]>([])
  const categorizedFacts = ref<CategorizedFactsResponse | null>(null)
  const { isLoading, wrap } = useLoadingState()
  const error = ref<Error | null>(null)

  const refresh = async (): Promise<KnowledgeCategoryItem[]> => {
    error.value = null
    return wrap(async () => {
      try {
        const data = await fetchCategories()
        categories.value = data
        return data
      } catch (err) {
        error.value = err instanceof Error ? err : new Error(String(err))
        throw err
      }
    })
  }

  const refreshCategorizedFacts = async (
    category: string | null = null,
    limit: number = 100
  ): Promise<CategorizedFactsResponse> => {
    error.value = null
    return wrap(async () => {
      try {
        const data = await getCategorizedFacts(category, limit)
        categorizedFacts.value = data
        return data
      } catch (err) {
        error.value = err instanceof Error ? err : new Error(String(err))
        throw err
      }
    })
  }

  return {
    categories: readonly(categories) as Readonly<Ref<KnowledgeCategoryItem[]>>,
    categorizedFacts: readonly(categorizedFacts) as Readonly<Ref<CategorizedFactsResponse | null>>,
    isLoading: readonly(isLoading),
    error: readonly(error),
    refresh,
    refreshCategorizedFacts,
    fetchCategories,
    fetchCategory,
    fetchMainCategories,
    fetchCategoryDocuments,
    getCategorizedFacts,
    buildCategoryFilterOptions,
    getCategoryIcon,
    fetchCategoryFactCount,
    updateCategory,
    deleteKnowledgeCategory,
  }
}
