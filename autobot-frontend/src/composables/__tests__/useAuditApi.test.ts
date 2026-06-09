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
