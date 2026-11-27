// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** #22198: with no source in the route, the debt composable makes no request at all. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useTechnicalDebtData } from '../useTechnicalDebtData'

vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/AppConfig.js', () => ({ default: { getServiceUrl: vi.fn(async () => 'http://backend') } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {} }) }))
const post = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ post, get: vi.fn() }) }))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
const mockFetch = fetchWithAuth as unknown as ReturnType<typeof vi.fn>

describe('useTechnicalDebtData without a source (#22198)', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    post.mockReset()
  })

  it('fetches nothing for any debt route', async () => {
    const d = useTechnicalDebtData()
    await d.fetchSummary()
    await d.fetchCategoryBreakdown()
    await d.fetchRoiPriorities(10)
    await d.fetchTrends('30d')
    await d.fetchReportBlob()
    expect(await d.fetchDebtItems()).toEqual([])
    expect(mockFetch).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })
})
