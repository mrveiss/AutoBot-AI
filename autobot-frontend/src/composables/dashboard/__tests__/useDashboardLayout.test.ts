// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * A failed load must never let the defaults overwrite the user's saved layout (#18896 review):
 * with no successful GET, save and reset write nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { DashboardLayout } from '../dashboardLayoutModel'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: api }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ error: vi.fn(), warn: vi.fn() }) }))

const { useDashboardLayout } = await import('../useDashboardLayout')

const DEFAULTS = (): DashboardLayout => ({
  dashboards: [{ id: 'default', name: 'n', widgets: [], createdAt: 0, updatedAt: 0 }],
  activeId: 'default',
})
const STORED: DashboardLayout = {
  dashboards: [{ id: 'mine', name: 'Mine', widgets: [], createdAt: 1, updatedAt: 1 }],
  activeId: 'mine',
}

describe('useDashboardLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('after a failed GET, save and reset send nothing and the error is exposed', async () => {
    api.get.mockRejectedValueOnce(new Error('503'))
    const d = useDashboardLayout('home', DEFAULTS)
    await d.load()
    expect(d.loaded.value).toBe(false)
    expect(d.loadError.value).toBe('503')
    expect(await d.save(DEFAULTS())).toBe(false)
    expect(await d.reset()).toBe(false)
    expect(api.put).not.toHaveBeenCalled()
    expect(api.delete).not.toHaveBeenCalled()
  })

  it('after a successful GET, the stored layout loads and save writes it', async () => {
    // contrast: fails if the guard also blocks the normal path
    api.get.mockResolvedValueOnce({ success: true, data: { page: 'home', layout: STORED } })
    api.put.mockResolvedValueOnce({})
    const d = useDashboardLayout('home', DEFAULTS)
    await d.load()
    expect(d.loaded.value).toBe(true)
    expect(d.layout.value.activeId).toBe('mine')
    expect(await d.save(STORED)).toBe(true)
    expect(api.put).toHaveBeenCalledOnce()
  })

  it('a retry after a failed GET clears the error and enables saving', async () => {
    api.get.mockRejectedValueOnce(new Error('503')).mockResolvedValueOnce({ data: { layout: STORED } })
    const d = useDashboardLayout('home', DEFAULTS)
    await d.load()
    await d.load()
    expect(d.loadError.value).toBeNull()
    expect(d.loaded.value).toBe(true)
  })

  it('migrates legacy localStorage dashboards and clears the key only after the PUT succeeds', async () => {
    localStorage.setItem('autobot_dashboards', JSON.stringify([{ id: 'default', name: 'Old', widgets: [] }]))
    api.get.mockResolvedValueOnce({ data: { layout: { dashboards: [] } } })
    api.put.mockRejectedValueOnce(new Error('500'))
    const d = useDashboardLayout('home', DEFAULTS)
    await d.load()
    expect(localStorage.getItem('autobot_dashboards')).not.toBeNull()
    expect(d.layout.value.dashboards[0].name).toBe('Old')
  })

  it('a successful reset clears a legacy key a failed migration left behind', async () => {
    // fails if Reset deletes the server layout but the next load restores the legacy one
    localStorage.setItem('autobot_dashboards', JSON.stringify([{ id: 'old', name: 'Old', widgets: [] }]))
    api.get.mockResolvedValueOnce({ data: { layout: STORED } })
    api.delete.mockResolvedValueOnce({})
    const d = useDashboardLayout('home', DEFAULTS)
    await d.load()
    expect(await d.reset()).toBe(true)
    expect(localStorage.getItem('autobot_dashboards')).toBeNull()
  })

  it('storage that throws reads as no legacy layout, not as a failed load', async () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    api.get.mockResolvedValueOnce({ data: { layout: { dashboards: [] } } })
    const d = useDashboardLayout('home', DEFAULTS)
    await d.load()
    expect(d.loaded.value).toBe(true)
    expect(d.loadError.value).toBeNull()
    spy.mockRestore()
  })
})
