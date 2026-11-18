// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for useAuditApi — GH#7538

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuditApi, useAuditState } from '../useAuditApi'
import { calculateSuccessRate, resolveAuditStatistics } from '@/types/audit'

const mockGet = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: mockGet, post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() }),
}))

vi.mock('@/utils/cacheManagement', () => ({
  showSubtleErrorNotification: vi.fn(),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

vi.mock('@/composables/usePollingJob', () => ({
  usePollingJob: () => ({ start: vi.fn(), stop: vi.fn() }),
}))

vi.mock('@/composables/useLoadingState', () => ({
  useLoadingState: () => ({
    isLoading: { value: false },
    wrap: async (fn: () => Promise<void>) => fn(),
  }),
}))

const FAKE_RESPONSE = {
  success: true,
  total_returned: 2,
  has_more: false,
  entries: [
    { id: '1', operation: 'login', result: 'denied', timestamp: '2026-01-01T00:00:00Z' },
    { id: '2', operation: 'access', result: 'error', timestamp: '2026-01-01T01:00:00Z' },
  ],
  query: {},
}

describe('useAuditApi.getFailedOperations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns the failed-operations list when the API returns data', async () => {
    mockGet.mockResolvedValue(FAKE_RESPONSE)

    const api = useAuditApi()
    const result = await api.getFailedOperations(24, 'denied')

    expect(result).not.toBeNull()
    expect(result!.success).toBe(true)
    expect(result!.entries).toHaveLength(2)
    expect(result!.entries[0].operation).toBe('login')
  })

  it('calls the correct endpoint with hours and result_filter params', async () => {
    mockGet.mockResolvedValue(FAKE_RESPONSE)

    const api = useAuditApi()
    await api.getFailedOperations(48, 'error')

    expect(mockGet).toHaveBeenCalledWith(
      '/api/audit/failures?hours=48&result_filter=error'
    )
  })

  it('returns null when the API call throws', async () => {
    mockGet.mockRejectedValue(new Error('network error'))

    const api = useAuditApi()
    const result = await api.getFailedOperations()

    expect(result).toBeNull()
  })

  it('does NOT call .json() on the response (no double-parse)', async () => {
    const mockResponse = {
      ...FAKE_RESPONSE,
      json: vi.fn(() => Promise.resolve(null)),
    }
    mockGet.mockResolvedValue(mockResponse)

    const api = useAuditApi()
    const result = await api.getFailedOperations()

    expect(mockResponse.json).not.toHaveBeenCalled()
    expect(result!.entries).toHaveLength(2)
  })

  it('uses default params (24h, denied) when called with no arguments', async () => {
    mockGet.mockResolvedValue(FAKE_RESPONSE)

    const api = useAuditApi()
    await api.getFailedOperations()

    expect(mockGet).toHaveBeenCalledWith(
      '/api/audit/failures?hours=24&result_filter=denied'
    )
  })
})

describe('useAuditApi figures over unfinished records (#20665)', () => {
  const row = (id: string, result: string) => ({ id, operation: 'op', result, timestamp: 1 })

  async function loaded(results: string[], statistics?: Record<string, unknown>) {
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/api/audit/statistics')) {
        return Promise.resolve({ success: true, statistics, vm_info: { vm_source: 'x', vm_name: 'y' } })
      }
      return Promise.resolve({
        success: true,
        total_returned: results.length,
        has_more: false,
        entries: results.map((r, i) => row(String(i), r)),
        query: {},
      })
    })
    const api = useAuditState()
    await api.loadLogs()
    if (statistics) await api.loadStatistics()
    return api
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('an attempted row beside a success leaves 100% and no failure', async () => {
    const api = await loaded(['attempted', 'success'])

    expect(api.successRate.value).toBe(100)
    expect(api.failedEntries.value).toHaveLength(0)
  })

  it('an attempted row beside a failure leaves 0% and one failure', async () => {
    const api = await loaded(['attempted', 'failed'])

    expect(api.successRate.value).toBe(0)
    expect(api.failedEntries.value).toHaveLength(1)
  })

  it('a lone attempted row is 0% with no failure', async () => {
    const api = await loaded(['attempted'])

    expect(api.successRate.value).toBe(0)
    expect(api.failedEntries.value).toHaveLength(0)
  })

  it('a statistics object that carries no success_rate does not hide the computed rate', async () => {
    const api = await loaded(['success', 'denied', 'attempted'], { total_entries: 3 })

    expect(api.statistics.value).not.toBeNull()
    expect(api.successRate.value).toBe(50)
  })

  it('a numeric success_rate from the server is honoured', async () => {
    const api = await loaded(['success', 'denied'], { success_rate: 87 })

    expect(api.successRate.value).toBe(87)
  })

  it('a non-finite success_rate from the server falls back to the computed rate', async () => {
    const api = await loaded(['success', 'failed'], { success_rate: NaN })

    expect(api.successRate.value).toBe(50)
  })
})

describe('calculateSuccessRate (#20665)', () => {
  it('is 0 when no row is terminal', () => {
    expect(calculateSuccessRate(0, 0)).toBe(0)
  })

  it('is 33 for 1 of 3', () => {
    expect(calculateSuccessRate(1, 3)).toBe(33)
  })

  it('rounds half up and reaches 100', () => {
    expect(calculateSuccessRate(2, 3)).toBe(67)
    expect(calculateSuccessRate(4, 4)).toBe(100)
  })
})

