// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * A failed pattern-analysis read must surface as `error`, never as the
 * "no analysis yet" empty state (#17651).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const apiGet = vi.fn()
const apiPost = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: { get: (...a: unknown[]) => apiGet(...a), post: (...a: unknown[]) => apiPost(...a) },
}))
// The UI kit's barrel pulls component dependencies this composable never uses.
vi.mock('@autobot/ui', () => ({
  getEnvPositiveInt: (_env: unknown, _key: string, fallback: number) => fallback,
  isHttpError: () => false,
  usePollingJob: () => ({ start: vi.fn(), stop: vi.fn() }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/AppConfig.js', () => ({ default: { getServiceUrl: vi.fn(async () => 'http://backend.test') } }))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { usePatternAnalysis } from './usePatternAnalysis'

const mockedFetch = vi.mocked(fetchWithAuth)

const SOURCE = 'src-a'
// The selected source's id, added the way `withSourceId` does (#20513).
const withSourceId = (url: string) => `${url}${url.includes('?') ? '&' : '?'}source_id=${SOURCE}`
const CACHED = withSourceId('/api/analytics/codebase/patterns/cached-summary')

describe('usePatternAnalysis failure reporting (#17651)', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
    mockedFetch.mockReset()
  })

  it('loadCachedData reports a failed cached-summary read as an error', async () => {
    apiGet.mockImplementation(async (url: string) => {
      if (url === CACHED) throw new Error('cached summary unavailable')
      return { status: 'success', stats: null }
    })
    const { loadCachedData, error, hasResults } = usePatternAnalysis(withSourceId)

    expect(await loadCachedData()).toBe(false)
    expect(error.value).toContain('cached summary unavailable')
    expect(hasResults.value).toBe(false)
  })

  it('loadCachedData with nothing cached is empty, not an error', async () => {
    apiGet.mockImplementation(async (url: string) =>
      url === CACHED ? { status: 'no_data', has_cached_data: false } : { status: 'success', stats: null },
    )
    const { loadCachedData, error } = usePatternAnalysis(withSourceId)

    expect(await loadCachedData()).toBe(false)
    expect(error.value).toBeNull()
  })

  it('clearStorage reports a failed clear', async () => {
    // storage/clear goes through useFetchEndpoint, so it is fetchWithAuth that fails.
    mockedFetch.mockRejectedValue(new Error('clear refused'))
    const { clearStorage, error } = usePatternAnalysis(withSourceId)

    expect(await clearStorage()).toBe(false)
    expect(error.value).toContain('clear refused')
  })

  it('getReport reports a failed fetch', async () => {
    mockedFetch.mockRejectedValue(new Error('report down'))
    const { getReport, error } = usePatternAnalysis(withSourceId)

    expect(await getReport()).toBeNull()
    expect(error.value).toContain('report down')
  })

  it('storage stats and clear are requested for the selected source through useFetchEndpoint (#20513)', async () => {
    const json = (body: unknown) =>
      new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    mockedFetch.mockResolvedValueOnce(json({ status: 'success', stats: { total_patterns: 3 } }))
    const { getStorageStats, clearStorage, storageStats } = usePatternAnalysis(withSourceId)

    await getStorageStats()
    expect(mockedFetch.mock.calls[0]?.[0]).toBe(
      'http://backend.test/api/analytics/codebase/patterns/storage/stats?source_id=src-a',
    )
    expect(storageStats.value).toEqual({ total_patterns: 3 })

    mockedFetch.mockResolvedValueOnce(json({ message: 'cleared' }))
    expect(await clearStorage()).toBe(true)
    const [clearUrl, init] = mockedFetch.mock.calls[1] as [string, RequestInit]
    expect(clearUrl).toBe('http://backend.test/api/analytics/codebase/patterns/storage/clear?source_id=src-a')
    expect(init.method).toBe('POST')
    expect(storageStats.value).toBeNull()
  })

  it('the report is read for the selected source through useFetchEndpoint, with its path (#20513)', async () => {
    mockedFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'success', report: '# r' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { getReport } = usePatternAnalysis(withSourceId)

    expect(await getReport('src/a b')).toBe('# r')
    expect(mockedFetch.mock.calls[0]?.[0]).toBe(
      'http://backend.test/api/analytics/codebase/patterns/report?source_id=src-a&path=src%2Fa%20b',
    )
  })

  it('with no source selected nothing is requested (the routes answer 422 without one, #20513)', async () => {
    const { loadCachedData, getReport, clearStorage } = usePatternAnalysis((url: string) => url)

    expect(await loadCachedData()).toBe(false)
    expect(await getReport()).toBeNull()
    expect(await clearStorage()).toBe(false)
    expect(apiGet).not.toHaveBeenCalled()
    expect(apiPost).not.toHaveBeenCalled()
    expect(mockedFetch).not.toHaveBeenCalled()
  })
})
