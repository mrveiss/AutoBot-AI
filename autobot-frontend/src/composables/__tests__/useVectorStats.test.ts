// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useVectorStats } from '../knowledge/useVectorStats'

// Mock the store
vi.mock('@/stores/useKnowledgeStore', () => ({
  useKnowledgeStore: vi.fn()
}))

import { useKnowledgeStore } from '@/stores/useKnowledgeStore'

const mockRefreshStats = vi.fn()

describe('useVectorStats', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when store.stats is empty', () => {
    vi.mocked(useKnowledgeStore).mockReturnValue({
      stats: {},
      refreshStats: mockRefreshStats
    } as any)
    const { vectorStats } = useVectorStats()
    expect(vectorStats.value).toBeNull()
  })

  it('returns null when store.stats has no total_facts', () => {
    vi.mocked(useKnowledgeStore).mockReturnValue({
      stats: { total_facts: 0, total_documents: 5 },
      refreshStats: mockRefreshStats
    } as any)
    const { vectorStats } = useVectorStats()
    expect(vectorStats.value).toBeNull()
  })

  it('maps store.stats to VectorStats when total_facts > 0', () => {
    vi.mocked(useKnowledgeStore).mockReturnValue({
      stats: {
        total_facts: 10,
        total_documents: 5,
        total_vectors: 10,
        db_size: 1024,
        status: 'online',
        rag_available: true,
        initialized: true,
        redis_db: '0',
        index_name: 'test-index',
        categories: [{ name: 'cat1' }, 'cat2']
      },
      refreshStats: mockRefreshStats
    } as any)
    const { vectorStats } = useVectorStats()
    expect(vectorStats.value).not.toBeNull()
    expect(vectorStats.value?.total_facts).toBe(10)
    expect(vectorStats.value?.redis_db).toBe(0)
    expect(vectorStats.value?.categories).toEqual(['cat1', 'cat2'])
    expect(vectorStats.value?.embedding_model).toBe('nomic-embed-text')
    expect(vectorStats.value?.embedding_dimensions).toBe(768)
  })

  it('refresh() calls store.refreshStats', async () => {
    vi.mocked(useKnowledgeStore).mockReturnValue({
      stats: { total_facts: 5 },
      refreshStats: mockRefreshStats
    } as any)
    const { refresh } = useVectorStats()
    await refresh()
    expect(mockRefreshStats).toHaveBeenCalledOnce()
  })
})
