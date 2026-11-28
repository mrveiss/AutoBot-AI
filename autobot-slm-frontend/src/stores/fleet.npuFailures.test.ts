// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19068: a rejected NPU read is a failure the caller sees, never `null` data that renders
 * as "this node has no config or metrics". The store also keeps the message in `error`.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useFleetStore } from './fleet'

const api = vi.hoisted(() => ({
  getNpuStatus: vi.fn(),
  getNpuLoadBalancing: vi.fn(),
  getNpuFleetMetrics: vi.fn(),
  getNpuNodeMetrics: vi.fn(),
  getNpuWorkerConfig: vi.fn(),
}))

vi.mock('@/composables/useSlmApi', () => ({ useSlmApi: () => api }))

describe('fleet store NPU reads report failure (#19068)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.values(api).forEach((m) => m.mockReset())
  })

  const cases = [
    ['fetchNpuStatus', 'getNpuStatus', ['n1']],
    ['fetchNpuLoadBalancing', 'getNpuLoadBalancing', []],
    ['fetchNpuFleetMetrics', 'getNpuFleetMetrics', []],
    ['fetchNpuNodeMetrics', 'getNpuNodeMetrics', ['n1']],
    ['fetchNpuWorkerConfig', 'getNpuWorkerConfig', ['n1']],
  ] as const

  it.each(cases)('%s rejects and records the error when the API call fails', async (action, apiFn, args) => {
    api[apiFn].mockRejectedValue(new Error('backend down'))
    const store = useFleetStore()
    const run = (store[action] as (...a: string[]) => Promise<unknown>)(...args)
    await expect(run).rejects.toThrow('backend down')
    expect(store.error).toBe('backend down')
  })

  it.each(cases)('%s keeps a non-Error rejection as text, with no invented message', async (action, apiFn, args) => {
    api[apiFn].mockRejectedValue('gateway timeout')
    const store = useFleetStore()
    await expect((store[action] as (...a: string[]) => Promise<unknown>)(...args)).rejects.toBe('gateway timeout')
    expect(store.error).toBe('gateway timeout')
  })

  it('returns the data on success', async () => {
    api.getNpuWorkerConfig.mockResolvedValue({ priority: 3 })
    expect(await useFleetStore().fetchNpuWorkerConfig('n1')).toEqual({ priority: 3 })
  })
})
