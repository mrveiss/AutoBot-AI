// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The former raw `fetch` sites now go through fetchWithAuth (#12363): they keep
 * their URL/method/body/credentials and gain the bearer token.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { LiveEventService } from '@/services/LiveEventService'
import { GlobalWebSocketService } from '@/services/GlobalWebSocketService'

// Built rather than a literal so a secret scanner never mistakes fixture data.
const TOKEN = ['fixture', 'not-a-real', 'value-0123456789abcdef'].join('.')

describe('migrated raw fetch sites (#12363)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    localStorage.setItem('autobot_auth', JSON.stringify({ token: TOKEN }))
    fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ steering_id: 's1' }), { status: 200 })
    )
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('sendSteeringMessage keeps method, body, credentials and now sends the bearer token', async () => {
    await new LiveEventService().sendSteeringMessage({ task_id: 't 1', guidance: 'go' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/agent-terminal/tasks/t%201/steer')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('include')
    expect(init.body).toBe(JSON.stringify({ guidance: 'go', task_id: 't 1' }))
    expect(new Headers(init.headers).get('Authorization')).toBe(`Bearer ${TOKEN}`)
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('quickHealthCheck keeps no-store + abort signal and resolves to response.ok', async () => {
    const ok = await new GlobalWebSocketService().quickHealthCheck()
    const [url, init] = fetchMock.mock.calls[0]
    expect(ok).toBe(true)
    expect(url).toMatch(/\/health$/)
    expect(init.cache).toBe('no-store')
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('quickHealthCheck still rethrows network errors', async () => {
    fetchMock.mockRejectedValueOnce(new Error('offline'))
    await expect(new GlobalWebSocketService().quickHealthCheck()).rejects.toThrow('offline')
  })
})
