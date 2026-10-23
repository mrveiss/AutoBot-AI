// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'

const scanFile = vi.fn()

vi.mock('@/composables/useCodeIntelligence', () => ({
  useCodeIntelligence: () => ({
    isLoading: ref(false),
    suggestions: ref([]),
    healthScore: ref(null),
    qualityScore: ref(null),
    analysisHistory: ref([]),
    analyzeCode: vi.fn(),
    getSuggestions: vi.fn(),
    getHealthScore: vi.fn(),
    getQualityScore: vi.fn(),
    getAnalysisHistory: vi.fn(),
    scanFile: (...args: unknown[]) => scanFile(...args),
  }),
}))

import { useCodeIntelAnalysis } from '../useCodeIntelAnalysis'

const types = { security: true, performance: true, redis: true }

function setup() {
  const notify = vi.fn()
  const deps = {
    rootPath: ref('/src'),
    sourceIdParam: computed(() => ''),
    sourceIdQuery: computed(() => ({})),
    withSourceId: (url: string) => url,
    analyzing: ref(false),
    t: (key: string) => key,
    showToast: vi.fn(),
    notify,
  }
  return { notify, analysis: useCodeIntelAnalysis(deps) }
}

describe('handleFileScan issue count', () => {
  beforeEach(() => scanFile.mockReset())

  it('reports no issues only for a numeric zero', async () => {
    scanFile.mockResolvedValue({ statistics: { issues_found: 0 } })
    const { notify, analysis } = setup()
    await analysis.handleFileScan('a.py', types)
    expect(notify).toHaveBeenCalledWith('analytics.codebase.notify.fileScanNoIssues', 'success')
  })

  it.each([[{}], [{ issues_found: 'many' }], [{ issues_found: null }]])(
    'never shows the no-issues success toast for an unknown count %j',
    async (statistics) => {
      scanFile.mockResolvedValue({ statistics })
      const { notify, analysis } = setup()
      await analysis.handleFileScan('a.py', types)
      expect(notify).toHaveBeenCalledWith('analytics.codebase.notify.fileScanFailed', 'error')
      expect(notify).not.toHaveBeenCalledWith('analytics.codebase.notify.fileScanNoIssues', 'success')
    },
  )
})
