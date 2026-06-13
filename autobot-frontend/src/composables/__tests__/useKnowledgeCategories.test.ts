// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeCategories Composable Tests
 *
 * Split from useKnowledgeBase.test.ts (#5122).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import type {
  CategoryResponse,
  CategoriesListResponse,
  CategorizedFactsResponse,
} from '@/types/knowledgeBase'
import { useKnowledgeCategories } from '../knowledge/useKnowledgeCategories'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/utils/formatHelpers', () => ({
  formatCategoryName: (name: string) => name.replace(/_/g, ' ').toUpperCase(),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/knowledge_base',
}))

import apiClient from '@/utils/ApiClient'

describe('useKnowledgeCategories', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('fetchCategories', () => {
    it('should fetch all categories with counts', async () => {
      const mockCategoriesResponse: CategoriesListResponse = {
        categories: [
          { name: 'architecture', count: 10, id: 'arch-1' },
          { name: 'security', count: 15, id: 'sec-1' },
        ],
        total: 2,
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockCategoriesResponse)

      const { fetchCategories } = useKnowledgeCategories()
      const result = await fetchCategories()

      expect(result).toEqual(mockCategoriesResponse.categories)
      expect(apiClient.get).toHaveBeenCalledWith('/knowledge_base/knowledge_base/categories')
    })

    it('should throw error when response structure is invalid', async () => {
      const invalidResponse: unknown = { notCategories: [] }

      vi.mocked(apiClient.get).mockResolvedValue(invalidResponse)

      const { fetchCategories } = useKnowledgeCategories()

      await expect(fetchCategories()).rejects.toThrow('Invalid categories response format')
    })
  })

  describe('fetchCategory', () => {
    it('should fetch facts for a specific category', async () => {
      const mockCategory: CategoryResponse = {
        facts: [
          { id: '1', fact: 'Use strong passwords', category: 'security', created_at: '2025-04-12T10:00:00Z', updated_at: '2025-04-12T10:00:00Z' },
        ],
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockCategory)

      const { fetchCategory } = useKnowledgeCategories()
      const result = await fetchCategory('security')

      expect(result).toEqual(mockCategory)
      expect(apiClient.get).toHaveBeenCalledWith('/knowledge_base/knowledge_base/category/security')
    })

    it('should throw error for invalid category', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('HTTP 404: Category not found'))

      const { fetchCategory } = useKnowledgeCategories()

      await expect(fetchCategory('nonexistent')).rejects.toThrow('HTTP 404')
    })
  })

  describe('getCategorizedFacts', () => {
    it('should fetch categorized facts', async () => {
      const mockCategorizedFacts: CategorizedFactsResponse = {
        total_facts: 50,
        categories: {
          security: [
            { key: '1', title: 'fact1', content: 'fact1 content', category: 'security', type: 'general', metadata: {} },
            { key: '2', title: 'fact2', content: 'fact2 content', category: 'security', type: 'general', metadata: {} },
          ],
          architecture: [
            { key: '3', title: 'fact3', content: 'fact3 content', category: 'architecture', type: 'general', metadata: {} },
          ],
        },
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockCategorizedFacts)

      const { getCategorizedFacts } = useKnowledgeCategories()
      const result = await getCategorizedFacts()

      expect(result).toEqual(mockCategorizedFacts)
      expect(result.total_facts).toBe(50)
      expect(Object.keys(result.categories).length).toBe(2)
    })

    it('should respect category filter parameter', async () => {
      const mockCategorizedFacts: CategorizedFactsResponse = {
        total_facts: 2,
        categories: {
          security: [
            {
              key: '1',
              title: 'fact1',
              content: 'fact1',
              category: 'security',
              type: 'general',
              metadata: {},
            },
          ],
        },
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockCategorizedFacts)

      const { getCategorizedFacts } = useKnowledgeCategories()
      await getCategorizedFacts('security', 100)

      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringContaining('category=security')
      )
    })

    it('should throw error for invalid response format', async () => {
      const invalidResponse: unknown = { total_facts: 0, noCategoriesField: {} }

      vi.mocked(apiClient.get).mockResolvedValue(invalidResponse)

      const { getCategorizedFacts } = useKnowledgeCategories()

      await expect(getCategorizedFacts()).rejects.toThrow('Invalid categorized facts response format')
    })
  })

  describe('buildCategoryFilterOptions', () => {
    it('should build filter options from categorized facts', () => {
      const categorizedFacts: CategorizedFactsResponse = {
        total_facts: 5,
        categories: {
          security: [
            { key: '1', title: 'f1', content: 'fact1', category: 'security', type: 'general', metadata: {} },
            { key: '2', title: 'f2', content: 'fact2', category: 'security', type: 'general', metadata: {} },
          ],
          architecture: [
            { key: '3', title: 'f3', content: 'fact3', category: 'architecture', type: 'general', metadata: {} },
          ],
        },
      }

      const { buildCategoryFilterOptions } = useKnowledgeCategories()
      const options = buildCategoryFilterOptions(categorizedFacts)

      expect(options.length).toBe(3)
      expect(options[0].label).toBe('All Categories')
      expect(options[0].value).toBe(null)
      expect(options[0].count).toBe(5)
    })

    it('should sort options by count descending', () => {
      const categorizedFacts: CategorizedFactsResponse = {
        total_facts: 6,
        categories: {
          small: [
            { key: '1', title: 'f1', content: 'fact1', category: 'small', type: 'general', metadata: {} },
          ],
          big: [
            { key: '2', title: 'f2', content: 'fact2', category: 'big', type: 'general', metadata: {} },
            { key: '3', title: 'f3', content: 'fact3', category: 'big', type: 'general', metadata: {} },
            { key: '4', title: 'f4', content: 'fact4', category: 'big', type: 'general', metadata: {} },
          ],
        },
      }

      const { buildCategoryFilterOptions } = useKnowledgeCategories()
      const options = buildCategoryFilterOptions(categorizedFacts)

      expect(options[0].value).toBe(null)
      expect(options[1].count).toBeGreaterThanOrEqual(options[2].count)
    })
  })

  describe('getCategoryIcon', () => {
    it('should return correct icon for security category', () => {
      const { getCategoryIcon } = useKnowledgeCategories()
      expect(getCategoryIcon('security')).toBe('shield-alt')
    })

    it('should return correct icon for architecture category', () => {
      const { getCategoryIcon } = useKnowledgeCategories()
      expect(getCategoryIcon('architecture')).toBe('sitemap')
    })

    it('should return correct icon for devops category', () => {
      const { getCategoryIcon } = useKnowledgeCategories()
      expect(getCategoryIcon('devops')).toBe('cogs')
    })

    it('should return default folder icon for unknown category', () => {
      const { getCategoryIcon } = useKnowledgeCategories()
      expect(getCategoryIcon('unknown')).toBe('folder')
    })

    it('should handle case-insensitive matching', () => {
      const { getCategoryIcon } = useKnowledgeCategories()
      expect(getCategoryIcon('SECURITY')).toBe('shield-alt')
      expect(getCategoryIcon('SeCuRiTy')).toBe('shield-alt')
    })
  })

  describe('reactive refs + refresh (#5149)', () => {
    it('should populate categories + isLoading refs on refresh', async () => {
      const mockResponse: CategoriesListResponse = {
        categories: [{ name: 'security', count: 3, id: 's-1' }],
        total: 1,
      }
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse)

      const { categories, isLoading, error, refresh } = useKnowledgeCategories()

      expect(categories.value).toEqual([])
      expect(isLoading.value).toBe(false)

      const promise = refresh()
      expect(isLoading.value).toBe(true)

      const data = await promise
      expect(data).toEqual(mockResponse.categories)
      expect(categories.value).toEqual(mockResponse.categories)
      expect(isLoading.value).toBe(false)
      expect(error.value).toBe(null)
    })

    it('should surface error via error ref when refresh fails', async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ notCategories: [] })

      const { error, isLoading, refresh } = useKnowledgeCategories()

      await expect(refresh()).rejects.toThrow('Invalid categories response format')
      expect(isLoading.value).toBe(false)
      expect(error.value).toBeInstanceOf(Error)
    })

    it('refreshCategorizedFacts populates categorizedFacts ref', async () => {
      const mockCategorizedFacts: CategorizedFactsResponse = {
        total_facts: 1,
        categories: {
          security: [
            { key: '1', title: 'f1', content: 'c', category: 'security', type: 'general', metadata: {} },
          ],
        },
      }
      vi.mocked(apiClient.get).mockResolvedValue(mockCategorizedFacts)

      const { categorizedFacts, refreshCategorizedFacts } = useKnowledgeCategories()
      const data = await refreshCategorizedFacts()

      expect(data).toEqual(mockCategorizedFacts)
      expect(categorizedFacts.value).toEqual(mockCategorizedFacts)
    })
  })
})
