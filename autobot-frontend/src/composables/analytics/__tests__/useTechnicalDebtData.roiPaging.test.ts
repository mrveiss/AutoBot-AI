// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #12741: /api/debt/roi-priorities is capped on the server (`limit`, at most 100) and reports
 * `total_available`. "Show more" on the ROI list therefore asks the server for a larger page, and
 * the composable must hand the dashboard the real total so the count text stays honest.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { useTechnicalDebtData, ROI_MAX } from '../useTechnicalDebtData'
import TruncationNotice from '@/components/analytics/TruncationNotice.vue'
import en from '@/i18n/locales/en.json'

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

  it('paging stops at the 100 cap and the notice turns into the server-limited note', async () => {
    const { fetchRoiPriorities, loadMoreRoi, roiAtCap, roiTotal } = useTechnicalDebtData()
    mockFetch.mockResolvedValueOnce(page(90, 240))
    await fetchRoiPriorities(90)
    expect(roiAtCap.value).toBe(false)

    mockFetch.mockResolvedValue(page(ROI_MAX, 240))
    const atCap = await loadMoreRoi()
    expect(String(mockFetch.mock.calls[1][0])).toContain(`limit=${ROI_MAX}`)
    expect(roiAtCap.value).toBe(true)
    await loadMoreRoi()
    expect(String(mockFetch.mock.calls[2][0])).toContain(`limit=${ROI_MAX}`) // never past the cap

    const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
    const notice = mount(TruncationNotice, {
      props: { shown: atCap.length, total: roiTotal.value, step: 10, serverLimited: roiAtCap.value },
      global: { plugins: [i18n] },
    })
    expect(notice.find('button').exists()).toBe(false)
    expect(notice.get('[data-testid="truncation-server-limited"]').text()).toBe(
      en.analytics.truncation.serverLimited.replace('{shown}', '100').replace('{total}', '240'),
    )
  })

  it('a failed "show more" keeps the previous list and retries the same page', async () => {
    const { fetchRoiPriorities, loadMoreRoi } = useTechnicalDebtData()
    mockFetch.mockResolvedValueOnce(page(10, 240))
    const first = await fetchRoiPriorities(10)

    mockFetch.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}), text: async () => '' })
    const afterError = await loadMoreRoi()
    expect(afterError).toEqual(first)
    expect(afterError).toHaveLength(10)

    mockFetch.mockResolvedValueOnce(page(20, 240))
    expect(await loadMoreRoi()).toHaveLength(20)
    // The failed call did not advance the page: the retry asks for 20 again, not 30.
    expect(String(mockFetch.mock.calls[2][0])).toContain('limit=20')
  })
})
