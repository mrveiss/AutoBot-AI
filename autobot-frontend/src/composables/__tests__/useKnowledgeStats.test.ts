/**
 * useKnowledgeStats Composable Tests
 *
 * Split from useKnowledgeBase.test.ts (#5122).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { KnowledgeStats } from '@/types/knowledgeBase'
import { useKnowledgeStats } from '../knowledge/useKnowledgeStats'

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

describe('useKnowledgeStats', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('fetchStats', () => {
    it('should fetch knowledge base statistics successfully', async () => {
      const mockStats: KnowledgeStats = {
        total_facts: 100,
        total_documents: 50,
        last_updated: '2025-04-12T10:00:00Z',
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockStats)

      const { fetchStats } = useKnowledgeStats()
      const result = await fetchStats()

      expect(result).toEqual(mockStats)
      expect(apiClient.get).toHaveBeenCalledWith('/knowledge_base/knowledge_base/stats')
    })

    it('should throw error when stats fetch fails', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('HTTP 500: Server error'))

      const { fetchStats } = useKnowledgeStats()

      await expect(fetchStats()).rejects.toThrow('HTTP 500')
    })
  })

  describe('fetchBasicStats', () => {
    it('should fetch basic statistics', async () => {
      const mockStats: KnowledgeStats = {
        total_facts: 75,
        total_documents: 3,
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockStats)

      const { fetchBasicStats } = useKnowledgeStats()
      const result = await fetchBasicStats()

      expect(result).toEqual(mockStats)
      expect(apiClient.get).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/stats/basic'
      )
    })

    it('should return null when fetch fails', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('HTTP 500'))

      const { fetchBasicStats } = useKnowledgeStats()
      const result = await fetchBasicStats()

      expect(result).toBe(null)
    })
  })
})
