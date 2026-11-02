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

import { usePatternAnalysis } from './usePatternAnalysis'

const CACHED = '/api/analytics/codebase/patterns/cached-summary'

describe('usePatternAnalysis failure reporting (#17651)', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
  })

  it('loadCachedData reports a failed cached-summary read as an error', async () => {
    apiGet.mockImplementation(async (url: string) => {
      if (url === CACHED) throw new Error('cached summary unavailable')
      return { status: 'success', stats: null }
    })
    const { loadCachedData, error, hasResults } = usePatternAnalysis()

    expect(await loadCachedData()).toBe(false)
    expect(error.value).toContain('cached summary unavailable')
    expect(hasResults.value).toBe(false)
  })

  it('loadCachedData with nothing cached is empty, not an error', async () => {
    apiGet.mockImplementation(async (url: string) =>
      url === CACHED ? { status: 'no_data', has_cached_data: false } : { status: 'success', stats: null },
    )
    const { loadCachedData, error } = usePatternAnalysis()

    expect(await loadCachedData()).toBe(false)
    expect(error.value).toBeNull()
  })

  it('clearStorage reports a failed clear', async () => {
    apiPost.mockRejectedValue(new Error('clear refused'))
    const { clearStorage, error } = usePatternAnalysis()

    expect(await clearStorage()).toBe(false)
    expect(error.value).toContain('clear refused')
  })

  it('getReport reports a failed fetch', async () => {
    apiGet.mockRejectedValue(new Error('report down'))
    const { getReport, error } = usePatternAnalysis()

    expect(await getReport()).toBeNull()
    expect(error.value).toContain('report down')
  })
})
