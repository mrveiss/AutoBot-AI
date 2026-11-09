// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useKnowledgeGraphEntities facts cursor — Issue #20945.
 *
 * The server pages facts by a scan cursor so a readable fact is never unreachable past the scan cap;
 * the composable follows the facts section's cursor until the server returns none.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('@/utils/ApiClient', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

import apiClient from '@/utils/ApiClient'
import { useKnowledgeGraphEntities } from '../knowledge/useKnowledgeGraphEntities'

const entity = (id: string) => ({ id, name: id, type: 'fact', observations: [] })
const page = (ids: string[], cursor: string | null) => ({
  data: { entities: ids.map(entity), relations: [] },
  stats: { sections: [{ key: 'facts', cursor }] },
})

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset()
})

describe('facts cursor paging (#20945)', () => {
  it('follows the cursor, merges the next page and stops when the server returns none', async () => {
    const urls: string[] = []
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      urls.push(url)
      if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
      if (url.includes('cursor=500%3A0')) return page(['b', 'a'], null) as never
      return page(['a'], '500:0') as never
    })
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()
    expect(graph.hasMoreFacts.value).toBe(true)
    await graph.loadMoreFacts()
    expect(graph.entities.value.map((e) => e.id)).toEqual(['a', 'b'])
    expect(graph.hasMoreFacts.value).toBe(false)
    expect(urls.some((u) => u.includes('cursor=500%3A0') && u.includes('include_buckets=false'))).toBe(true)
  })

  it('reports a failed next page without losing the page already shown', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
      if (url.includes('cursor=')) throw new Error('boom')
      return page(['a'], '500:0') as never
    })
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()
    await graph.loadMoreFacts()
    expect(graph.entities.value.map((e) => e.id)).toEqual(['a'])
    expect(graph.errorMessage.value).not.toBe('')
    expect(graph.hasMoreFacts.value).toBe(true)
  })
})
