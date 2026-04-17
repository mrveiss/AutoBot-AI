/**
 * useKnowledgeCategories Composable
 *
 * Knowledge base category listing, per-category browsing, categorized-fact
 * retrieval, and UI filter-option building.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 * Structural validation (Array.isArray / typeof) preserved — it is real
 * business logic, not error-hiding.
 */

import apiClient from '@/utils/ApiClient'
import { formatCategoryName as formatCategoryHelper } from '@/utils/formatHelpers'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
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

export function useKnowledgeCategories() {
  /**
   * Fetch all categories with counts
   * Returns list of categories with document counts for filtering.
   */
  const fetchCategories = async (): Promise<KnowledgeCategoryItem[]> => {
    const data = await apiClient.get<CategoriesListResponse>(`${getApiBase()}/knowledge_base/categories`)

    // Structural validation — real business logic, not error hiding
    if (!data || !Array.isArray(data.categories)) {
      throw new Error('Invalid categories response format')
    }

    return data.categories
  }

  /**
   * Fetch knowledge by category
   */
  const fetchCategory = (category: string): Promise<CategoryResponse> =>
    apiClient.get<CategoryResponse>(`${getApiBase()}/knowledge_base/category/${category}`)

  /**
   * Fetch facts grouped by category for browsing
   * Uses GET /api/knowledge_base/facts/by_category endpoint.
   * @param category - Optional category filter (null for all categories)
   * @param limit - Maximum number of facts per category (default: 100)
   */
  const getCategorizedFacts = async (
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
   * Build category filter options from categorized facts
   * Helper to create CategoryFilterOption[] for dropdowns/tabs.
   */
  const buildCategoryFilterOptions = (
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

  return {
    fetchCategories,
    fetchCategory,
    getCategorizedFacts,
    buildCategoryFilterOptions,
    getCategoryIcon,
  }
}
