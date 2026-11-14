// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for useAuditApi — GH#7538

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuditApi } from '../useAuditApi'

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
    const api = useAuditApi()
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
})
