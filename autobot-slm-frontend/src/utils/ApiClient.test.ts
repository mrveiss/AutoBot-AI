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
import { SlmApiClient } from './ApiClient'

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
    expect(window.location.href).toBe('/login')
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
