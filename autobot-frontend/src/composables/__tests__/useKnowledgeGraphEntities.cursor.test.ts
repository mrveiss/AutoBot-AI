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
})
