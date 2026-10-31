// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * `slmApi` (#19834, ADR 011 section 4): base path, the one session token, the 401 and 503
 * policies, and the typed seams. The transport is the real main-app `ApiClient`; only `fetch`,
 * the stored token and the user store are faked.
 */
import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from 'vitest'

const { clearStoredAuth, logout } = vi.hoisted(() => ({ clearStoredAuth: vi.fn(), logout: vi.fn() }))

vi.mock('@/stores/useUserStore', () => ({ useUserStore: () => ({ logout }) }))
vi.mock('@/utils/authToken', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/authToken')>()),
  readStoredAuthToken: () => 'main-session-jwt',
  clearStoredAuth,
}))

import { slmApi, slmClient, slmUrl, slmWsUrl } from '../index'

const origin = window.location.origin

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit]
  return { url, init }
}

const wireNode = {
  id: 1,
  node_id: 'n1',
  hostname: 'h1',
  ip_address: '10.0.0.1',
  status: 'online',
  roles: ['redis'],
  cpu_percent: 1,
  memory_percent: 2,
  disk_percent: 3,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  auth_method: 'key',
}

describe('slmApi (#19834)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeAll(() => {
    slmClient() // built against the real origin, before any test replaces `window.location`
  })

  beforeEach(() => {
    clearStoredAuth.mockClear()
    logout.mockClear()
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  describe('base path', () => {
    it('serves the contract path /api/nodes at /slm/api/nodes on the page origin', async () => {
      fetchMock.mockResolvedValue(json({ nodes: [wireNode], total: 1, page: 1, per_page: 50 }))
      const nodes = await slmApi.getNodes()

      expect(lastCall(fetchMock).url).toBe(`${origin}/slm/api/nodes`)
      expect(nodes[0]).toMatchObject({ node_id: 'n1', health: { status: 'healthy', cpu_percent: 1 }, detected_roles: [] })
    })

    it('does not use the main backend base: the client is the page origin, not appConfig.getApiUrl', () => {
      expect(slmClient().getConfiguration().baseUrl).toBe(origin)
      expect(slmUrl('/api/nodes/{node_id}/events', { node_id: 'a' })).toBe('/slm/api/nodes/a/events')
    })

    it('URL-encodes every path parameter', async () => {
      fetchMock.mockResolvedValue(json(wireNode))
      await slmApi.getNode('a/b c')
      expect(lastCall(fetchMock).url).toBe(`${origin}/slm/api/nodes/a%2Fb%20c`)
    })

    it('sends query values that are set and drops those that are not', async () => {
      fetchMock.mockResolvedValue(json({ events: [], total: 0 }))
      await slmApi.getNodeEvents('n1', { limit: 5, severity: 'error' })
      const { url } = lastCall(fetchMock)
      expect(url).toContain(`${origin}/slm/api/nodes/n1/events?`)
      expect(url).toContain('limit=5')
      expect(url).toContain('severity=error')
      expect(url).not.toContain('type=')
      expect(url).not.toContain('offset=')
    })

    it('builds the provision WebSocket on the page origin under /slm/api', () => {
      expect(slmWsUrl('/ws/provision')).toBe(`${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/slm/api/ws/provision`)
    })
  })

  describe('auth header', () => {
    it('sends the main-app session token, never slm_access_token', async () => {
      sessionStorage.setItem('slm_access_token', 'slm-hs256-token')
      localStorage.setItem('slm_access_token', 'slm-hs256-token')
      try {
        fetchMock.mockResolvedValue(json({ nodes: [], total: 0, page: 1, per_page: 50 }))
        await slmApi.getNodes()
        const headers = lastCall(fetchMock).init.headers as Record<string, string>
        expect(headers.Authorization).toBe('Bearer main-session-jwt')
        expect(JSON.stringify(headers)).not.toContain('slm-hs256-token')
      } finally {
        sessionStorage.removeItem('slm_access_token')
        localStorage.removeItem('slm_access_token')
      }
    })

    it('sends a JSON body with the method the contract declares', async () => {
      fetchMock.mockResolvedValue(json({ ...wireNode, roles: ['redis', 'postgres'] }))
      const node = await slmApi.updateNodeRoles('n1', ['redis', 'postgres'])
      const { url, init } = lastCall(fetchMock)
      expect(init.method).toBe('PATCH')
      expect(url).toBe(`${origin}/slm/api/nodes/n1/roles`)
      expect(JSON.parse(init.body as string)).toEqual({ roles: ['redis', 'postgres'] })
      expect(node.roles).toEqual(['redis', 'postgres'])
    })
  })

  describe('401 ends the one session (ADR 011 section 4)', () => {
    let originalLocation: Location

    beforeEach(() => {
      originalLocation = window.location
      Object.defineProperty(window, 'location', {
        configurable: true,
        writable: true,
        value: { pathname: '/admin/fleet', href: '', port: '', origin, host: 'localhost', protocol: 'http:' } as unknown as Location,
      })
    })

    afterEach(() => {
      Object.defineProperty(window, 'location', { configurable: true, writable: true, value: originalLocation })
    })

    it('clears the main session, logs the user store out and redirects to the main login', async () => {
      fetchMock.mockResolvedValue(json({ detail: 'expired' }, 401))
      await expect(slmApi.getNodes()).rejects.toThrow('HTTP 401')

      expect(clearStoredAuth).toHaveBeenCalledTimes(1)
      expect(window.location.href).toBe('/login?redirect=%2Fadmin%2Ffleet')
      await vi.waitFor(() => expect(logout).toHaveBeenCalledTimes(1))
      expect(fetchMock).toHaveBeenCalledTimes(1) // a 4xx is never retried
    })

    it('a 401 on an SLM auth endpoint is a credential failure, not a rejected session', async () => {
      // `isAuthEndpoint` matches `${getApiBase()}/auth/`, a substring of `/slm/api/auth/...`.
      // The stores never call one; this pins that an SLM auth route would not end the session.
      fetchMock.mockResolvedValue(json({ detail: 'bad credentials' }, 401))
      const response = await slmClient().rawRequest('/slm/api/auth/login', { method: 'POST', body: {} })
      expect(response.status).toBe(401)
      expect(clearStoredAuth).not.toHaveBeenCalled()
      expect(window.location.href).toBe('')
    })
  })

  describe('503 keeps the session (#18892, #16387)', () => {
    it('surfaces the retryable error, retries the GET, and neither clears auth nor redirects', async () => {
      vi.useFakeTimers()
      fetchMock.mockImplementation(async () => json({ detail: 'revocation_check_unavailable' }, 503))
      const settled = slmApi.getNodes().then(
        () => 'resolved',
        (error: Error) => error.message,
      )
      await vi.advanceTimersByTimeAsync(60_000)

      await expect(settled).resolves.toBe('HTTP 503: revocation_check_unavailable')
      expect(fetchMock.mock.calls.length).toBeGreaterThan(1) // 5xx is retried, unlike 4xx
      expect(clearStoredAuth).not.toHaveBeenCalled()
      expect(logout).not.toHaveBeenCalled()
      expect(window.location.href).not.toContain('/login')
    })
  })

  describe('typed seams for undeclared bodies', () => {
    it('enroll sends ssh_password only when given and returns the parsed body', async () => {
      fetchMock.mockImplementation(async () => json({ success: true, message: 'started' }))
      await expect(slmApi.enrollNode('n1')).resolves.toEqual({ success: true, message: 'started' })
      expect(JSON.parse(lastCall(fetchMock).init.body as string)).toEqual({})
      await slmApi.enrollNode('n1', 's3cret')
      expect(JSON.parse(lastCall(fetchMock).init.body as string)).toEqual({ ssh_password: 's3cret' }) // pragma: allowlist secret
      expect(lastCall(fetchMock).url).toBe(`${origin}/slm/api/nodes/n1/enroll`)
    })

    it('apply updates posts update_ids and returns applied/failed', async () => {
      fetchMock.mockResolvedValue(json({ applied_updates: ['u1'], failed_updates: [] }))
      await expect(slmApi.applyUpdates('n1', ['u1'])).resolves.toEqual({ applied_updates: ['u1'], failed_updates: [] })
      expect(JSON.parse(lastCall(fetchMock).init.body as string)).toEqual({ update_ids: ['u1'] })
      expect(lastCall(fetchMock).url).toBe(`${origin}/slm/api/nodes/n1/updates/apply`)
    })

    it('provision-status passes the line cursor as since_line', async () => {
      fetchMock.mockResolvedValue(json({ status: 'running', lines: ['x'], total_lines: 7, error: null }))
      await expect(slmApi.getProvisionStatus(6)).resolves.toMatchObject({ total_lines: 7 })
      expect(lastCall(fetchMock).url).toBe(`${origin}/slm/api/setup/provision-status?since_line=6`)
    })

    it('remove npu role is a DELETE on the node role route and returns success/message', async () => {
      fetchMock.mockResolvedValue(json({ success: true, message: 'removed' }))
      await expect(slmApi.removeNpuRole('n1')).resolves.toEqual({ success: true, message: 'removed' })
      expect(lastCall(fetchMock).init.method).toBe('DELETE')
      expect(lastCall(fetchMock).url).toBe(`${origin}/slm/api/npu/nodes/n1/role`)
    })
  })
})
