// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #20498: the overview card must read the fields the endpoints
 * actually return. Fixtures copy the handler response shapes:
 *  - analytics_quality.py get_health_score: { overall, grade, trend, breakdown }
 *  - analytics_debt.py get_debt_summary: { summary: { total_items, total_hours } }
 */
import { describe, it, expect } from 'vitest'
import { buildCodeQuality } from '../codeQualityOverview'

const health = {
  status: 'success',
  overall: 72.4,
  grade: 'C',
  trend: 'stable',
  breakdown: { testability: 61.2, performance: 90 },
}
const debt = {
  status: 'success',
  summary: { total_items: 40, total_hours: 123.5 },
  top_files: [],
}
const dup = { status: 'success', total_count: 7 }

describe('buildCodeQuality (#20498)', () => {
  // Pre-fix: read health_score (absent) and fell back to breakdown.performance (90).
  it('takes the overall score from `overall`, not the performance breakdown', () => {
    expect(buildCodeQuality(health, dup, debt).overall_score).toBe(72)
  })

  // Pre-fix: read top-level total_debt_hours/total_items (absent) -> 0.
  it('takes technical debt hours from summary.total_hours', () => {
    expect(buildCodeQuality(health, dup, debt).technical_debt).toBe(123.5)
  })

  it('keeps a real zero as 0', () => {
    const zero = { status: 'success', summary: { total_items: 0, total_hours: 0 } }
    expect(buildCodeQuality(health, dup, zero).technical_debt).toBe(0)
  })

  // Pre-fix: missing values collapsed to 0 / 50 / performance score.
  it('reports missing values as null (not available), never 0', () => {
    const q = buildCodeQuality(null, null, null)
    expect(q).toEqual({
      overall_score: null,
      test_coverage: null,
      code_duplicates: null,
      technical_debt: null,
    })
  })

  it('does not use total_items as hours when total_hours is absent', () => {
    const q = buildCodeQuality(health, dup, { status: 'success', summary: { total_items: 40 } })
    expect(q.technical_debt).toBeNull()
  })

  it('reads test coverage from breakdown.testability and duplicates from total_count', () => {
    const q = buildCodeQuality(health, dup, debt)
    expect(q.test_coverage).toBe(61)
    expect(q.code_duplicates).toBe(7)
  })
})
