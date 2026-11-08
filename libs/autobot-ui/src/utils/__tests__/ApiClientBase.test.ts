// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AbsoluteEndpointError, ApiClientBase, parseRetryAfterMs, withQuery, type TransportRequestOptions } from '../ApiClientBase'
import { HttpError } from '../httpError'

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

class TestClient extends ApiClientBase<TransportRequestOptions> {
  token: string | null = 'tok'
  unauthorized = vi.fn()
  constructor() {
    super(1000, logger as never)
  }
  protected resolveBaseUrl() { return 'http://base' }
  protected getAuthToken() { return this.token }
  protected isAuthEndpoint(endpoint: string) { return endpoint.includes('/auth/') }
  protected handleUnauthorized(endpoint: string, attached: boolean) { this.unauthorized(endpoint, attached) }
}

class ProxyClient extends TestClient {
  protected resolveBaseUrl() { return '' }
}

class TrustingClient extends ProxyClient {
  protected isTrustedAbsoluteEndpoint() { return true }
}

const FOREIGN_ENDPOINTS = [
  'https://evil.example/x', 'HTTP://evil.example/x', 'HtTpS://evil.example/x', 'ftp://evil.example/x',
  'javascript:alert(1)', '//evil.example/x', '/\\evil.example/x', '\\\\evil.example/x', '\\/evil.example/x',
  '  https://evil.example/x', '\thttps://evil.example/x', 'ht\ntps://evil.example/x', '\n//evil.example/x',
]

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } })

