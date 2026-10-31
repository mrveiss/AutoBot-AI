// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19217: the SLM web research composable talks to the MAIN backend's seven
 * /web-research routes through the SLM's `SlmApiClient` pointed at it (#12363). The
 * client's token and 401 handling are tested in `utils/ApiClient.test.ts`; this pins
 * the base URL and the exact routes and bodies, not just "a call".
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { HttpError } from '@autobot/ui'
import { backendClient } from '@/testing/mockAutobotBackendClient'

vi.mock('@/utils/ApiClient', async (importOriginal) =>
  (await import('@/testing/mockAutobotBackendClient')).withMockedBackendClient(importOriginal),
)
vi.mock('@/config/ssot-config', () => ({
  getBackendUrl: () => '/autobot-api',
  getEnvPositiveInt: (_key: string, fallback: number) => fallback,
}))

import {
  useWebResearchAdminApi,
  isSavedNotApplied,
  isWebResearcherUnavailable,
} from './useWebResearchAdminApi'

describe('useWebResearchAdminApi (#19217)', () => {
  beforeEach(() => {
    backendClient.get.mockReset()
    backendClient.post.mockReset()
    backendClient.put.mockReset()
  })

  it('targets the main backend', () => {
    useWebResearchAdminApi()
    expect(backendClient.baseUrl).toBe('/autobot-api')
  })

  it('getSettings GETs /web-research/settings and returns the settings object', async () => {
    const settings = { enabled: true, max_results: 5 }
    backendClient.get.mockResolvedValue({ status: 'success', settings })
    expect(await useWebResearchAdminApi().getSettings()).toEqual(settings)
    expect(backendClient.get).toHaveBeenCalledWith('/web-research/settings')
  })

  it('updateSettings PUTs exactly the changes it is given', async () => {
    const body = { status: 'success', message: 'ok', settings: {} }
    backendClient.put.mockResolvedValue(body)
    const result = await useWebResearchAdminApi().updateSettings({ max_results: 9 })
    expect(backendClient.put).toHaveBeenCalledWith('/web-research/settings', { max_results: 9 })
    expect(result).toEqual(body)
  })

  it('enable and disable POST their routes', async () => {
    backendClient.post.mockResolvedValue({ status: 'success', enabled: true })
    const api = useWebResearchAdminApi()
    await api.enable()
    await api.disable()
    expect(backendClient.post).toHaveBeenNthCalledWith(1, '/web-research/enable')
    expect(backendClient.post).toHaveBeenNthCalledWith(2, '/web-research/disable')
  })

  it('getStatus GETs /web-research/status', async () => {
    backendClient.get.mockResolvedValue({ status: 'success', enabled: true })
    await useWebResearchAdminApi().getStatus()
    expect(backendClient.get).toHaveBeenCalledWith('/web-research/status', { maxRetries: 1 })
  })

  it('clearCache and resetCircuitBreakers POST their routes', async () => {
    backendClient.post.mockResolvedValue({ status: 'success', message: 'done' })
    const api = useWebResearchAdminApi()
    await api.clearCache()
    await api.resetCircuitBreakers()
    expect(backendClient.post).toHaveBeenNthCalledWith(1, '/web-research/clear-cache')
    expect(backendClient.post).toHaveBeenNthCalledWith(2, '/web-research/reset-circuit-breakers')
  })

  it('classifies saved_not_applied and a 503', () => {
    expect(isSavedNotApplied({ status: 'saved_not_applied' })).toBe(true)
    expect(isSavedNotApplied({ status: 'success' })).toBe(false)
    expect(isWebResearcherUnavailable(new HttpError(503, 'Service Unavailable'))).toBe(true)
    expect(isWebResearcherUnavailable(new HttpError(500, 'Internal Server Error'))).toBe(false)
    expect(isWebResearcherUnavailable(new Error('x'))).toBe(false)
  })
})
