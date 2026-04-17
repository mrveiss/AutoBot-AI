/**
 * useKnowledgeFacts Composable Tests
 *
 * Split from useKnowledgeBase.test.ts (#5122).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import type {
  SearchResponse,
  AddFactResponse,
} from '@/types/knowledgeBase'
import { useKnowledgeFacts } from '../knowledge/useKnowledgeFacts'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/knowledge_base',
}))

import apiClient from '@/utils/ApiClient'

describe('useKnowledgeFacts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('searchKnowledge', () => {
    it('should perform basic keyword search', async () => {
      const mockSearchResult: SearchResponse = {
        results: [
          { id: '1', fact: 'matching fact', similarity_score: 0.95 },
        ],
        total_results: 1,
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockSearchResult)

      const { searchKnowledge } = useKnowledgeFacts()
      const result = await searchKnowledge('test query')

      expect(result).toEqual(mockSearchResult)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/search',
        { query: 'test query' }
      )
    })

    it('should throw error when search fails', async () => {
      vi.mocked(apiClient.post).mockRejectedValue(new Error('HTTP 500: Search backend error'))

      const { searchKnowledge } = useKnowledgeFacts()

      await expect(searchKnowledge('test')).rejects.toThrow('HTTP 500')
    })
  })

  describe('advancedSearch', () => {
    it('should perform advanced search with all options', async () => {
      const mockResults: SearchResponse = {
        results: [{ id: '1', fact: 'semantic match', similarity_score: 0.98 }],
        total_results: 1,
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockResults)

      const { advancedSearch } = useKnowledgeFacts()
      const result = await advancedSearch({
        query: 'test',
        mode: 'semantic',
        enable_rag: true,
        category: 'security',
        top_k: 10,
      })

      expect(result).toEqual(mockResults)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/search',
        expect.objectContaining({
          query: 'test',
          mode: 'semantic',
          enable_rag: true,
          category: 'security',
        })
      )
    })

    it('should support hybrid search mode', async () => {
      const mockResults: SearchResponse = { results: [], total_results: 0 }

      vi.mocked(apiClient.post).mockResolvedValue(mockResults)

      const { advancedSearch } = useKnowledgeFacts()
      await advancedSearch({
        query: 'test',
        mode: 'hybrid',
        enable_reranking: true,
      })

      expect(apiClient.post).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          mode: 'hybrid',
          enable_reranking: true,
        })
      )
    })
  })

  describe('addFact', () => {
    it('should add a new fact to knowledge base', async () => {
      const mockAddResponse: AddFactResponse = {
        success: true,
        fact_id: 'fact-123',
        fact: {
          id: 'fact-123',
          fact: 'New security fact',
          category: 'security',
          created_at: '2025-04-12T10:00:00Z',
          updated_at: '2025-04-12T10:00:00Z',
        },
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockAddResponse)

      const { addFact } = useKnowledgeFacts()
      const result = await addFact({
        content: 'New security fact',
        category: 'security',
      })

      expect(result).toEqual(mockAddResponse)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/facts',
        expect.objectContaining({
          content: 'New security fact',
          category: 'security',
        })
      )
    })

    it('should add fact with metadata', async () => {
      const mockAddResponse: AddFactResponse = {
        success: true,
        fact_id: 'fact-456',
        fact: {
          id: 'fact-456',
          fact: 'Fact with metadata',
          category: 'architecture',
          created_at: '2025-04-12T10:00:00Z',
          updated_at: '2025-04-12T10:00:00Z',
        },
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockAddResponse)

      const { addFact } = useKnowledgeFacts()
      const result = await addFact({
        content: 'Fact with metadata',
        category: 'architecture',
        metadata: { source: 'manual', priority: 'high' },
      })

      expect(result.success).toBe(true)
    })
  })
})
