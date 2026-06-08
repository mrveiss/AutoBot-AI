// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2026 mrveiss
// Author: mrveiss
/**
 * Regression tests for #5215 (found during #5207 audit) —
 * KnowledgeRepository stats + categories response-shape handling.
 *
 * Backend `/api/knowledge_base/stats/basic`, `/detailed_stats`, and
 * `/categories` all return shapes that the previous declarations lied
 * about. These tests lock in the real backend contracts so a future
 * edit can't silently reintroduce the mismatch.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeRepository } from '../KnowledgeRepository'

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api'
}))

describe('KnowledgeRepository stats endpoints (#5215)', () => {
  let repo: KnowledgeRepository
  let getSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    repo = new KnowledgeRepository()
    getSpy = vi.fn()
    // @ts-expect-error - override inherited method for unit test isolation
    repo.get = getSpy
  })

  describe('getKnowledgeStats — /knowledge_base/stats/basic', () => {
    it('returns the backend shape (total_facts/total_vectors/categories/status)', async () => {
      getSpy.mockResolvedValue({
        data: {
          total_facts: 42,
          total_vectors: 13,
          categories: ['autobot_memory', 'docs'],
          status: 'online'
        }
      })

      const result = await repo.getKnowledgeStats()

      expect(getSpy).toHaveBeenCalledWith('/api/knowledge_base/stats/basic')
      expect(result).toEqual({
        total_facts: 42,
        total_vectors: 13,
        categories: ['autobot_memory', 'docs'],
        status: 'online'
      })
    })

    it('coerces a missing envelope into a safe zeroed default', async () => {
      getSpy.mockResolvedValue({ data: undefined })

      const result = await repo.getKnowledgeStats()

      expect(result).toEqual({
        total_facts: 0,
        total_vectors: 0,
        categories: [],
        status: 'unknown'
      })
    })

    it('coerces a non-array categories field into an empty array', async () => {
      // Older backend revs occasionally returned `{"cat": count}` map shape
      getSpy.mockResolvedValue({
        data: {
          total_facts: 1,
          total_vectors: 2,
          categories: { autobot_memory: 1 } as unknown as string[],
          status: 'online'
        }
      })

      const result = await repo.getKnowledgeStats()

      expect(result.categories).toEqual([])
      expect(result.total_facts).toBe(1)
    })
  })

  describe('getDetailedKnowledgeStats — /knowledge_base/detailed_stats', () => {
    it('returns the nested envelope shape the backend actually emits', async () => {
      getSpy.mockResolvedValue({
        data: {
          status: 'online',
          basic_stats: {
            total_documents: 0,
            total_chunks: 0,
            total_facts: 0,
            total_vectors: 0,
            categories: ['autobot_memory'],
            db_size: 80519456,
            status: 'online',
            last_updated: '2026-04-20T06:08:51.983737+00:00',
            vector_store: 'chromadb'
          },
          category_breakdown: { memory: 5 },
          source_breakdown: { manual: 3 },
          type_breakdown: { fact: 4 },
          size_metrics: {
            total_content_size: 1024,
            average_fact_size: 128,
            median_fact_size: 100,
            largest_fact_size: 512,
            smallest_fact_size: 8
          },
          rag_available: true
        }
      })

      const result = await repo.getDetailedKnowledgeStats()

      expect(getSpy).toHaveBeenCalledWith('/api/knowledge_base/detailed_stats')
      expect(result.status).toBe('online')
      expect(result.basic_stats.total_facts).toBe(0)
      expect(result.basic_stats.categories).toEqual(['autobot_memory'])
      expect(result.basic_stats.vector_store).toBe('chromadb')
      expect(result.category_breakdown).toEqual({ memory: 5 })
      expect(result.size_metrics.total_content_size).toBe(1024)
      expect(result.rag_available).toBe(true)
    })

    it('coerces a missing envelope into a safe zeroed default', async () => {
      getSpy.mockResolvedValue({ data: undefined })

      const result = await repo.getDetailedKnowledgeStats()

      expect(result.status).toBe('unknown')
      expect(result.basic_stats).toEqual({
        total_facts: 0,
        total_vectors: 0,
        categories: [],
        status: 'unknown'
      })
      expect(result.category_breakdown).toEqual({})
      expect(result.source_breakdown).toEqual({})
      expect(result.type_breakdown).toEqual({})
      expect(result.size_metrics).toEqual({
        total_content_size: 0,
        average_fact_size: 0,
        median_fact_size: 0,
        largest_fact_size: 0,
        smallest_fact_size: 0
      })
      expect(result.rag_available).toBe(false)
    })
  })

  describe('getCategories — /knowledge_base/categories', () => {
    it('unwraps {categories, total} envelope into a bare KnowledgeCategoryEntry[]', async () => {
      getSpy.mockResolvedValue({
        data: {
          categories: [
            { name: 'autobot_memory', count: 0, id: 'autobot_memory' },
            { name: 'autobot_docs', count: 5638, id: 'autobot_docs' }
          ],
          total: 2
        }
      })

      const result = await repo.getCategories()

      expect(getSpy).toHaveBeenCalledWith('/api/knowledge_base/categories')
      expect(result).toHaveLength(2)
      expect(result[0]).toEqual({ name: 'autobot_memory', count: 0, id: 'autobot_memory' })
      expect(result[1].count).toBe(5638)
    })

    it('returns [] when the envelope is missing or malformed', async () => {
      getSpy.mockResolvedValue({ data: undefined })
      expect(await repo.getCategories()).toEqual([])

      getSpy.mockResolvedValue({ data: {} })
      expect(await repo.getCategories()).toEqual([])

      getSpy.mockResolvedValue({ data: { categories: 'not-an-array' } })
      expect(await repo.getCategories()).toEqual([])
    })
  })
})
