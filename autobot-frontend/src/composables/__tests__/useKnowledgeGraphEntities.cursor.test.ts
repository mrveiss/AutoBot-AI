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
  default: { get: vi.fn(), post: vi.fn(), call: vi.fn() },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

vi.mock('@/i18n', () => ({ default: { global: { t: (key: string) => key } } }))

import apiClient from '@/utils/ApiClient'
import { useKnowledgeGraphEntities } from '../knowledge/useKnowledgeGraphEntities'

const entity = (id: string) => ({ id, name: id, type: 'fact', observations: [] })
const page = (ids: string[], cursor: string | null) => ({
  data: { entities: ids.map(entity), relations: [] },
  stats: { sections: [{ key: 'facts', cursor }] },
})

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset()
  vi.mocked(apiClient.call).mockReset()
})

describe('facts cursor paging (#20945)', () => {
  it('follows the cursor, merges the next page and stops when the server returns none', async () => {
    const queries: Array<Record<string, unknown>> = []
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
      return page(['a'], '500:0') as never
    })
    vi.mocked(apiClient.call).mockImplementation((async (_verb: string, _path: string, opts: { query: Record<string, unknown> }) => {
      queries.push(opts.query)
      return page(['b', 'a'], null)
    }) as never)
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()
    expect(graph.hasMoreFacts.value).toBe(true)
    await graph.loadMoreFacts()
    expect(graph.entities.value.map((e) => e.id)).toEqual(['a', 'b'])
    expect(graph.hasMoreFacts.value).toBe(false)
    expect(queries).toEqual([{ max_facts: 100, include_buckets: false, cursor: '500:0' }])
  })

  it('keeps one relation when two sequential pages carry the same category relation', async () => {
    const withRelation = (ids: string[], cursor: string | null) => ({
      data: {
        entities: ids.map(entity),
        relations: [{ from: 'cat_a', to: 'cat_b', type: 'contains', strength: 1 }],
      },
      stats: { sections: [{ key: 'facts', cursor }] },
    })
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
      return withRelation(['a'], '500:0') as never
    })
    vi.mocked(apiClient.call).mockResolvedValue(withRelation(['b'], null) as never)
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()
    await graph.loadMoreFacts()
    expect(graph.relations.value).toEqual([{ from: 'cat_a', to: 'cat_b', type: 'contains', strength: 1 }])
  })

  it('treats a page the server marks failed as a failure and keeps the graph and the cursor', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
      return page(['a'], '500:0') as never
    })
    const failedPage = { ...page([], '500:0'), stats: { sections: [{ key: 'facts', cursor: '500:0', failed: true }] } }
    vi.mocked(apiClient.call).mockResolvedValue(failedPage as never)
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()
    await graph.loadMoreFacts()
    expect(graph.errorMessage.value).toBe('knowledge.graph.loadFailedNoReason')
    expect(graph.entities.value.map((e) => e.id)).toEqual(['a'])
    expect(graph.hasMoreFacts.value).toBe(true)
    vi.mocked(apiClient.call).mockResolvedValue(page(['b'], null) as never)
    await graph.loadMoreFacts()
    expect(graph.entities.value.map((e) => e.id)).toEqual(['a', 'b'])
    expect(graph.errorMessage.value).toBe('')
  })

  it('treats an unchanged cursor with nothing new as a failure', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
      return page(['a'], '500:0') as never
    })
    vi.mocked(apiClient.call).mockResolvedValue(page(['a'], '500:0') as never)
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()
    await graph.loadMoreFacts()
    expect(graph.errorMessage.value).toBe('knowledge.graph.loadFailedNoReason')
    expect(graph.entities.value.map((e) => e.id)).toEqual(['a'])
  })

  it('reports a failed next page without losing the page already shown', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
      return page(['a'], '500:0') as never
    })
    vi.mocked(apiClient.call).mockRejectedValue(new Error('boom'))
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()
    await graph.loadMoreFacts()
    expect(graph.entities.value.map((e) => e.id)).toEqual(['a'])
    expect(graph.errorMessage.value).not.toBe('')
    expect(graph.hasMoreFacts.value).toBe(true)
  })

  it('names a failure that carries no message with the translated fallback, never an empty banner', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
      return page(['a'], '500:0') as never
    })
    vi.mocked(apiClient.call).mockRejectedValue(new Error(''))
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()
    await graph.loadMoreFacts()
    expect(graph.errorMessage.value).toBe('knowledge.graph.loadFailedNoReason')
  })

  it('serialises overlapping calls: one request, the page appended once', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
      return page(['a'], '500:0') as never
    })
    let release: (value: unknown) => void = () => undefined
    vi.mocked(apiClient.call).mockImplementation((() => new Promise((resolve) => { release = resolve })) as never)
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()
    const first = graph.loadMoreFacts()
    const second = graph.loadMoreFacts()
    expect(graph.isLoadingMore.value).toBe(true)
    expect(graph.isLoading.value).toBe(false)
    release(page(['b'], null))
    await Promise.all([first, second])
    expect(apiClient.call).toHaveBeenCalledTimes(1)
    expect(graph.entities.value.map((e) => e.id)).toEqual(['a', 'b'])
    expect(graph.isLoadingMore.value).toBe(false)
  })

  describe('a refresh while a next page is in flight', () => {
    const seed = () =>
      vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
        if (url.includes('/memory/entities/all')) return { data: { entities: [] } } as never
        return page(['a'], '500:0') as never
      })
    const deferred = () => {
      const settle: { resolve: (v: unknown) => void; reject: (e: unknown) => void } = {
        resolve: () => undefined,
        reject: () => undefined,
      }
      vi.mocked(apiClient.call).mockImplementationOnce((() =>
        new Promise((resolve, reject) => { settle.resolve = resolve; settle.reject = reject })) as never)
      return settle
    }

    it('starts its own request for a call made after the refresh and drops the stale page', async () => {
      seed()
      const stale = deferred()
      const graph = useKnowledgeGraphEntities()
      await graph.fetchGraphData()
      const old = graph.loadMoreFacts()
      await graph.fetchGraphData()
      expect(graph.isLoadingMore.value).toBe(false)
      vi.mocked(apiClient.call).mockResolvedValueOnce(page(['fresh'], null) as never)
      await graph.loadMoreFacts()
      expect(apiClient.call).toHaveBeenCalledTimes(2)
      expect(graph.entities.value.map((e) => e.id)).toEqual(['a', 'fresh'])
      stale.resolve(page(['stale'], null))
      await old
      expect(graph.entities.value.map((e) => e.id)).toEqual(['a', 'fresh'])
      expect(graph.hasMoreFacts.value).toBe(false)
    })

    it('does not let the stale read set the error or the loading flag after the refresh', async () => {
      seed()
      const stale = deferred()
      const graph = useKnowledgeGraphEntities()
      await graph.fetchGraphData()
      const old = graph.loadMoreFacts()
      await graph.fetchGraphData()
      stale.reject(new Error('old failure'))
      await old
      expect(graph.errorMessage.value).toBe('')
      expect(graph.isLoadingMore.value).toBe(false)
    })
  })
})
