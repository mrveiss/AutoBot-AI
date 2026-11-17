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
    expect(store.incomplete).toEqual({ read: 2, total: 5 })
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
})
