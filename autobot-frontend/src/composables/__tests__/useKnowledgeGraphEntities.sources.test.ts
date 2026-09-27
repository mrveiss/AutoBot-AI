// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useKnowledgeGraphEntities source outcomes — Issue #17612.
 *
 * The graph is assembled from two independent stores, and an empty canvas had
 * one explanation on screen for three different causes: both stores read and
 * holding nothing, one store unreadable, both unreadable. The view asked only
 * `entities.length === 0`, so all three rendered "No Entities Found" with an
 * invitation to create an entity — a claim about the data made on the strength
 * of a failed request. The failure notification is a `useTransientError(5000)`
 * toast, so after five seconds the false version was the only thing left.
 *
 * Each cause is asserted separately here; collapsing any two of them is the
 * defect. `Promise.all` was also discarding a healthy store's entities when the
 * other failed, so the partial case is pinned too.
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

const UNIFIED = '/api/knowledge_base/multi-source/graph'
const MEMORY = '/api/memory/entities/all'

interface StoreScript {
  unified?: unknown | Error
  memory?: unknown | Error
}

/** Route each store's GET to its scripted answer; an Error is a rejection. */
function script({ unified, memory }: StoreScript): void {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    const answer = url.startsWith(UNIFIED) ? unified : url === MEMORY ? memory : { data: { relations: [] } }
    if (answer instanceof Error) throw answer
    return answer as never
  })
}

const entity = (id: string) => ({ id, name: id, type: 'concept', observations: [] })

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset()
})

describe('useKnowledgeGraphEntities source outcomes (#17612)', () => {
  it('reports both stores read and holding nothing', async () => {
    script({ unified: { data: { entities: [], relations: [] } }, memory: { data: { entities: [] } } })
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()

    expect(graph.entities.value).toHaveLength(0)
    // Every store ok is what makes "the graph is empty" a true statement.
    expect(graph.sources.value.every((source) => source.ok)).toBe(true)
    expect(graph.sources.value.map((source) => source.count)).toEqual([0, 0])
  })

  it('does not report an empty graph when no store could be read', async () => {
    script({ unified: new Error('unified down'), memory: new Error('memory down') })
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()

    // Same `entities.length` as the case above, opposite meaning. This is the
    // pair the old code could not tell apart.
    expect(graph.entities.value).toHaveLength(0)
    expect(graph.sources.value.some((source) => source.ok)).toBe(false)
    expect(graph.sources.value.map((source) => source.error)).toEqual(['unified down', 'memory down'])
  })

  it('keeps a healthy store’s entities when the other one fails', async () => {
    script({ unified: new Error('unified down'), memory: { data: { entities: [entity('a'), entity('b')] } } })
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()

    // `Promise.all` threw these two away because the other store rejected.
    expect(graph.entities.value.map((e) => e.id)).toEqual(['a', 'b'])
    expect(graph.sources.value.find((source) => source.key === 'memory')).toMatchObject({ ok: true, count: 2 })
    expect(graph.sources.value.find((source) => source.key === 'unified')).toMatchObject({ ok: false })
  })

  it('reports no reason rather than a reason-shaped non-reason', async () => {
    script({ unified: { data: { entities: [] } }, memory: new Error('') })
    const graph = useKnowledgeGraphEntities()
    await graph.fetchGraphData()

    // '' is the contract, and the view turns it into translated words. The
    // first implementation fell through to `String(error)`, which for an Error
    // with no message is the literal "Error" -- it fills the slot and says
    // nothing, which is worse than an admitted gap.
    expect(graph.sources.value.find((source) => source.key === 'memory')?.error).toBe('')
  })

  it('does not reject when a store fails', async () => {
    script({ unified: new Error('unified down'), memory: new Error('memory down') })
    const graph = useKnowledgeGraphEntities()

    // The old rejection reached `onMounted` unhandled and aborted the caller's
    // Cytoscape initialisation, so a failed load also left the canvas dead.
    await expect(graph.fetchGraphData()).resolves.toBeUndefined()
    expect(graph.isLoading.value).toBe(false)
  })
})
