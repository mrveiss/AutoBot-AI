// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #20498: loadCodeQuality fills the overview from the real response
 * shapes, and reports a failed fetch as "not available" (null), never 0.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const responses = vi.hoisted(() => ({ byPath: {} as Record<string, unknown> }))

vi.mock('@/composables/api/useFetchEndpoint', () => ({
  useFetchEndpoint: (cfg: { path: string }) => {
    const data = ref<unknown>(null)
    return {
      load: vi.fn(async () => { data.value = responses.byPath[cfg.path] ?? null }),
      data,
      error: ref(''),
      loading: ref(false),
    }
  },
}))

import { useDashboardLoaders } from '../useDashboardLoaders'

const make = () => useDashboardLoaders({ withSourceId: (u) => u, additionalRefreshCallbacks: () => [] })

describe('useDashboardLoaders.loadCodeQuality (#20498)', () => {
  beforeEach(() => { responses.byPath = {} })

  // Pre-fix: overall_score was the performance breakdown (90) and technical_debt 0.
  it('populates the state from the endpoints\' real response shapes', async () => {
    responses.byPath = {
      '/api/quality/health-score': {
        status: 'success', overall: 72.4, grade: 'C', trend: 'stable',
        breakdown: { testability: 61.2, performance: 90 },
      },
      '/api/debt/summary': { status: 'success', summary: { total_items: 40, total_hours: 123.5 } },
      '/api/analytics/codebase/duplicates/cached': { status: 'success', total_count: 7 },
    }
    const loaders = make()
    await loaders.loadCodeQuality()
    expect(loaders.codeQuality.value).toEqual({
      overall_score: 72,
      test_coverage: 61,
      code_duplicates: 7,
      technical_debt: 123.5,
    })
  })

  // Pre-fix: every field fell back to 0 (and test_coverage to 50).
  it('every endpoint failing yields four nulls, not zeros', async () => {
    const loaders = make()
    await loaders.loadCodeQuality()
    expect(loaders.codeQuality.value).toEqual({
      overall_score: null,
      test_coverage: null,
      code_duplicates: null,
      technical_debt: null,
    })
  })
})
