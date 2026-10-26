// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SlmApiClient's #12363 options, which let a second client (useAutobotApi's axios)
 * move onto it: errors keep status and details, query params, a text GET, and a
 * DELETE body.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { HttpError } from '@autobot/ui'
import { SlmApiClient, withQuery } from './ApiClient'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

describe('SlmApiClient #12363 options', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let client: SlmApiClient

  beforeEach(() => {
    sessionStorage.clear()
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    client = new SlmApiClient()
    client.setBaseUrl('/autobot-api')
  })
  afterEach(() => vi.unstubAllGlobals())

  it('throws an HttpError that keeps the old message, the status and the backend detail', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Rule already exists' }, 409))
    const err = await client.post('/permissions/rules', { a: 1 }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(HttpError)
    const http = err as HttpError
    expect(http.message).toBe('HTTP 409: Rule already exists')
    expect(http.status).toBe(409)
    expect(http.detail).toBe('Rule already exists')
  })

  it('does not retry a 4xx GET, as before, and still throws HttpError', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'nope' }, 404))
    await expect(client.get('/x', { maxRetries: 3 })).rejects.toBeInstanceOf(HttpError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('still retries a 5xx GET, the text form included, then succeeds', async () => {
    vi.useFakeTimers()
    try {
      fetchMock
        .mockResolvedValueOnce(jsonResponse({ detail: 'busy' }, 500))
        .mockResolvedValueOnce(new Response('ok', { status: 200, headers: { 'content-type': 'text/plain' } }))
      const pending = client.get<string>('/metrics', { responseType: 'text', maxRetries: 2 })
      await vi.runAllTimersAsync()
      await expect(pending).resolves.toBe('ok')
      expect(fetchMock).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it.each(['put', 'patch', 'delete'] as const)('throws an HttpError from %s too', async (verb) => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'denied' }, 403))
    const call = verb === 'delete' ? client.delete('/x') : client[verb]('/x', { a: 1 })
    const err = await call.catch((e: unknown) => e)
    expect(err).toBeInstanceOf(HttpError)
    expect((err as HttpError).status).toBe(403)
    expect((err as HttpError).detail).toBe('denied')
  })

  it('appends params URL-encoded and leaves out null and undefined', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}))
    await client.put('/mcp/servers/a b/toggle', null, { params: { enabled: true, host: undefined, note: null } })
    expect(fetchMock.mock.calls[0][0]).toBe('/autobot-api/mcp/servers/a b/toggle?enabled=true')
  })

  it('returns the raw body for a text GET instead of parsing JSON', async () => {
    fetchMock.mockResolvedValue(new Response('# HELP up\nup 1\n', { status: 200, headers: { 'content-type': 'text/plain' } }))
    await expect(client.get<string>('/metrics', { responseType: 'text' })).resolves.toBe('# HELP up\nup 1\n')
  })

  it('sends a DELETE body when one is given', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    await client.delete('/permissions/rules', { body: { pattern: 'rm *' } })
    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('DELETE')
    expect(init.body).toBe(JSON.stringify({ pattern: 'rm *' }))
  })

  it('keeps an existing query string when adding params', () => {
    expect(withQuery('/logs?level=warn', { limit: 10 })).toBe('/logs?level=warn&limit=10')
    expect(withQuery('/logs', {})).toBe('/logs')
    expect(withQuery('/logs', undefined)).toBe('/logs')
  })
})
