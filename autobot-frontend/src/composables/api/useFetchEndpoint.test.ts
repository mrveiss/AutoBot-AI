// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Unit tests for useFetchEndpoint.
 *
 * Covers:
 *   - default behavior: `deps` optional, `scopeToSource` defaults FALSE
 *   - explicit opt-in: `scopeToSource: true` + deps.withSourceId wraps the URL
 *   - fallback to identity when scopeToSource=true without a withSourceId
 *   - HTTP methods: GET (default), POST + body factory, DELETE + body
 *   - loading/error/data lifecycle, onSuccess/onNoData/onError hooks
 *   - queryExtras appending + empty-value skipping
 *
 * Issues #5153 (umbrella), #5174 (consolidated from the deleted analytics
 * alias test file).
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

  it('cycles loading: false -> true -> false across load()', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 1 }),
    )
    const { loading, load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/anything',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
    })
    expect(loading.value).toBe(false)
    const p = load()
    expect(loading.value).toBe(true)
    await p
    expect(loading.value).toBe(false)
  })

  it('onSuccess receives both picked data AND the raw envelope', async () => {
    const rawEnvelope = { ok: true, value: 7 }
    mockedFetch.mockResolvedValueOnce(jsonResponse(rawEnvelope))
    const onSuccess = vi.fn()
    const { load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/anything',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      onSuccess,
    })
    await load()
    // Third arg is the optional request context (undefined when load() is
    // called without one) — see onSuccess?: (data, raw, context) in the API.
    expect(onSuccess).toHaveBeenCalledWith(7, rawEnvelope, undefined)
  })

  it('DELETE method routes correctly and supports a body', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 3 }),
    )
    const { load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/analytics/codebase/cache',
      method: 'DELETE',
      body: () => ({ reason: 'manual' }),
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
    })
    await load()
    const init = mockedFetch.mock.calls[0]?.[1] as RequestInit | undefined
    expect(init?.method).toBe('DELETE')
    expect(init?.body).toBe(JSON.stringify({ reason: 'manual' }))
  })

  it('DELETE without a body sends no body', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 1 }),
    )
    const { load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/thing/123',
      method: 'DELETE',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
    })
    await load()
    const init = mockedFetch.mock.calls[0]?.[1] as RequestInit | undefined
    expect(init?.method).toBe('DELETE')
    expect(init?.body).toBeUndefined()
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

  // ───────── #5235: onResponse hook + reset() ─────────

  it('onResponse return string overrides the default `${label} returned ${status}` error message', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({}, 504))
    const { error, load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/slow',
      label: 'Slow endpoint',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      onResponse: (response) =>
        response.status === 504
          ? 'Analysis timed out -- codebase too large for real-time scan'
          : undefined,
    })
    await load()
    expect(error.value).toBe(
      'Analysis timed out -- codebase too large for real-time scan',
    )
  })

  it('onResponse async return (e.g. parses `{ detail }` JSON body) is awaited', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ detail: 'Backend rejected: rootPath not indexed' }, 400),
    )
    const { error, load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/analyze',
      label: 'Analyze endpoint',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      onResponse: async (response) => {
        const body = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null
        return body?.detail
      },
    })
    await load()
    expect(error.value).toBe('Backend rejected: rootPath not indexed')
  })

  it('onResponse returning undefined falls through to the default error format', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({}, 500))
    const { error, load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/boom',
      label: 'Boom endpoint',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      onResponse: () => undefined,
    })
    await load()
    expect(error.value).toBe('Boom endpoint returned 500')
  })

  it('onResponse is NOT called on a successful (ok=true) response', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 42 }),
    )
    const onResponse = vi.fn()
    const { data, load } = useFetchEndpoint<RawPayload, number>({
      path: '/api/ok',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
      onResponse,
    })
    await load()
    expect(data.value).toBe(42)
    expect(onResponse).not.toHaveBeenCalled()
  })

  it('reset() clears data, loading, and error back to initial state', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({}, 500))
    const { data, error, load, reset } = useFetchEndpoint<RawPayload, number>({
      path: '/api/boom',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
    })
    await load()
    expect(error.value).not.toBe('')
    reset()
    expect(error.value).toBe('')
    expect(data.value).toBeNull()
  })

  it('reset() after a successful load clears data', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ ok: true, value: 99 }),
    )
    const { data, load, reset } = useFetchEndpoint<RawPayload, number>({
      path: '/api/ok',
      pickData: (raw) => (raw.ok ? (raw.value ?? null) : null),
    })
    await load()
    expect(data.value).toBe(99)
    reset()
    expect(data.value).toBeNull()
  })
})
