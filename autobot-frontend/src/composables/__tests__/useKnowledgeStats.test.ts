// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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

  describe('reactive refs + refresh (#5149)', () => {
    it('should expose stats/isLoading/error refs and populate them on refresh', async () => {
      const mockStats: KnowledgeStats = {
        total_facts: 42,
        total_documents: 10,
      }
      vi.mocked(apiClient.get).mockResolvedValue(mockStats)

      const { stats, isLoading, error, refresh } = useKnowledgeStats()

      expect(stats.value).toBe(null)
      expect(isLoading.value).toBe(false)
      expect(error.value).toBe(null)

      const promise = refresh()
      // isLoading flips true synchronously inside refresh
      expect(isLoading.value).toBe(true)

      const data = await promise
      expect(data).toEqual(mockStats)
      expect(stats.value).toEqual(mockStats)
      expect(isLoading.value).toBe(false)
      expect(error.value).toBe(null)
    })

    it('should populate error ref and reset isLoading when refresh throws', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('boom'))

      const { stats, isLoading, error, refresh } = useKnowledgeStats()

      await expect(refresh()).rejects.toThrow('boom')
      expect(stats.value).toBe(null)
      expect(isLoading.value).toBe(false)
      expect(error.value).toBeInstanceOf(Error)
      expect(error.value?.message).toBe('boom')
    })

    it('refreshBasic should populate basicStats ref on success', async () => {
      const mockStats: KnowledgeStats = { total_facts: 5, total_documents: 1 }
      vi.mocked(apiClient.get).mockResolvedValue(mockStats)

      const { basicStats, refreshBasic } = useKnowledgeStats()
      const data = await refreshBasic()

      expect(data).toEqual(mockStats)
      expect(basicStats.value).toEqual(mockStats)
    })
  })
})
