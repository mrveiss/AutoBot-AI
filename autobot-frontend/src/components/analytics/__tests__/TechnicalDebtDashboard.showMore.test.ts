// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #12741: the Quick Wins "Show more" button on the mounted dashboard asks the composable for the
 * next ROI page, and the list grows to what it returns.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const item = (id: number) => ({
  id: String(id), file_path: `src/f${id}.ts`, category: 'code_complexity', severity: 'low', description: `d${id}`,
  estimated_hours: 1, impact_score: 5, roi_score: 2, created_at: '2026-01-01',
})
const items = (n: number) => Array.from({ length: n }, (_, i) => item(i))

const { loadMoreRoi } = vi.hoisted(() => ({ loadMoreRoi: vi.fn() }))
vi.mock('@/composables/analytics/useTechnicalDebtData', async () => {
  const { ref } = await import('vue')
  return {
    ROI_PAGE: 10,
    useTechnicalDebtData: () => ({
      fetchSummary: vi.fn(async () => ({ summary: { total_items: 0, total_hours: 0, estimated_cost: 0, critical_count: 0, health_score: 100, trend: 0 } })),
      fetchCategoryBreakdown: vi.fn(async () => []),
      fetchRoiPriorities: vi.fn(async () => items(10)),
      roiTotal: ref(25),
      roiAtCap: ref(false),
      loadMoreRoi,
      fetchDebtItems: vi.fn(async () => []),
      fetchTrends: vi.fn(async () => []),
      fetchReportBlob: vi.fn(),
    }),
  }
})

import TechnicalDebtDashboard from '../TechnicalDebtDashboard.vue'

describe('TechnicalDebtDashboard ROI "Show more" (#12741)', () => {
  it('the show-more button calls loadMoreRoi and renders the larger page', async () => {
    loadMoreRoi.mockResolvedValue(items(20))
    const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
    const w = mount(TechnicalDebtDashboard, { global: { plugins: [i18n], stubs: { BaseModal: true } } })
    await flushPromises()
    expect(w.findAll('.priority-item')).toHaveLength(10)

    await w.get('.priorities-panel [data-testid="truncation-show-more"]').trigger('click')
    await flushPromises()
    expect(loadMoreRoi).toHaveBeenCalledTimes(1)
    expect(w.findAll('.priority-item')).toHaveLength(20)
  })
})
