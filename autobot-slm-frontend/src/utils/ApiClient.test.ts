// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Unit tests for the canonical SLM ApiClient (#12420 Phase 1).
 *
 * Covers: base-URL resolution from getSlmApiBase(), auth-header injection
 * (sessionStorage primary + localStorage fallback), 401 session handling
 * (token-carrying vs token-less vs auth-endpoint), GET retry/backoff, request
 * timeout via AbortController, FormData passthrough and 204 handling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { SlmApiClient, parseRetryAfterMs } from './ApiClient'

const TOKEN_KEY = 'slm_access_token'
const USER_KEY = 'slm_user'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('SlmApiClient', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let originalLocation: Location

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    // Replace window.location with a mutable stub so redirects are observable.
    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/fleet', href: '' } as unknown as Location,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs() // here, not in a test body: a failed assertion would leak BASE_URL
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    })
  })

  // -------------------------------------------------------------------------
  // Base URL resolution
  // -------------------------------------------------------------------------

  it('resolves base URL from getSlmApiBase() (/api) and prefixes the endpoint', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    const client = new SlmApiClient()

    await client.get('/nodes')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/nodes')
  })

  it('honours a setBaseUrl() override', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    const client = new SlmApiClient()
    client.setBaseUrl('/slm/api')

    await client.get('/nodes')

    expect(fetchMock.mock.calls[0][0]).toBe('/slm/api/nodes')
  })

  // -------------------------------------------------------------------------
  // Auth header injection
  // -------------------------------------------------------------------------

  it('injects Authorization from sessionStorage token', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'session-jwt')
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    const client = new SlmApiClient()

    await client.get('/nodes')

    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer session-jwt')
  })

  it('falls back to localStorage token when sessionStorage is empty', async () => {
    localStorage.setItem(TOKEN_KEY, 'local-jwt')
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    const client = new SlmApiClient()

    await client.get('/nodes')

    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer local-jwt')
  })

  it('omits Authorization when no token is stored', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    const client = new SlmApiClient()

    await client.get('/nodes')

    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined()
  })

  // -------------------------------------------------------------------------
  // 401 handling
  // -------------------------------------------------------------------------

  it('clears session and redirects to /login on 401 when a token was attached', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'expired-jwt')
    sessionStorage.setItem(USER_KEY, '{"username":"a"}')
    localStorage.setItem(TOKEN_KEY, 'expired-jwt')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'unauthorized' }, 401))
    const client = new SlmApiClient()

    await expect(client.get('/nodes', { maxRetries: 1 })).rejects.toThrow('HTTP 401')

    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(sessionStorage.getItem(USER_KEY)).toBeNull()
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(window.location.href).toBe(`/login?redirect=${encodeURIComponent('/fleet')}`)
  })

  it('keeps the session on a 401 when the caller asked to (a connectivity probe, #12363)', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'live-jwt')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'unauthorized' }, 401))
    const client = new SlmApiClient()

    const response = await client.rawRequest('/health', { keepSessionOn401: true })

    expect(response.status).toBe(401)
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe('live-jwt')
    expect(window.location.href).toBe('')
  })

  it('keeps the session on every 401 from a client set to keep it (#10193, #12363)', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'live-jwt')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'unauthorized' }, 401))
    const client = new SlmApiClient()
    client.setKeepSessionOn401(true)

    await expect(client.get('/settings', { maxRetries: 1 })).rejects.toThrow('HTTP 401')

    expect(sessionStorage.getItem(TOKEN_KEY)).toBe('live-jwt')
    expect(window.location.href).toBe('')
  })

  it('redirects to the base-aware login with the current route as redirect (#18892)', async () => {
    vi.stubEnv('BASE_URL', '/slm/')
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/slm/updates/summary', search: '?tab=system', hash: '', href: '' } as unknown as Location,
    })
    sessionStorage.setItem(TOKEN_KEY, 'expired-jwt')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'unauthorized' }, 401))
    const client = new SlmApiClient()

    await expect(client.get('/nodes', { maxRetries: 1 })).rejects.toThrow('HTTP 401')

    expect(window.location.href).toBe(
      `/slm/login?redirect=${encodeURIComponent('/updates/summary?tab=system')}`
    )
  })

  it('does not redirect again when already on the base-aware login page (#18892)', async () => {
    vi.stubEnv('BASE_URL', '/slm/')
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/slm/login', search: '', hash: '', href: '' } as unknown as Location,
    })
    sessionStorage.setItem(TOKEN_KEY, 'expired-jwt')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'unauthorized' }, 401))
    const client = new SlmApiClient()

    await expect(client.get('/nodes', { maxRetries: 1 })).rejects.toThrow('HTTP 401')

    expect(window.location.href).toBe('')
  })

  it('keeps the session and does not redirect on 503, surfacing a retryable error (#18892)', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'live-jwt')
    fetchMock.mockImplementation(async () =>
      jsonResponse({ detail: 'revocation_check_unavailable' }, 503)
    )
    const client = new SlmApiClient()

    await expect(client.get('/nodes', { maxRetries: 2 })).rejects.toThrow(
      'HTTP 503: revocation_check_unavailable'
    )

    expect(fetchMock).toHaveBeenCalledTimes(2) // 5xx is retried, unlike 4xx
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe('live-jwt')
    expect(window.location.href).toBe('')
  })

  describe('503 Retry-After (#18892)', () => {
    function unavailable(headers: Record<string, string> = {}): Response {
      return new Response(JSON.stringify({ detail: 'revocation_check_unavailable' }), {
        status: 503,
        headers: { 'content-type': 'application/json', ...headers },
      })
    }

    // Measured on the fake clock, never by spying on setTimeout: a spy installed over the
    // fake timer outlives useRealTimers() and leaves later tests' timers that never fire.
    async function fetchesAfter(headers: Record<string, string>, elapsedMs: number): Promise<number> {
      vi.useFakeTimers()
      try {
        fetchMock.mockImplementationOnce(async () => unavailable(headers))
        fetchMock.mockImplementationOnce(async () => jsonResponse({ ok: true }))
        const pending = new SlmApiClient().get('/nodes', { maxRetries: 2 })
        await vi.advanceTimersByTimeAsync(elapsedMs)
        const calls = fetchMock.mock.calls.length
        await vi.advanceTimersByTimeAsync(10_000)
        await pending
        return calls
      } finally {
        vi.useRealTimers()
      }
    }

    it('waits at least Retry-After seconds before retrying', async () => {
      expect(await fetchesAfter({ 'retry-after': '3' }, 2_999)).toBe(1)
    })

    it('retries once Retry-After has elapsed', async () => {
      expect(await fetchesAfter({ 'retry-after': '3' }, 3_001)).toBe(2)
    })

    it('uses plain backoff when Retry-After is missing', async () => {
      expect(await fetchesAfter({}, 2_999)).toBe(2)
    })

    it('uses plain backoff when Retry-After is garbage', async () => {
      expect(await fetchesAfter({ 'retry-after': 'soon-ish' }, 2_999)).toBe(2)
    })

    it('parses an HTTP-date Retry-After as a floor', () => {
      const now = Date.parse('2026-10-20T10:00:00Z')
      expect(parseRetryAfterMs('Tue, 20 Oct 2026 10:00:04 GMT', now)).toBe(4000)
      expect(parseRetryAfterMs(null, now)).toBe(0)
    })
  })

  it('does NOT clear session on a token-less 401', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'unauthorized' }, 401))
    const client = new SlmApiClient()

    await expect(client.get('/public', { maxRetries: 1 })).rejects.toThrow('HTTP 401')

    expect(window.location.href).toBe('')
  })

  it('does NOT clear session on a 401 from an auth endpoint', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'temp-jwt')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'bad creds' }, 401))
    const client = new SlmApiClient()

    await expect(client.get('/auth/me', { maxRetries: 1 })).rejects.toThrow('HTTP 401')

    expect(sessionStorage.getItem(TOKEN_KEY)).toBe('temp-jwt')
    expect(window.location.href).toBe('')
  })

  // -------------------------------------------------------------------------
  // Retry / backoff
  // -------------------------------------------------------------------------

  it('retries a failed GET and succeeds on a later attempt', async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError('network down'))
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
    const client = new SlmApiClient()

    const result = await client.get<{ ok: boolean }>('/nodes', { maxRetries: 2 })

    expect(result).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('does NOT retry a 4xx client error', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'not found' }, 404))
    const client = new SlmApiClient()

    await expect(client.get('/nodes', { maxRetries: 3 })).rejects.toThrow('HTTP 404')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  // -------------------------------------------------------------------------
  // Timeout via AbortController
  // -------------------------------------------------------------------------

  it('aborts and throws a timeout error when the request exceeds the timeout', async () => {
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => {
            const err = new Error('aborted')
            err.name = 'AbortError'
            reject(err)
          })
        })
    )
    const client = new SlmApiClient()

    await expect(client.rawRequest('/nodes', { timeout: 30 })).rejects.toThrow(
      'Request timeout after 30ms'
    )
  })

  // -------------------------------------------------------------------------
  // FormData passthrough + 204 handling
  // -------------------------------------------------------------------------

  it('passes FormData through untouched and drops the JSON Content-Type header', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    const client = new SlmApiClient()
    const form = new FormData()
    form.append('field', 'value')

    await client.post('/upload', form)

    const [, init] = fetchMock.mock.calls[0]
    expect(init.body).toBe(form)
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined()
  })

  it('serialises a plain object body as JSON', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    const client = new SlmApiClient()

    await client.post('/nodes', { name: 'n1' })

    const [, init] = fetchMock.mock.calls[0]
    expect(init.body).toBe(JSON.stringify({ name: 'n1' }))
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('returns an empty object for a 204 No Content response', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    const client = new SlmApiClient()

    const result = await client.delete('/nodes/n1')

    expect(result).toEqual({})
  })

  it('throws a descriptive error for a non-OK POST', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'boom' }, 500))
    const client = new SlmApiClient()

    await expect(client.post('/nodes', {})).rejects.toThrow('HTTP 500: boom')
  })
})

describe('SlmApiClient.getContract (#16292)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('drops the contract key\'s /api prefix, because the base supplies it', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ nodes: [], total: 0 }))
    const client = new SlmApiClient()

    const body = await client.getContract('/api/monitoring/gpu/nodes')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/monitoring/gpu/nodes')
    expect(body).toEqual({ nodes: [], total: 0 })
  })

  it('keeps a co-located base', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ nodes: [], total: 0 }))
    const client = new SlmApiClient()
    client.setBaseUrl('/slm/api')

    await client.getContract('/api/monitoring/gpu/nodes')

    expect(fetchMock.mock.calls[0][0]).toBe('/slm/api/monitoring/gpu/nodes')
  })
})
