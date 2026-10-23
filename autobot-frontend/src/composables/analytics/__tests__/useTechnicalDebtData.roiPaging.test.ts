// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #12741: /api/debt/roi-priorities is capped on the server (`limit`, at most 100) and reports
 * `total_available`. "Show more" on the ROI list therefore asks the server for a larger page, and
 * the composable must hand the dashboard the real total so the count text stays honest.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useTechnicalDebtData } from '../useTechnicalDebtData'

vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/AppConfig.js', () => ({ default: { getServiceUrl: vi.fn(async () => 'http://backend') } }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ post: vi.fn(), get: vi.fn() }) }))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
const mockFetch = fetchWithAuth as unknown as ReturnType<typeof vi.fn>

const page = (n: number, total: number) => ({
  ok: true,
  status: 200,
  json: async () => ({ status: 'success', priorities: Array.from({ length: n }, (_, i) => ({ id: String(i) })), total_available: total }),
  text: async () => '',
})

describe('useTechnicalDebtData ROI paging (#12741)', () => {
  beforeEach(() => mockFetch.mockReset())

  it('requests the given limit and exposes total_available', async () => {
    mockFetch.mockResolvedValueOnce(page(10, 240))
    const { fetchRoiPriorities, roiTotal } = useTechnicalDebtData()
    const first = await fetchRoiPriorities(10)
    expect(first).toHaveLength(10)
    expect(roiTotal.value).toBe(240)
    expect(String(mockFetch.mock.calls[0][0])).toContain('limit=10')

    mockFetch.mockResolvedValueOnce(page(20, 240))
    const second = await fetchRoiPriorities(20)
    expect(second).toHaveLength(20)
    expect(String(mockFetch.mock.calls[1][0])).toContain('limit=20')
    expect(roiTotal.value).toBe(240)
  })
})
