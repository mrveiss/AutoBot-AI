// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useHostInventory tests (#12614)
 *
 * Verifies the composable routes SLM /api/nodes calls through the canonical
 * SLM bridge (slmClient) — not raw getSLMUrl()+fetch — and preserves its
 * graceful-error behaviour (error string set, empty/null return, state intact).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

const getMock = vi.fn()
const postMock = vi.fn()

vi.mock('@/utils/slmClient', () => ({
  slmClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}))

import { useHostInventory } from '../useHostInventory'

describe('useHostInventory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchHosts GETs /api/nodes with pagination via slmClient', async () => {
    getMock.mockResolvedValue({ nodes: [{ node_id: 'n1' }], total: 1, page: 1, per_page: 50 })
    const { hosts, total, fetchHosts, error } = useHostInventory()

    await fetchHosts(2, 25)

    expect(getMock).toHaveBeenCalledWith('/api/nodes?page=2&per_page=25')
    expect(hosts.value).toEqual([{ node_id: 'n1' }])
    expect(total.value).toBe(1)
    expect(error.value).toBeNull()
  })

  it('addHost POSTs to /api/nodes then refreshes the list', async () => {
    postMock.mockResolvedValue({ node_id: 'new' })
    getMock.mockResolvedValue({ nodes: [], total: 0, page: 1, per_page: 50 })
    const { addHost } = useHostInventory()

    const created = await addHost({ hostname: 'h', ip_address: '10.0.0.1' })

    expect(postMock).toHaveBeenCalledWith('/api/nodes', { hostname: 'h', ip_address: '10.0.0.1' })
    expect(getMock).toHaveBeenCalledWith('/api/nodes?page=1&per_page=50')
    expect(created).toEqual({ node_id: 'new' })
  })

  it('provisionRole POSTs role payload to the provision endpoint', async () => {
    postMock.mockResolvedValue({ job_id: 'job-9' })
    const { provisionRole } = useHostInventory()

    const jobId = await provisionRole('n1', 'ollama')

    expect(postMock).toHaveBeenCalledWith('/api/nodes/n1/provision', { roles: ['ollama'] })
    expect(jobId).toBe('job-9')
  })

  it('sets error and leaves state intact when slmClient rejects', async () => {
    getMock.mockRejectedValue(new Error('SLM 503: down'))
    const { hosts, fetchHosts, error } = useHostInventory()

    await fetchHosts()

    expect(error.value).toBe('SLM 503: down')
    expect(hosts.value).toEqual([])
  })
})
