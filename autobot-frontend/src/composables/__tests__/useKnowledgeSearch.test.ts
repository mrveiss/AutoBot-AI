// Copyright (c) 2026 mrveiss
// Unit tests for useKnowledgeSearch (extracted from KnowledgeSearch.vue)
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const ragSearch = vi.fn()
const searchKnowledge = vi.fn()
vi.mock('@/models/repositories', () => ({
  knowledgeRepository: { ragSearch: (...a: unknown[]) => ragSearch(...a), searchKnowledge: (...a: unknown[]) => searchKnowledge(...a) },
}))

import { useKnowledgeSearch } from '../knowledge/useKnowledgeSearch'

describe('useKnowledgeSearch', () => {
  beforeEach(() => { ragSearch.mockReset(); searchKnowledge.mockReset() })

  it('traditional search passes the injected category as a filter', async () => {
    searchKnowledge.mockResolvedValue([{ document: { id: '1' } }])
    const category = ref<string | null>('linux')
    const s = useKnowledgeSearch(category)
    s.searchQuery.value = 'grep'
    await s.handleSearch()
    expect(searchKnowledge).toHaveBeenCalledWith(expect.objectContaining({
      query: 'grep', use_rag: false, filters: { categories: ['linux'] },
    }))
    expect(s.searchResults.value).toHaveLength(1)
    expect(s.searchPerformed.value).toBe(true)
    expect(s.lastSearchQuery.value).toBe('grep')
  })

  it('RAG search failure falls back to traditional search and records ragError', async () => {
    ragSearch.mockRejectedValue(new Error('rag down'))
    searchKnowledge.mockResolvedValue([])
    const s = useKnowledgeSearch(ref(null))
    s.useRagSearch.value = true
    s.searchQuery.value = 'x'
    await s.handleSearch()
    expect(s.ragError.value).toBe('rag down')
    expect(searchKnowledge).toHaveBeenCalled()
  })

  it('access-level filter is applied client-side', async () => {
    searchKnowledge.mockResolvedValue([
      { document: { id: '1', access_level: 'system' } },
      { document: { id: '2', access_level: 'user' } },
    ])
    const s = useKnowledgeSearch(ref(null))
    s.selectedAccessLevel.value = 'system'
    s.searchQuery.value = 'x'
    await s.handleSearch()
    expect(s.searchResults.value.map(r => r.document?.id)).toEqual(['1'])
  })

  it('clearResults resets search state', async () => {
    searchKnowledge.mockResolvedValue([{ document: { id: '1' } }])
    const s = useKnowledgeSearch(ref(null))
    s.searchQuery.value = 'x'
    await s.handleSearch()
    s.clearResults()
    expect(s.searchResults.value).toEqual([])
    expect(s.searchPerformed.value).toBe(false)
    expect(s.ragResponse.value).toBeNull()
  })
})
