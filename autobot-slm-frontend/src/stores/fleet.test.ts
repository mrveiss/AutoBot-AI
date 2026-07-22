// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #11964 — node-card "code update available" badge vs. the
 * NodeLifecyclePanel "Check for updates" live scan disagreeing.
 *
 * Root cause: the badge (fleetUpdateSummary, fetched once on page load) and
 * the live per-node scan read different/stale data. These tests prove that
 * checkNodeUpdates() -- the store action backing the live scan -- reconciles
 * the cached fleetUpdateSummary entry with the fresh result, so the badge
 * can never keep showing "code update available" once a live check finds
 * none.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useFleetStore } from './fleet'

const mockGetFleetUpdateSummary = vi.fn()
const mockCheckUpdates = vi.fn()

vi.mock('@/composables/useSlmApi', () => ({
  useSlmApi: () => ({
    getFleetUpdateSummary: mockGetFleetUpdateSummary,
    checkUpdates: mockCheckUpdates,
  }),
}))

describe('fleetStore — badge/live-check reconciliation (#11964)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGetFleetUpdateSummary.mockReset()
    mockCheckUpdates.mockReset()
  })

  it('clears a stale code_update_available badge once the live scan finds nothing', async () => {
    // Badge fetched at page load: node flagged as needing a code update.
    mockGetFleetUpdateSummary.mockResolvedValue({
      nodes: [
        {
          node_id: 'node-1',
          hostname: 'host-1',
          system_updates: 0,
          code_update_available: true,
          code_status: 'outdated',
          total_updates: 1,
        },
      ],
      total_system_updates: 0,
      total_code_updates: 1,
      nodes_needing_updates: 1,
    })

    const fleetStore = useFleetStore()
    await fleetStore.fetchFleetUpdateSummary()
    expect(fleetStore.getNodeUpdateSummary('node-1')?.code_update_available).toBe(true)

    // Live scan (NodeLifecyclePanel "Check for updates") re-reads node.code_status
    // fresh and finds it's actually up to date now.
    mockCheckUpdates.mockResolvedValue({
      updates: [],
      total: 0,
      code_update_available: false,
      code_status: 'up_to_date',
    })

    await fleetStore.checkNodeUpdates('node-1')

    const reconciled = fleetStore.getNodeUpdateSummary('node-1')
    expect(reconciled?.code_update_available).toBe(false)
    expect(reconciled?.code_status).toBe('up_to_date')
    expect(reconciled?.total_updates).toBe(0)
    expect(fleetStore.fleetUpdateSummary?.total_code_updates).toBe(0)
    expect(fleetStore.fleetUpdateSummary?.nodes_needing_updates).toBe(0)
  })

  it('keeps the badge in sync when the live scan confirms a code update is still pending', async () => {
    mockGetFleetUpdateSummary.mockResolvedValue({
      nodes: [
        {
          node_id: 'node-2',
          hostname: 'host-2',
          system_updates: 0,
          code_update_available: true,
          code_status: 'outdated',
          total_updates: 1,
        },
      ],
      total_system_updates: 0,
      total_code_updates: 1,
      nodes_needing_updates: 1,
    })

    const fleetStore = useFleetStore()
    await fleetStore.fetchFleetUpdateSummary()

    mockCheckUpdates.mockResolvedValue({
      updates: [],
      total: 0,
      code_update_available: true,
      code_status: 'outdated',
    })

    const result = await fleetStore.checkNodeUpdates('node-2')

    expect(result.code_update_available).toBe(true)
    expect(fleetStore.getNodeUpdateSummary('node-2')?.code_update_available).toBe(true)
  })
})