describe('ApiClientBase', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    Object.values(logger).forEach((fn) => fn.mockClear())
  })
  afterEach(() => vi.unstubAllGlobals())

  it('sends the bearer, the base URL and the query params', async () => {
    fetchMock.mockResolvedValue(json({ ok: 1 }))
    const result = await new TestClient().get('/x', { params: { a: 1, b: null, c: 'z' } })
    expect(result).toEqual({ ok: 1 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://base/x?a=1&c=z')
    expect(init.headers.Authorization).toBe('Bearer tok')
  })

  it('runs the 401 policy with whether a token was attached, and never on an auth endpoint', async () => {
    fetchMock.mockImplementation(async () => json({}, 401))
    const client = new TestClient()
    await client.rawRequest('/x')
    client.token = null
    await client.rawRequest('/y')
    await client.rawRequest('/auth/login')
    expect(client.unauthorized.mock.calls).toEqual([['/x', true], ['/y', false]])
  })

  it('keepSessionOn401 (per call or per client) skips the 401 policy', async () => {
    fetchMock.mockImplementation(async () => json({}, 401))
    const client = new TestClient()
    await client.rawRequest('/a', { keepSessionOn401: true })
    client.setKeepSessionOn401(true)
    await client.rawRequest('/b')
    expect(client.unauthorized).not.toHaveBeenCalled()
  })

  it('does not retry a 4xx GET and throws an HttpError carrying the status', async () => {
    fetchMock.mockImplementation(async () => json({ detail: 'nope' }, 404))
    await expect(new TestClient().get('/x')).rejects.toMatchObject({ status: 404 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(logger.warn).toHaveBeenCalledTimes(1)
  })

  it('retries a 5xx GET up to maxRetries and stays quiet with suppressErrorLog', async () => {
    fetchMock.mockImplementation(async () => json({}, 500))
    await expect(new TestClient().get('/x', { maxRetries: 2, suppressErrorLog: true })).rejects.toBeInstanceOf(HttpError)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(logger.warn).not.toHaveBeenCalled()
  })

  it('returns the body as text for responseType text', async () => {
    fetchMock.mockResolvedValue(new Response('plain', { status: 200 }))
    expect(await new TestClient().get('/x', { responseType: 'text' })).toBe('plain')
  })

  it('reads a 204 POST as an empty object', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    expect(await new TestClient().post('/x', { a: 1 })).toEqual({})
    expect(fetchMock.mock.calls[0][1].body).toBe('{"a":1}')
  })

  it('drops Content-Type for FormData so the browser sets the boundary', async () => {
    fetchMock.mockResolvedValue(json({}))
    await new TestClient().post('/x', new FormData())
    expect(fetchMock.mock.calls[0][1].headers['Content-Type']).toBeUndefined()
  })

  it('reports a timeout by its own message', async () => {
    fetchMock.mockImplementation((_u: string, init: RequestInit) => new Promise((_r, reject) => {
      init.signal!.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
    }))
    await expect(new TestClient().rawRequest('/x', { timeout: 5 })).rejects.toThrow('Request timeout after 5ms')
  })

  it('passes a caller abort through as the AbortError', async () => {
    const controller = new AbortController()
    controller.abort()
    fetchMock.mockImplementation(async (_u: string, init: RequestInit) => {
      if (init.signal!.aborted) throw Object.assign(new Error('aborted'), { name: 'AbortError' })
      return json({})
    })
    await expect(new TestClient().rawRequest('/x', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
  })

  describe.each([['a proxy-mode (empty base URL) client', ProxyClient], ['a client with a base URL', TestClient]])('%s', (_name, Client) => {
    it.each(FOREIGN_ENDPOINTS)('refuses %j without any request, so no Authorization header leaves', async (endpoint) => {
      const client = new Client()
      await expect(client.rawRequest(endpoint)).rejects.toBeInstanceOf(AbsoluteEndpointError)
      await expect(client.get(endpoint)).rejects.toBeInstanceOf(AbsoluteEndpointError)
      await expect(client.post(endpoint, {})).rejects.toBeInstanceOf(AbsoluteEndpointError)
      await expect(client.uploadFile(endpoint, new File(['x'], 'x.txt'))).rejects.toBeInstanceOf(AbsoluteEndpointError)
      expect(fetchMock).not.toHaveBeenCalled()
    })

    it('does not retry or log a refused GET', async () => {
      await expect(new Client().get('//evil.example/x')).rejects.toBeInstanceOf(AbsoluteEndpointError)
      expect(logger.warn).not.toHaveBeenCalled()
    })

    it.each(['/api/x', '/api/x?next=https://ok.example', '/a//b', '/api/x:y'])('still sends the bearer on %s', async (endpoint) => {
      fetchMock.mockResolvedValue(json({}))
      await new Client().rawRequest(endpoint)
      expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer tok')
    })
  })

  describe('isTrustedAbsoluteEndpoint hook (#20053)', () => {
    it('defaults to refusing every scheme: endpoint (covered by the foreign-endpoint cases above)', async () => {
      await expect(new TestClient().get('https://api.example/x')).rejects.toBeInstanceOf(AbsoluteEndpointError)
      expect(fetchMock).not.toHaveBeenCalled()
    })

    it('lets an override admit a scheme: endpoint through get, rawRequest and uploadFile', async () => {
      fetchMock.mockResolvedValue(json({}))
      const client = new TrustingClient()
      await client.get('https://api.example/x')
      await client.rawRequest('https://api.example/x')
      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer tok')
      const opened: string[] = []
      vi.stubGlobal('XMLHttpRequest', class {
        upload = {}
        status = 200
        responseText = '{}'
        open(_method: string, url: string) { opened.push(url) }
        setRequestHeader() {}
        send() { (this as unknown as { onload: () => void }).onload() }
      })
      await client.uploadFile('https://api.example/up', new File(['x'], 'x.txt'))
      expect(opened).toEqual(['https://api.example/up'])
      vi.unstubAllGlobals()
    })

    it.each(['//evil.example/x', '/\\evil.example/x', '\\\\evil.example/x', '\n//evil.example/x'])(
      'never consults the override for %j: protocol-relative and backslash forms stay refused',
      async (endpoint) => {
        const client = new TrustingClient()
        await expect(client.get(endpoint)).rejects.toBeInstanceOf(AbsoluteEndpointError)
        await expect(client.rawRequest(endpoint)).rejects.toBeInstanceOf(AbsoluteEndpointError)
        expect(fetchMock).not.toHaveBeenCalled()
      }
    )
  })
})

describe('withQuery and parseRetryAfterMs', () => {
  it('keeps an existing query and skips empty params', () => {
    expect(withQuery('/x?a=1', { b: 2, c: undefined })).toBe('/x?a=1&b=2')
    expect(withQuery('/x', { b: null })).toBe('/x')
  })

  it('reads delta-seconds and dates, and treats junk as 0', () => {
    expect(parseRetryAfterMs('3')).toBe(3000)
    expect(parseRetryAfterMs('Wed, 21 Oct 2015 07:28:10 GMT', Date.parse('Wed, 21 Oct 2015 07:28:00 GMT'))).toBe(10_000)
    expect(parseRetryAfterMs('junk')).toBe(0)
    expect(parseRetryAfterMs(null)).toBe(0)
  })
})
