// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useVectorStats, EMPTY_VECTOR_STATS } from '../knowledge/useVectorStats'
import type { KnowledgeStats } from '@/types/knowledgeBase'

// Mock the store
vi.mock('@/stores/useKnowledgeStore', () => ({
  useKnowledgeStore: vi.fn()
}))

import { useKnowledgeStore } from '@/stores/useKnowledgeStore'

const mockRefreshStats = vi.fn()

/** Install a store stub exposing only what useVectorStats consumes. */
function mockStore(stats: KnowledgeStats): void {
  vi.mocked(useKnowledgeStore).mockReturnValue({
    stats,
    refreshStats: mockRefreshStats
  } as unknown as ReturnType<typeof useKnowledgeStore>)
}

describe('useVectorStats', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when store.stats is empty', () => {
    mockStore({})
    const { vectorStats } = useVectorStats()
    expect(vectorStats.value).toBeNull()
  })

  it('returns null when store.stats has no total_facts', () => {
    mockStore({ total_facts: 0, total_documents: 5 })
    const { vectorStats } = useVectorStats()
    expect(vectorStats.value).toBeNull()
  })

  it('maps store.stats to VectorStats when total_facts > 0', () => {
    mockStore({
      total_facts: 10,
      total_documents: 5,
      total_vectors: 10,
      db_size: 1024,
      status: 'online',
      rag_available: true,
      initialized: true,
      redis_db: '0',
      index_name: 'test-index',
      categories: [{ name: 'cat1' }, 'cat2'] as unknown as string[]
    })
    const { vectorStats } = useVectorStats()
    expect(vectorStats.value).not.toBeNull()
    expect(vectorStats.value?.total_facts).toBe(10)
    expect(vectorStats.value?.redis_db).toBe(0)
    expect(vectorStats.value?.categories).toEqual(['cat1', 'cat2'])
    expect(vectorStats.value?.embedding_model).toBe('nomic-embed-text')
    expect(vectorStats.value?.embedding_dimensions).toBe(768)
  })

  it('applies defaults for missing optional fields', () => {
    mockStore({ total_facts: 1 })
    const { vectorStats } = useVectorStats()
    expect(vectorStats.value).toMatchObject({
      total_facts: 1,
      total_documents: 0,
      total_vectors: 0,
      status: 'offline',
      rag_available: false,
      initialized: false,
      redis_db: 0,
      index_name: 'unknown',
      categories: []
    })
    expect(vectorStats.value?.last_updated).toBeUndefined()
  })

  it('refresh() calls store.refreshStats', async () => {
    mockStore({ total_facts: 5 })
    const { refresh } = useVectorStats()
    await refresh()
    expect(mockRefreshStats).toHaveBeenCalledOnce()
  })

  it('EMPTY_VECTOR_STATS is a frozen zeroed offline fallback', () => {
    expect(EMPTY_VECTOR_STATS.total_facts).toBe(0)
    expect(EMPTY_VECTOR_STATS.status).toBe('offline')
    expect(EMPTY_VECTOR_STATS.index_name).toBe('unknown')
    expect(Object.isFrozen(EMPTY_VECTOR_STATS)).toBe(true)
  })
})
