// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Builds the Code Quality overview card from the three endpoint responses.
 *
 * Response shapes, copied from the backend handlers:
 *  - GET /api/quality/health-score  -> { status, overall, grade, trend, breakdown, ... }
 *    (analytics_quality.py get_health_score)
 *  - GET /api/debt/summary          -> { status, summary: { total_items, total_hours, ... }, ... }
 *    (analytics_debt.py get_debt_summary)
 *  - GET duplicates                 -> { status: 'success', total_count | total_duplicates | count }
 *
 * A figure the endpoints did not return is `null` (rendered as "not
 * available"), never 0 — 0 is a real measurement (Issue #20498).
 */

export interface CodeQualityData {
  overall_score: number | null
  test_coverage: number | null
  code_duplicates: number | null
  /** Estimated debt in hours. */
  technical_debt: number | null
}

type Json = Record<string, unknown> | null

const num = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null

const rounded = (v: number | null): number | null => (v === null ? null : Math.round(v))

function duplicateCount(duplicates: Json): number | null {
  if (duplicates?.status !== 'success') return null
  return (
    num(duplicates.total_count) ?? num(duplicates.total_duplicates) ?? num(duplicates.count)
  )
}

export function buildCodeQuality(health: Json, duplicates: Json, debt: Json): CodeQualityData {
  const breakdown = (health?.breakdown as Record<string, unknown> | undefined) ?? {}
  const summary = (debt?.summary as Record<string, unknown> | undefined) ?? {}
  return {
    overall_score: rounded(num(health?.overall)),
    test_coverage: rounded(num(breakdown.testability)),
    code_duplicates: duplicateCount(duplicates),
    technical_debt: num(summary.total_hours),
  }
}
