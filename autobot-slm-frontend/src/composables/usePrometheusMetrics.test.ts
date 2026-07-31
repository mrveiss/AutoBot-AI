// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * usePrometheusMetrics — metrics transport behaviour (#13140).
 *
 * This composable is the largest of the `getSlmApiBase()` group (9 call sites)
 * and the one with the most to lose from a mechanical swap, because every read
 * in it is issued from a 30s polling loop. What is asserted here is what the
 * raw `fetch` sites did NOT do:
 *
 *   * the request carried NO `Authorization` header for any token that landed
 *     in storage AFTER the auth store was constructed. `getHeaders()` read
 *     `authStore.token`, and that ref is seeded from storage exactly once
 *     (`stores/auth.ts:66`) — so a login in another tab, or a refresh done
 *     through a different store instance, left the poll going out anonymous
 *     against a session that was demonstrably present;
 *   * no request had a timeout, so a hung SLM backend pinned a poll tick open
 *     indefinitely;
 *
 * and what must NOT change now that the client is in the path:
 *
 *   * a polled read stays single-shot — `slmApiClient.get()` otherwise retries
 *     a 5xx three times with ~3s of exponential backoff, which inside a poll
 *     loop stacks ticks on top of each other;
 *   * `/performance/metrics/prometheus` is still read as TEXT, not parsed as
 *     JSON — it returns the Prometheus exposition format.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePrometheusMetrics } from './usePrometheusMetrics'
import { useAuthStore } from '@/stores/auth'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

const TOKEN_KEY = 'slm_access_token'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function textResponse(body: string, status = 200): Response {
  return new Response(body, { status, headers: { 'content-type': 'text/plain' } })
}

/** The composable is used outside a component here, so lifecycle hooks no-op. */
function metrics() {
  return usePrometheusMetrics({ autoFetch: false, pollInterval: 0 })
}

function lastInit(mock: ReturnType<typeof vi.fn>): RequestInit {
  return mock.mock.calls[mock.mock.calls.length - 1][1] as RequestInit
}

function headerOf(init: RequestInit, name: string): string | undefined {
  return (init.headers as Record<string, string>)[name]
}

describe('usePrometheusMetrics transport', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let originalLocation: Location

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/monitoring', href: '' } as unknown as Location,
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

  it('sends a bearer that reached storage after the auth store was constructed', async () => {
    // Construct the store with NO session, then write the token — the shape of
    // a login in another tab, or of a refresh performed through a different
    // store instance. `authStore.token` is seeded from storage once, at
    // construction, so it is still null here and `getHeaders()` produced no
    // Authorization header at all: the poll went out anonymous against a
    // session that plainly exists. The client re-reads storage per request.
    useAuthStore()
    sessionStorage.setItem(TOKEN_KEY, 'poll-token')
    fetchMock.mockResolvedValue(jsonResponse({ fleet_metrics: {}, health_summary: {} }))

    await metrics().fetchDashboard()

    expect(headerOf(lastInit(fetchMock), 'Authorization')).toBe('Bearer poll-token')
  })

  it('gives every polled read an abort signal, so a hung backend cannot pin a tick open', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'poll-token')
    fetchMock.mockResolvedValue(jsonResponse({ fleet_metrics: {}, health_summary: {} }))

    await metrics().fetchDashboard()

    expect(lastInit(fetchMock).signal).toBeInstanceOf(AbortSignal)
  })

  it('keeps a polled read single-shot on a 500 rather than retrying inside the tick', async () => {
    // Regression guard on POLL_OPTS, not a pre-change defect: the raw fetch
    // did not retry either. Dropping `maxRetries` would silently turn one
    // 30s tick into three attempts with ~3s of backoff.
    sessionStorage.setItem(TOKEN_KEY, 'poll-token')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'boom' }, 500))

    const m = metrics()
    await m.fetchFleetMetrics()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(m.error.value).toContain('500')
  })

  it('reports a failed dashboard read instead of leaving the panel silently stale', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'poll-token')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'dashboard down' }, 503))

    const m = metrics()
    await m.fetchDashboard()

    expect(m.isConnected.value).toBe(false)
    expect(m.error.value).toContain('dashboard down')
  })

  it('resolves endpoints against the SLM API base', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'poll-token')
    fetchMock.mockResolvedValue(jsonResponse({ nodes: [] }))

    await metrics().fetchNPUDetails()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/npu/nodes')
  })

  it('reads the Prometheus export as text, not as JSON', async () => {
    // `get()` would call response.json() and reject on the exposition format —
    // this read keeps the Response object on purpose.
    sessionStorage.setItem(TOKEN_KEY, 'poll-token')
    const exposition = '# HELP slm_up\nslm_up 1\n'
    fetchMock.mockResolvedValue(textResponse(exposition))

    const m = metrics()
    await m.fetchPrometheusExport()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/performance/metrics/prometheus')
    expect(m.prometheusExport.value).toBe(exposition)
    expect(m.error.value).toBeNull()
  })

  it('clears the session and redirects when a poll is rejected as unauthorised', async () => {
    // The raw sites dropped a 401: `if (response.ok)` with no else left the
    // panel rendering stale numbers against a dead session.
    sessionStorage.setItem(TOKEN_KEY, 'expired-token')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Not authenticated' }, 401))

    await metrics().fetchAlerts()

    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(window.location.href).toBe('/login')
  })
})
