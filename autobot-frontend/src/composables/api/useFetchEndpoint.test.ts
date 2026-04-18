// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Unit tests for the rehomed useFetchEndpoint.
 *
 * Focuses on the DIFFERENCES from the analytics-domain alias:
 *   - `deps` is OPTIONAL
 *   - `scopeToSource` defaults FALSE
 *   - warns but doesn't throw when scopeToSource=true without withSourceId
 *
 * The analytics alias is covered by the pre-existing
 * composables/analytics/useAnalyticsEndpoint.test.ts (which exercises the
 * default-true scopeToSource path through the alias).
 *
 * Issue #5153 scope C.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn(),
}))

vi.mock('@/config/AppConfig.js', () => ({
  default: {
    getServiceUrl: vi.fn(async () => 'http://backend.test'),
  },
}))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { useFetchEndpoint } from './useFetchEndpoint'

const mockedFetch = vi.mocked(fetchWithAuth)

interface RawPayload {
  ok: boolean
  value?: number
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('useFetchEndpoint (rehomed)', () => {
  beforeEach(() => {
    mockedFetch.mockReset()
  })

  it('works with NO deps argument (deps is optional)', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 42 }),
    )
    const { data, load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/templates/templates',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
    })
    // no deps passed at all
    await load()
    expect(data.value).toBe(42)
    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toBe('http://backend.test/api/templates/templates')
  })

  it('defaults scopeToSource to false (does NOT call withSourceId even when provided)', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 1 }),
    )
    const withSourceId = vi.fn((u: string) => `${u}?source_id=s1`)
    const { load } = useFetchEndpoint<RawPayload, number>(
      {
        path: '/api/whatever',
        pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      },
      { withSourceId },
    )
    await load()
    expect(withSourceId).not.toHaveBeenCalled()
    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toBe('http://backend.test/api/whatever')
  })

  it('scopeToSource=true with deps.withSourceId wraps the URL', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 1 }),
    )
    const withSourceId = vi.fn((u: string) => `${u}?source_id=s42`)
    const { load } = useFetchEndpoint<RawPayload, number>(
      {
        path: '/api/analytics/codebase/stats',
        scopeToSource: true,
        pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      },
      { withSourceId },
    )
    await load()
    expect(withSourceId).toHaveBeenCalledTimes(1)
    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toBe('http://backend.test/api/analytics/codebase/stats?source_id=s42')
  })

  it('scopeToSource=true with NO deps falls back to identity and does not throw', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 7 }),
    )
    const { data, error, load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/analytics/codebase/stats',
      scopeToSource: true,
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
    })
    await load()
    expect(error.value).toBe('')
    expect(data.value).toBe(7)
    // URL unchanged — identity fallback
    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toBe('http://backend.test/api/analytics/codebase/stats')
  })

  it('scopeToSource=true with deps={} (withSourceId omitted) falls back to identity', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 1 }),
    )
    const { data, load } = useFetchEndpoint<RawPayload, number>(
      {
        path: '/api/x',
        scopeToSource: true,
        pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      },
      {}, // empty deps
    )
    await load()
    expect(data.value).toBe(1)
    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toBe('http://backend.test/api/x')
  })

  it('POST with body works without deps', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 3 }),
    )
    const { load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/things/analyze',
      method: 'POST',
      body: () => ({ trigger: 'manual' }),
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
    })
    await load()
    const init = mockedFetch.mock.calls[0]?.[1] as RequestInit | undefined
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe(JSON.stringify({ trigger: 'manual' }))
  })

  it('queryExtras still appended when scopeToSource=false', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 1 }),
    )
    const { load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/search',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
    })
    await load({ q: 'claude', limit: '5' })
    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toContain('q=claude')
    expect(url).toContain('limit=5')
  })

  it('error path populates error.value and clears data (unchanged from alias)', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({}, 500))
    const { data, error, load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/boom',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      label: 'Boom endpoint',
    })
    await load()
    expect(data.value).toBeNull()
    expect(error.value).toContain('Boom endpoint returned 500')
  })

  it('pickData null -> no-data path (onNoData fires, data stays null, no error)', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: false }),
    )
    const onNoData = vi.fn()
    const { data, error, load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/x',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      onNoData,
    })
    await load()
    expect(data.value).toBeNull()
    expect(error.value).toBe('')
    expect(onNoData).toHaveBeenCalledTimes(1)
  })
})
