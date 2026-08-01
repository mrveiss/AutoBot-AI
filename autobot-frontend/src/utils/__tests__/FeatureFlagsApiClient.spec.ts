// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * FeatureFlagsApiClient tests (#12152)
 *
 * Verifies the client routes every request through the shared apiClient
 * singleton (so it inherits expiry-aware auth + 401 auto-logout + retry)
 * instead of its own fetchWithAuth/base-URL plumbing.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    rawRequest: vi.fn(),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

import apiClient from '@/utils/ApiClient'
import { featureFlagsApiClient } from '../FeatureFlagsApiClient'

function mockResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(body),
  }
}

describe('FeatureFlagsApiClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('getFeatureFlagsStatus issues a GET against apiClient.rawRequest', async () => {
    const status = {
      current_mode: 'log_only',
      history: [],
      endpoint_overrides: {},
      total_endpoints_configured: 3,
    }
    vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse(status))

    const result = await featureFlagsApiClient.getFeatureFlagsStatus()

    expect(apiClient.rawRequest).toHaveBeenCalledWith('/api/admin/feature-flags/status', {})
    // On success this client returns the backend body directly (pre-existing
    // shape — the backend response already conforms to ApiResponse<T>).
    expect(result).toEqual(status)
  })

  it('updateEnforcementMode PUTs the raw { mode } object (apiClient stringifies it)', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse({ new_mode: 'enforced', updated_by: 'admin', updated_at: '2026-07-23T00:00:00Z' })
    )

    await featureFlagsApiClient.updateEnforcementMode('enforced')

    expect(apiClient.rawRequest).toHaveBeenCalledWith('/api/admin/feature-flags/enforcement-mode', {
      method: 'PUT',
      body: { mode: 'enforced' },
    })
  })

  it('setEndpointEnforcement URL-encodes the endpoint and PUTs { mode }', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse({ endpoint: '/api/chat', mode: 'log_only' })
    )

    await featureFlagsApiClient.setEndpointEnforcement('/api/chat', 'log_only')

    expect(apiClient.rawRequest).toHaveBeenCalledWith(
      '/api/admin/feature-flags/endpoint/%2Fapi%2Fchat',
      { method: 'PUT', body: { mode: 'log_only' } }
    )
  })

  it('removeEndpointEnforcement issues a DELETE with no body', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse({ endpoint: '/api/chat', reverted_to: 'disabled' })
    )

    await featureFlagsApiClient.removeEndpointEnforcement('/api/chat')

    expect(apiClient.rawRequest).toHaveBeenCalledWith(
      '/api/admin/feature-flags/endpoint/%2Fapi%2Fchat',
      { method: 'DELETE' }
    )
  })

  it('translates a non-ok response into ApiResponse.success = false with the backend error', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse({ detail: 'admin only' }, false, 403)
    )

    const result = await featureFlagsApiClient.getFeatureFlagsStatus()

    expect(result).toEqual({ success: false, error: 'admin only' })
  })

  it('translates a thrown/network error into ApiResponse.success = false', async () => {
    vi.mocked(apiClient.rawRequest).mockRejectedValue(new Error('Request timeout after 30000ms'))

    const result = await featureFlagsApiClient.getFeatureFlagsStatus()

    expect(result).toEqual({ success: false, error: 'Request timeout after 30000ms' })
  })

  it('getAccessControlMetrics builds the query string and issues a GET', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse({ total_violations: 0, period_days: 7, by_endpoint: {}, by_user: {}, by_day: {}, current_mode: 'log_only' })
    )

    await featureFlagsApiClient.getAccessControlMetrics({ days: 14, include_details: true })

    expect(apiClient.rawRequest).toHaveBeenCalledWith(
      '/api/admin/access-control/metrics?days=14&include_details=true',
      {}
    )
  })
})