describe('resolveAuditStatistics (#21513)', () => {
  const rows = (...results: string[]) => results.map((result) => ({ result }))

  it('is null with neither a statistics object nor a row', () => {
    expect(resolveAuditStatistics(null, [])).toBeNull()
  })

  it('uses the server counts and rate as sent, whatever the loaded rows hold', () => {
    const out = resolveAuditStatistics(
      { total_entries: 500, success_count: 400, denied_count: 50, failed_count: 30, error_count: 20, success_rate: 80 },
      rows('failed')
    )
    expect(out).toMatchObject({
      total_entries: 500, success_count: 400, denied_count: 50, failed_count: 30, error_count: 20, success_rate: 80,
    })
  })

  it('derives every figure the server did not send from the rows', () => {
    const out = resolveAuditStatistics({}, rows('success', 'success', 'denied', 'failed', 'error', 'attempted'))
    expect(out).toMatchObject({
      total_entries: 6, success_count: 2, denied_count: 1, failed_count: 1, error_count: 1,
    })
    // 2 of the 5 final rows: the attempted row is not in the denominator
    expect(out?.success_rate).toBe(40)
  })

  it('counts an attempted row as neither a success nor a failure', () => {
    const out = resolveAuditStatistics(null, rows('attempted', 'success'))
    expect(out).toMatchObject({ success_count: 1, failed_count: 0, denied_count: 0, error_count: 0, success_rate: 100 })
  })

  it('mixes a served figure with derived ones and ignores a non-finite served figure', () => {
    const out = resolveAuditStatistics({ success_count: 9, failed_count: NaN } as never, rows('failed', 'success'))
    expect(out).toMatchObject({ success_count: 9, failed_count: 1 })
  })
})

describe('resolveAuditStatistics consistency (#21520 review)', () => {
  it('derives a missing rate from the served counts, not the loaded rows', () => {
    const out = resolveAuditStatistics(
      { success_count: 90, denied_count: 5, failed_count: 5, error_count: 0 },
      [{ result: 'failed' }, { result: 'failed' }]
    )
    expect(out?.success_rate).toBe(90)
  })

  it('lets an explicit null/undefined collection fall back to the safe default', () => {
    const out = resolveAuditStatistics(
      { top_users: null, top_operations: undefined, operations_by_type: null, entries_by_hour: null } as never,
      []
    )
    expect(out).toMatchObject({ top_users: [], top_operations: [], operations_by_type: {}, entries_by_hour: {} })
  })
})

describe('useAuditState.resolvedStatistics (#21513)', () => {
  function stub(results: string[], statistics?: Record<string, unknown>) {
    mockGet.mockImplementation((url: string) =>
      Promise.resolve(
        url.startsWith('/api/audit/statistics')
          ? { success: true, statistics, vm_info: { vm_source: 'x', vm_name: 'y' } }
          : {
              success: true, total_returned: results.length, has_more: false, query: {},
              entries: results.map((result, i) => ({ id: String(i), operation: 'op', result, timestamp: 1 })),
            }
      )
    )
  }

  it('shows the server counts when the response carries them', async () => {
    stub(['failed'], { total_entries: 90, success_count: 80, denied_count: 4, failed_count: 5, error_count: 1, success_rate: 89 })
    const api = useAuditState()
    await api.loadLogs()
    await api.loadStatistics()
    expect(api.resolvedStatistics.value).toMatchObject({ total_entries: 90, success_count: 80, failed_count: 5, success_rate: 89 })
  })

  it('counts a timed_out row as a final outcome in a row-derived rate (attempted stays out)', async () => {
    stub(['success', 'timed_out', 'attempted'])
    const api = useAuditState()
    await api.loadLogs()
    await api.loadStatistics()
    expect(api.resolvedStatistics.value).toMatchObject({ success_count: 1, success_rate: 50 })
  })

  it('keeps a failed statistics request distinguishable from row-only estimates, and clears it on retry', async () => {
    stub(['success'], { total_entries: 1 })
    const api = useAuditState()
    await api.loadLogs()
    mockGet.mockImplementationOnce(() => Promise.reject(new Error('503')))
    await api.loadStatistics()
    expect(api.statisticsFailed.value).toBe(true)
    expect(api.resolvedStatistics.value).toMatchObject({ success_count: 1, success_rate: 100 })
    await api.loadStatistics()
    expect(api.statisticsFailed.value).toBe(false)
  })

  it('keeps the failures-only response out of the entries the dashboard derives from', async () => {
    stub(['success', 'denied'])
    const api = useAuditState()
    await api.loadLogs()
    mockGet.mockImplementationOnce(() =>
      Promise.resolve({ success: true, total_returned: 1, has_more: false, query: {}, entries: [{ id: 'f', operation: 'op', result: 'denied', timestamp: 1 }] })
    )
    await api.loadFailedOperations(24)
    expect(api.failureEntries.value).toHaveLength(1)
    expect(api.entries.value).toHaveLength(2)
    expect(api.resolvedStatistics.value).toMatchObject({ success_rate: 50 })
  })

  it('derives the counts from the entries when the response carries none', async () => {
    stub(['success', 'denied', 'attempted'], { total_entries: 3 })
    const api = useAuditState()
    await api.loadLogs()
    await api.loadStatistics()
    expect(api.resolvedStatistics.value).toMatchObject({
      total_entries: 3, success_count: 1, denied_count: 1, failed_count: 0, error_count: 0, success_rate: 50,
    })
  })
})
