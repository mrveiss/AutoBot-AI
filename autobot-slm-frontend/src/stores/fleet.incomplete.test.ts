// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21584: fetchNodes keeps what a partial read returned and records it in `incomplete`, without
// failing the nine callers; a complete read clears it; a read that returned nothing still throws.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { PartialListError } from '@/utils/fetchAllPages'

const getNodes = vi.fn()
vi.mock('@/composables/useSlmApi', () => ({ useSlmApi: () => ({ getNodes }) }))

import { useFleetStore } from './fleet'

const node = (i: number) => ({ node_id: `n${i}`, hostname: `h${i}` })

describe('fleet store incomplete node list (#21584)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getNodes.mockReset()
  })

  it('a partial read keeps the nodes read, records the shortfall and does not throw', async () => {
    getNodes.mockRejectedValue(new PartialListError([node(1), node(2)], 5, new Error('504')))
    const store = useFleetStore()

    await expect(store.fetchNodes()).resolves.toBeUndefined()

    expect(store.nodeList.map((n) => n.node_id)).toEqual(['n1', 'n2'])
    expect(store.incomplete).toEqual({ read: 2, total: 5, reason: '504' })
    expect(store.error).toBeNull() // usable data beside a failure banner would contradict itself
    expect(store.isLoading).toBe(false)
  })

  it('a complete read afterwards clears the shortfall', async () => {
    const store = useFleetStore()
    getNodes.mockRejectedValueOnce(new PartialListError([node(1)], 2, new Error('504')))
    await store.fetchNodes()
    getNodes.mockResolvedValueOnce([node(1), node(2)])
    await store.fetchNodes()

    expect(store.incomplete).toBeNull()
    expect(store.nodeList).toHaveLength(2)
  })

  it('a read that returned nothing still throws and leaves no shortfall recorded', async () => {
    getNodes.mockRejectedValue(new Error('network down'))
    const store = useFleetStore()

    await expect(store.fetchNodes()).rejects.toThrow('network down')
    expect(store.incomplete).toBeNull()
  })

  it('an outright failure after a partial read keeps the shortfall record with the nodes it kept', async () => {
    const store = useFleetStore()
    getNodes.mockRejectedValueOnce(new PartialListError([node(1)], 3, new Error('504')))
    await store.fetchNodes()
    getNodes.mockRejectedValueOnce(new Error('network down'))
    await expect(store.fetchNodes()).rejects.toThrow('network down')

    expect(store.incomplete).toEqual({ read: 1, total: 3, reason: '504' })
    expect(store.nodeList).toHaveLength(1)
  })

  it('a non-Error rejection reports the translated fallback, not a literal', async () => {
    getNodes.mockRejectedValue('boom')
    const store = useFleetStore()
    await expect(store.fetchNodes()).rejects.toBe('boom')
    expect(store.nodesError).toBe('Could not load the node list')
  })

  it('overlapping reads: the newest decides, an older failure leaves no stale error', async () => {
    const store = useFleetStore()
    let rejectFirst!: (e: Error) => void
    getNodes.mockReturnValueOnce(new Promise((_, rej) => { rejectFirst = rej }))
    getNodes.mockResolvedValueOnce([])
    const first = store.fetchNodes()
    await store.fetchNodes()
    rejectFirst(new Error('late failure'))
    await expect(first).resolves.toBeUndefined()

    expect(store.nodesError).toBeNull()
    expect(store.error).toBeNull()
    expect(store.isLoading).toBe(false)
  })

  it('$reset clears nodesError', async () => {
    getNodes.mockRejectedValue(new Error('down'))
    const store = useFleetStore()
    await expect(store.fetchNodes()).rejects.toThrow()
    store.$reset()
    expect(store.nodesError).toBeNull()
  })
})
