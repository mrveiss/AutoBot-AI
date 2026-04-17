// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Unit tests for useAnalyticsEndpoint.
 *
 * Issue #5112.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetchWithAuth (the composable calls it instead of raw fetch).
vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn(),
}))

// Mock AppConfig.getServiceUrl so tests don't hit service discovery.
vi.mock('@/config/AppConfig.js', () => ({
  default: {
    getServiceUrl: vi.fn(async () => 'http://backend.test'),
  },
}))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { useAnalyticsEndpoint } from './useAnalyticsEndpoint'

const mockedFetch = vi.mocked(fetchWithAuth)

const withSourceId = vi.fn(
  (u: string) => (u.includes('?') ? `${u}&source_id=s1` : `${u}?source_id=s1`),
)

interface RawStats {
  status: 'success' | 'no_data'
  stats?: { total: number }
}

interface Stats {
  total: number
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('useAnalyticsEndpoint', () => {
  beforeEach(() => {
    mockedFetch.mockReset()
    withSourceId.mockClear()
  })

  it('loads data on success and cycles loading', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ status: 'success', stats: { total: 42 } }),
    )

    const onSuccess = vi.fn()
    const { data, loading, error, load } = useAnalyticsEndpoint<
      RawStats,
      Stats
    >(
      {
        path: '/api/analytics/codebase/stats',
        pickData: (raw) =>
          raw.status === 'success' && raw.stats ? raw.stats : null,
        onSuccess,
      },
      { withSourceId },
    )

    expect(loading.value).toBe(false)
    const p = load()
    expect(loading.value).toBe(true)
    await p

    expect(loading.value).toBe(false)
    expect(error.value).toBe('')
    expect(data.value).toEqual({ total: 42 })
    expect(onSuccess).toHaveBeenCalledWith(
      { total: 42 },
      { status: 'success', stats: { total: 42 } },
    )
  })

  it('handles no_data (pickData returns null) without setting error', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ status: 'no_data' }),
    )
    const onNoData = vi.fn()
    const { data, error, load } = useAnalyticsEndpoint<RawStats, Stats>(
      {
        path: '/api/analytics/codebase/stats',
        pickData: (raw) =>
          raw.status === 'success' && raw.stats ? raw.stats : null,
        onNoData,
      },
      { withSourceId },
    )

    await load()

    expect(data.value).toBeNull()
    expect(error.value).toBe('')
    expect(onNoData).toHaveBeenCalledTimes(1)
  })

  it('populates error on non-ok HTTP status and leaves data null', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({}, 500))
    const onError = vi.fn()

    const { data, error, load } = useAnalyticsEndpoint<RawStats, Stats>(
      {
        path: '/api/analytics/codebase/stats',
        pickData: (raw) =>
          raw.status === 'success' && raw.stats ? raw.stats : null,
        onError,
        label: 'Stats endpoint',
      },
      { withSourceId },
    )

    await load()

    expect(data.value).toBeNull()
    expect(error.value).toContain('Stats endpoint returned 500')
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('populates error on network/fetch rejection', async () => {
    mockedFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    const { data, error, load } = useAnalyticsEndpoint<RawStats, Stats>(
      {
        path: '/api/analytics/codebase/stats',
        pickData: (raw) =>
          raw.status === 'success' && raw.stats ? raw.stats : null,
      },
      { withSourceId },
    )

    await load()

    expect(data.value).toBeNull()
    expect(error.value).toContain('Failed to fetch')
  })

  it('applies withSourceId by default (scopeToSource opt-out)', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ status: 'success', stats: { total: 1 } }),
    )
    const { load } = useAnalyticsEndpoint<RawStats, Stats>(
      {
        path: '/api/analytics/codebase/stats',
        pickData: (raw) =>
          raw.status === 'success' && raw.stats ? raw.stats : null,
      },
      { withSourceId },
    )

    await load()

    expect(withSourceId).toHaveBeenCalledTimes(1)
    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toContain('source_id=s1')
  })

  it('scopeToSource=false bypasses withSourceId', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ status: 'success', stats: { total: 1 } }),
    )
    const { load } = useAnalyticsEndpoint<RawStats, Stats>(
      {
        path: '/api/unified/report',
        scopeToSource: false,
        pickData: (raw) =>
          raw.status === 'success' && raw.stats ? raw.stats : null,
      },
      { withSourceId },
    )

    await load()

    expect(withSourceId).not.toHaveBeenCalled()
    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toBe('http://backend.test/api/unified/report')
  })

  it('appends queryExtras to the URL', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ status: 'success', stats: { total: 1 } }),
    )
    const { load } = useAnalyticsEndpoint<RawStats, Stats>(
      {
        path: '/api/analytics/codebase/stats',
        pickData: (raw) =>
          raw.status === 'success' && raw.stats ? raw.stats : null,
      },
      { withSourceId },
    )

    await load({ problem_type: 'race_condition', limit: '50' })

    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toContain('problem_type=race_condition')
    expect(url).toContain('limit=50')
    // still scoped
    expect(url).toContain('source_id=s1')
  })

  it('skips empty queryExtras entries', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ status: 'success', stats: { total: 1 } }),
    )
    const { load } = useAnalyticsEndpoint<RawStats, Stats>(
      {
        path: '/api/analytics/codebase/stats',
        scopeToSource: false,
        pickData: (raw) =>
          raw.status === 'success' && raw.stats ? raw.stats : null,
      },
      { withSourceId },
    )

    await load({ empty: '', also_empty: '' })

    const url = mockedFetch.mock.calls[0]?.[0] as string
    expect(url).toBe('http://backend.test/api/analytics/codebase/stats')
  })
})
