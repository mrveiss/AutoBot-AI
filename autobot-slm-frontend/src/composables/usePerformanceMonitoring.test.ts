// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * usePerformanceMonitoring transport — #13140 definition-of-done item 3.
 *
 * This composable's `apiRequest` helper was migrated onto `slmApiClient` and
 * left without a test. What needs pinning is not that it reaches the network —
 * it is the three properties the migration deliberately PRESERVED, each of which
 * a later "simplification" to `slmApiClient.get()` would silently destroy. The
 * helper's own docstring names them, and a documented intention with no test is
 * one refactor away from being read as an oversight:
 *
 *   1. **Single-shot dispatch.** `get()` retries a 5xx three times with
 *      exponential backoff. `startPolling()` re-issues `fetchOverview` every
 *      `pollInterval`, so a retried tick would overlap the next one.
 *   2. **The verbatim error message.** Every catch block surfaces
 *      `HTTP <n>: <raw body text>` to the user; the typed helpers re-shape it
 *      from parsed JSON, which changes what the UI shows.
 *   3. **The bearer is read from storage per request**, not from a reactive ref
 *      seeded once at store construction — the defect that sent requests out
 *      with no credential when the token landed later.
 *
 * Asserted against the global `fetch` rather than a mocked `slmApiClient`, so
 * the endpoint path is checked through the real base-URL resolution instead of
 * around it.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { usePerformanceMonitoring } from './usePerformanceMonitoring'

const TOKEN_KEY = 'slm_access_token'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function textResponse(body: string, status: number): Response {
  return new Response(body, { status, headers: { 'content-type': 'text/plain' } })
}

describe('usePerformanceMonitoring transport', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    fetchMock = vi.fn().mockResolvedValue(jsonResponse({ slos: [] }))
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('resolves each endpoint against the SLM API base', async () => {
    const { fetchOverview } = usePerformanceMonitoring()

    await fetchOverview()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/performance/overview')
  })

  it('applies the client timeout, which the previous raw fetch had none of', async () => {
    const { fetchSLOs } = usePerformanceMonitoring()

    await fetchSLOs()

    expect((fetchMock.mock.calls[0][1] as RequestInit).signal).toBeInstanceOf(AbortSignal)
  })

  it('reads the bearer from storage on the request, not at construction', async () => {
    // The composable is created BEFORE the token exists: the order that used to
    // send an anonymous request for the rest of the session.
    const { fetchSLOs } = usePerformanceMonitoring()
    sessionStorage.setItem(TOKEN_KEY, 'late-token')

    await fetchSLOs()

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer late-token')
  })

  it('falls back to localStorage for the bearer', async () => {
    localStorage.setItem(TOKEN_KEY, 'persisted-token')
    const { fetchSLOs } = usePerformanceMonitoring()

    await fetchSLOs()

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer persisted-token')
  })

  it('sends no Authorization header at all when there is no session', async () => {
    const { fetchSLOs } = usePerformanceMonitoring()

    await fetchSLOs()

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })

  it('dispatches a 5xx ONCE — a retry would overlap the next poll tick', async () => {
    // The load-bearing reason this helper calls rawRequest and not get().
    fetchMock.mockResolvedValue(textResponse('overview backend down', 503))
    const { fetchOverview } = usePerformanceMonitoring()

    await fetchOverview()

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('surfaces the raw body text in the error, not a re-shaped message', async () => {
    fetchMock.mockResolvedValue(textResponse('slo store unavailable', 500))
    const { fetchSLOs, error } = usePerformanceMonitoring()

    await fetchSLOs()

    expect(error.value).toBe('HTTP 500: slo store unavailable')
  })

  it('falls back to the status text when the body is empty', async () => {
    fetchMock.mockResolvedValue(new Response('', { status: 502, statusText: 'Bad Gateway' }))
    const { fetchSLOs, error } = usePerformanceMonitoring()

    await fetchSLOs()

    expect(error.value).toContain('HTTP 502')
  })

  it('hands the body over unserialised, so rawRequest encodes it exactly once', async () => {
    // A pre-stringified body would be double-encoded and the backend would read
    // a JSON string where it expects an object.
    fetchMock.mockResolvedValue(jsonResponse({ slo_id: 'slo-1' }))
    const { createSLO } = usePerformanceMonitoring()

    const payload = {
      name: 'p99-latency',
      description: null,
      target_percent: 99,
      metric_type: 'latency',
      threshold_value: 250,
      threshold_unit: 'ms',
      window_days: 30,
      node_id: null,
      enabled: true,
    }

    await createSLO(payload)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/performance/slos')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual(payload)
  })

  it('treats a 204 as success rather than an unparseable body', async () => {
    // `deleteSLO` then calls `fetchSLOs`, so a throw here would report a failed
    // delete for one that succeeded.
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    const { deleteSLO } = usePerformanceMonitoring()

    await expect(deleteSLO('slo-1')).resolves.toBe(true)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/performance/slos/slo-1')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('DELETE')
  })

  it('encodes the trace query on the endpoint, relative to the base', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ traces: [], total: 0 }))
    const { fetchTraces } = usePerformanceMonitoring()

    await fetchTraces({ hours: 24, page: 2 })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/performance/traces?hours=24&page=2')
  })
})
