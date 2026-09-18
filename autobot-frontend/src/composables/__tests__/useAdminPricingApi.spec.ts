// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for useAdminPricingApi — #16825.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAdminPricingApi } from '../useAdminPricingApi'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({
    get: mockGet,
    post: mockPost,
    put: mockPut,
    delete: mockDelete,
    patch: vi.fn(),
  }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() }),
}))

describe('useAdminPricingApi.fetchStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls GET /api/admin/pricing/status', async () => {
    mockGet.mockResolvedValue({ providers: {} })
    const { fetchStatus } = useAdminPricingApi()
    await fetchStatus()
    expect(mockGet).toHaveBeenCalledWith('/api/admin/pricing/status')
  })

  it('returns the providers map', async () => {
    const providers = {
      openai: { last_attempt_at: '2026-01-01T00:00:00Z', last_refresh_at: '2026-01-01T00:00:00Z', success: true, model_count: 12 },
    }
    mockGet.mockResolvedValue({ providers })
    const { fetchStatus } = useAdminPricingApi()
    const result = await fetchStatus()
    expect(result).toEqual(providers)
  })

  it('returns an empty object (not null) when the API call throws', async () => {
    mockGet.mockRejectedValue(new Error('network error'))
    const { fetchStatus } = useAdminPricingApi()
    const result = await fetchStatus()
    expect(result).toEqual({})
  })

  it('tolerates a response missing the providers field', async () => {
    mockGet.mockResolvedValue({})
    const { fetchStatus } = useAdminPricingApi()
    const result = await fetchStatus()
    expect(result).toEqual({})
  })
})

describe('useAdminPricingApi.refreshNow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls POST /api/admin/pricing/refresh', async () => {
    mockPost.mockResolvedValue({ sources: {}, written: 5, indexed: 5 })
    const { refreshNow } = useAdminPricingApi()
    const result = await refreshNow()
    expect(mockPost).toHaveBeenCalledWith('/api/admin/pricing/refresh')
    expect(result.written).toBe(5)
  })
})

describe('useAdminPricingApi.setOverride / deleteOverride', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('PUTs an override to the provider/model path, URL-encoded', async () => {
    mockPut.mockResolvedValue({})
    const { setOverride } = useAdminPricingApi()
    await setOverride('open ai', 'gpt-4o', { input_per_1m: 1, output_per_1m: 2 })
    expect(mockPut).toHaveBeenCalledWith(
      '/api/admin/pricing/open%20ai/gpt-4o',
      { input_per_1m: 1, output_per_1m: 2 },
    )
  })

  it('DELETEs an override at the provider/model path', async () => {
    mockDelete.mockResolvedValue({})
    const { deleteOverride } = useAdminPricingApi()
    await deleteOverride('anthropic', 'claude-3-5-sonnet')
    expect(mockDelete).toHaveBeenCalledWith('/api/admin/pricing/anthropic/claude-3-5-sonnet')
  })
})
