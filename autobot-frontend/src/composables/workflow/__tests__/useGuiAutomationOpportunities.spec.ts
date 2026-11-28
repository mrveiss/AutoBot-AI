// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// A failed refresh must not look like "no opportunities", and a refresh in flight when the company
// changes must not repopulate the list afterwards (#21520).

import { describe, it, expect, vi, beforeEach } from 'vitest'

const getAutomationOpportunities = vi.fn()
vi.mock('@/composables/useVisionApi', () => ({ getAutomationOpportunities: (...a: unknown[]) => getAutomationOpportunities(...a) }))
vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ warn: vi.fn(), error: vi.fn(), debug: vi.fn(), info: vi.fn() }) }))

import { useGuiAutomationOpportunities } from '../useGuiAutomationOpportunities'

describe('useGuiAutomationOpportunities', () => {
  beforeEach(() => getAutomationOpportunities.mockReset())

  it('loads the opportunities', async () => {
    getAutomationOpportunities.mockResolvedValue({ opportunities: [{ id: 'o1' }] })
    const g = useGuiAutomationOpportunities()
    await g.load()
    expect(g.opportunities.value).toHaveLength(1)
    expect(g.loadFailed.value).toBe(false)
    expect(g.loading.value).toBe(false)
  })

  it('flags a failed refresh, and clears the flag on the next attempt', async () => {
    getAutomationOpportunities.mockRejectedValueOnce(new Error('503'))
    const g = useGuiAutomationOpportunities()
    await g.load()
    expect(g.loadFailed.value).toBe(true)
    expect(g.opportunities.value).toEqual([])
    getAutomationOpportunities.mockResolvedValueOnce({ opportunities: [] })
    await g.load()
    expect(g.loadFailed.value).toBe(false)
  })

  it('reset() revokes a refresh in flight: its late reply neither fills the list nor sets loading', async () => {
    let release!: (v: unknown) => void
    getAutomationOpportunities.mockReturnValueOnce(new Promise((res) => { release = res }))
    const g = useGuiAutomationOpportunities()
    const pending = g.load()
    expect(g.loading.value).toBe(true)
    g.reset() // company switch
    expect(g.loading.value).toBe(false)
    release({ opportunities: [{ id: 'previous-company' }] })
    await pending
    expect(g.opportunities.value).toEqual([])
    expect(g.loading.value).toBe(false)
  })

  it('a revoked refresh that fails does not flag the new company as failed', async () => {
    let fail!: (e: unknown) => void
    getAutomationOpportunities.mockReturnValueOnce(new Promise((_, rej) => { fail = rej }))
    const g = useGuiAutomationOpportunities()
    const pending = g.load()
    g.reset()
    fail(new Error('late'))
    await pending
    expect(g.loadFailed.value).toBe(false)
  })
})
