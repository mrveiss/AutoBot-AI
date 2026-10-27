// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19217: the SLM web research composable talks to the MAIN backend's seven
 * /web-research routes through an axios client that carries the SLM session token.
 * The harness stubs `axios.create` and runs the registered request interceptor, so
 * the token header and the exact routes and bodies are asserted, not just "a call".
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

type RequestConfig = { headers: Record<string, unknown> }

const h = vi.hoisted(() => {
  const state = {
    createConfig: null as Record<string, unknown> | null,
    requestInterceptor: null as ((c: RequestConfig) => RequestConfig) | null,
    token: null as string | null,
  }
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    interceptors: {
      request: {
        use: (fn: (c: RequestConfig) => RequestConfig) => {
          state.requestInterceptor = fn
        },
      },
    },
  }
  return { state, instance }
})

vi.mock('axios', () => ({
  default: {
    create: (config: Record<string, unknown>) => {
      h.state.createConfig = config
      return h.instance
    },
  },
}))
vi.mock('@/config/ssot-config', () => ({ getBackendUrl: () => '/autobot-api' }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    get token() {
      return h.state.token
    },
  }),
}))

import {
  useWebResearchAdminApi,
  isSavedNotApplied,
  isWebResearcherUnavailable,
} from './useWebResearchAdminApi'

describe('useWebResearchAdminApi (#19217)', () => {
  beforeEach(() => {
    h.state.token = null
    h.instance.get.mockReset()
    h.instance.post.mockReset()
    h.instance.put.mockReset()
  })

  it('targets the main backend and attaches the SLM session token', () => {
    h.state.token = 'slm-token'
    useWebResearchAdminApi()
    expect(h.state.createConfig).toMatchObject({ baseURL: '/autobot-api' })
    const config = h.state.requestInterceptor!({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer slm-token')
  })

  it('sends no Authorization header without a token', () => {
    useWebResearchAdminApi()
    expect(h.state.requestInterceptor!({ headers: {} }).headers.Authorization).toBeUndefined()
  })

  it('getSettings GETs /web-research/settings and returns the settings object', async () => {
    const settings = { enabled: true, max_results: 5 }
    h.instance.get.mockResolvedValue({ data: { status: 'success', settings } })
    expect(await useWebResearchAdminApi().getSettings()).toEqual(settings)
    expect(h.instance.get).toHaveBeenCalledWith('/web-research/settings')
  })

  it('updateSettings PUTs exactly the changes it is given', async () => {
    const body = { status: 'success', message: 'ok', settings: {} }
    h.instance.put.mockResolvedValue({ data: body })
    const result = await useWebResearchAdminApi().updateSettings({ max_results: 9 })
    expect(h.instance.put).toHaveBeenCalledWith('/web-research/settings', { max_results: 9 })
    expect(result).toEqual(body)
  })

  it('enable and disable POST their routes', async () => {
    h.instance.post.mockResolvedValue({ data: { status: 'success', enabled: true } })
    const api = useWebResearchAdminApi()
    await api.enable()
    await api.disable()
    expect(h.instance.post).toHaveBeenNthCalledWith(1, '/web-research/enable')
    expect(h.instance.post).toHaveBeenNthCalledWith(2, '/web-research/disable')
  })

  it('getStatus GETs /web-research/status', async () => {
    h.instance.get.mockResolvedValue({ data: { status: 'success', enabled: true } })
    await useWebResearchAdminApi().getStatus()
    expect(h.instance.get).toHaveBeenCalledWith('/web-research/status')
  })

  it('clearCache and resetCircuitBreakers POST their routes', async () => {
    h.instance.post.mockResolvedValue({ data: { status: 'success', message: 'done' } })
    const api = useWebResearchAdminApi()
    await api.clearCache()
    await api.resetCircuitBreakers()
    expect(h.instance.post).toHaveBeenNthCalledWith(1, '/web-research/clear-cache')
    expect(h.instance.post).toHaveBeenNthCalledWith(2, '/web-research/reset-circuit-breakers')
  })

  it('classifies saved_not_applied and a 503', () => {
    expect(isSavedNotApplied({ status: 'saved_not_applied' })).toBe(true)
    expect(isSavedNotApplied({ status: 'success' })).toBe(false)
    expect(isWebResearcherUnavailable({ response: { status: 503 } })).toBe(true)
    expect(isWebResearcherUnavailable({ response: { status: 500 } })).toBe(false)
    expect(isWebResearcherUnavailable(new Error('x'))).toBe(false)
  })
})
