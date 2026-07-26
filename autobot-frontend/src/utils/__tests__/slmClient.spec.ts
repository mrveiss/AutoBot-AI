// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SlmClient tests (#12614)
 *
 * The canonical SLM bridge for the main frontend. Verifies:
 *  - base URL resolves from getSLMUrl() (SLM backend, NOT the app backend)
 *  - the SLM token is injected per-client from its token getter (read live),
 *    and token-less clients send no Authorization header
 *  - JSON body serialisation + default JSON Content-Type
 *  - raw bodies (URLSearchParams) pass through untouched, no forced JSON header
 *  - skipAuth suppresses token injection
 *  - error handling: detail/message/error preference, HTTP status fallback
 *  - 204 / non-JSON bodies parse to {}
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('@/config/ssot-config', () => ({
  getSLMUrl: vi.fn(() => 'http://slm.test:8000'),
}))

import { getSLMUrl } from '@/config/ssot-config'
import { SlmClient, slmClient } from '../slmClient'

function jsonResponse(body: unknown, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    statusText: `Status ${status}`,
    headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response
}

describe('SlmClient', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = fetchMock as unknown as typeof fetch
    vi.mocked(getSLMUrl).mockReturnValue('http://slm.test:8000')
  })

  it('resolves the base URL from getSLMUrl() and appends the caller path', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    await new SlmClient().get('/api/nodes?page=1')

    expect(getSLMUrl).toHaveBeenCalled()
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('http://slm.test:8000/api/nodes?page=1')
  })

  it('re-resolves the base URL on every request (lazy, not cached)', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}))
    const client = new SlmClient()
    await client.get('/api/a')
    vi.mocked(getSLMUrl).mockReturnValue('/slm')
    await client.get('/api/b')

    expect(fetchMock.mock.calls[0][0]).toBe('http://slm.test:8000/api/a')
    expect(fetchMock.mock.calls[1][0]).toBe('/slm/api/b')
  })

  it('injects the SLM bearer token from the client token getter (read live)', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}))
    let token: string | null = 'tok-1'
    const client = new SlmClient(() => token)

    await client.get('/api/nodes')
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer tok-1',
    })

    token = 'tok-2'
    await client.get('/api/nodes')
    expect((fetchMock.mock.calls[1][1] as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer tok-2',
    })
  })

  it('sends no Authorization header for a token-less client', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}))
    await new SlmClient().get('/api/nodes')

    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('skipAuth suppresses token injection even when a token is present', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ access_token: 'x' }))
    const client = new SlmClient(() => 'tok')
    await client.rawRequest('/api/auth/token', { method: 'POST', skipAuth: true })

    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })

  it('JSON-serialises object bodies and defaults the JSON Content-Type', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1 }))
    await new SlmClient().post('/api/nodes', { hostname: 'h1' })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ hostname: 'h1' }))
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('passes raw bodies (URLSearchParams) through without forcing JSON Content-Type', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ access_token: 'x' }))
    const form = new URLSearchParams({ username: 'u', password: 'p' })
    await new SlmClient().rawRequest('/api/auth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.body).toBe(form)
    expect((init.headers as Record<string, string>)['Content-Type']).toBe(
      'application/x-www-form-urlencoded'
    )
  })

  it('throws Error(detail) on a non-OK JSON error body', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'node not found' }, { ok: false, status: 404 }))
    await expect(new SlmClient().get('/api/nodes/x')).rejects.toThrow('node not found')
  })

  it('falls back to HTTP <status>: <statusText> when no detail/message/error present', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 500 }))
    await expect(new SlmClient().get('/api/nodes')).rejects.toThrow('HTTP 500: Status 500')
  })

  it('delete on a 204 No Content resolves to {} (no body read error)', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 204,
      statusText: 'No Content',
      headers: { get: () => null },
      json: vi.fn().mockRejectedValue(new Error('no body')),
    } as unknown as Response)

    await expect(new SlmClient().delete('/api/tls/credentials/c1')).resolves.toEqual({})
  })

  it('exports a token-less default singleton', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}))
    await slmClient.get('/api/nodes')
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })
})
