// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #11964, ported with the store (#19834): the node-card "code update available" badge vs the
 * "Check for updates" live scan. `checkNodeUpdates()` reconciles the cached fleetUpdateSummary
 * entry with the fresh result, so the badge cannot keep showing an update a live check found none of.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const api = vi.hoisted(() => ({ getFleetUpdateSummary: vi.fn(), checkUpdates: vi.fn() }))
vi.mock('@/utils/slmApi', () => ({ slmApi: api }))

import { useFleetStore } from '../index'

function summaryFor(nodeId: string) {
  return {
    nodes: [
      {
        node_id: nodeId,
        hostname: `host-${nodeId}`,
        system_updates: 0,
        code_update_available: true,
        code_status: 'outdated',
        total_updates: 1,
      },
    ],
    total_system_updates: 0,
    total_code_updates: 1,
    nodes_needing_updates: 1,
  }
}

describe('fleet store: badge/live-check reconciliation (#11964)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.getFleetUpdateSummary.mockReset()
    api.checkUpdates.mockReset()
  })

  it('clears a stale code_update_available badge once the live scan finds nothing', async () => {
    api.getFleetUpdateSummary.mockResolvedValue(summaryFor('node-1'))
    const store = useFleetStore()
    await store.fetchFleetUpdateSummary()
    expect(store.getNodeUpdateSummary('node-1')?.code_update_available).toBe(true)

    api.checkUpdates.mockResolvedValue({ updates: [], total: 0, code_update_available: false, code_status: 'up_to_date' })
    await store.checkNodeUpdates('node-1')

    const reconciled = store.getNodeUpdateSummary('node-1')
    expect(reconciled?.code_update_available).toBe(false)
    expect(reconciled?.code_status).toBe('up_to_date')
    expect(reconciled?.total_updates).toBe(0)
    expect(store.fleetUpdateSummary?.total_code_updates).toBe(0)
    expect(store.fleetUpdateSummary?.nodes_needing_updates).toBe(0)
  })

  it('keeps the badge in sync when the live scan confirms a code update is still pending', async () => {
    api.getFleetUpdateSummary.mockResolvedValue(summaryFor('node-2'))
    const store = useFleetStore()
    await store.fetchFleetUpdateSummary()

    api.checkUpdates.mockResolvedValue({ updates: [], total: 0, code_update_available: true, code_status: 'outdated' })
    const result = await store.checkNodeUpdates('node-2')

    expect(result.code_update_available).toBe(true)
    expect(store.getNodeUpdateSummary('node-2')?.code_update_available).toBe(true)
  })

  it('leaves the summary null when the summary read fails (supplementary info)', async () => {
    api.getFleetUpdateSummary.mockRejectedValue(new Error('down'))
    const store = useFleetStore()
    await store.fetchFleetUpdateSummary()
    expect(store.fleetUpdateSummary).toBeNull()
    expect(store.nodesNeedingUpdates).toBe(0)
  })
})
