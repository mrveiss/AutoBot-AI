// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Unit tests for useCodeQualityData no-data state plumbing (Issue #6671).
 *
 * The backend's _no_data_response() returns { status: "no_data", ... } when
 * no codebase scan has happened yet. The composable must surface that state
 * via noDataState so the dashboard can render an empty-state banner instead
 * of silently rendering Grade C / zeros.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Capture pickData callbacks the composable registers so we can drive them
// directly without a fetch round-trip.
type PickData = (raw: Record<string, unknown>) => unknown
const registered: { path: string; pickData: PickData }[] = []

vi.mock('@/composables/api/useFetchEndpoint', () => ({
  useFetchEndpoint: (cfg: { path: string; pickData?: PickData }) => {
    registered.push({ path: cfg.path, pickData: cfg.pickData ?? ((r) => r) })
    return {
      data: { value: null },
      load: vi.fn().mockResolvedValue(undefined),
    }
  },
}))

import { useCodeQualityData } from './useCodeQualityData'

describe('useCodeQualityData — no-data state (#6671)', () => {
  beforeEach(() => {
    registered.length = 0
  })

  it('starts with noDataState.noData === false', () => {
    const data = useCodeQualityData((u) => u)
    expect(data.noDataState.value.noData).toBe(false)
    expect(data.noDataState.value.message).toBeNull()
  })

  it('flips noDataState.noData to true when health-score returns status:"no_data"', () => {
    const data = useCodeQualityData((u) => u)
    const ep = registered.find((r) => r.path === '/api/quality/health-score')
    expect(ep).toBeDefined()
    ep!.pickData({
      status: 'no_data',
      message: 'Run codebase indexing first.',
    })
    expect(data.noDataState.value.noData).toBe(true)
    expect(data.noDataState.value.message).toBe('Run codebase indexing first.')
  })

  it('clears noDataState when a subsequent response has real data', () => {
    const data = useCodeQualityData((u) => u)
    const hs = registered.find((r) => r.path === '/api/quality/health-score')!
    hs.pickData({ status: 'no_data', message: 'Run codebase indexing first.' })
    expect(data.noDataState.value.noData).toBe(true)
    hs.pickData({ status: 'ok', overall: 87, grade: 'B' })
    expect(data.noDataState.value.noData).toBe(false)
    expect(data.noDataState.value.message).toBeNull()
  })

  it('aggregates across endpoints — any endpoint reporting no_data wins', () => {
    const data = useCodeQualityData((u) => u)
    const hs = registered.find((r) => r.path === '/api/quality/health-score')!
    const cx = registered.find((r) => r.path === '/api/quality/complexity')!
    hs.pickData({ status: 'ok', overall: 90 })
    expect(data.noDataState.value.noData).toBe(false)
    cx.pickData({
      status: 'no_data',
      message: 'No complexity data',
    })
    expect(data.noDataState.value.noData).toBe(true)
    expect(data.noDataState.value.message).toBe('No complexity data')
  })

  it('healthScore pickData still returns sensible defaults so the component does not crash', () => {
    useCodeQualityData((u) => u)
    const hs = registered.find((r) => r.path === '/api/quality/health-score')!
    const result = hs.pickData({
      status: 'no_data',
      message: 'Run codebase indexing first.',
    }) as { overall: number; grade: string; recommendations: string[] }
    expect(result.overall).toBe(0)
    expect(result.grade).toBe('C')
    expect(result.recommendations).toEqual([])
  })

  it('metrics array path keeps existing semantics: a bare array means "ok, no rows"', () => {
    const data = useCodeQualityData((u) => u)
    const m = registered.find((r) => r.path === '/api/quality/metrics')!
    const result = m.pickData([]) as unknown[]
    expect(result).toEqual([])
    expect(data.noDataState.value.noData).toBe(false)
  })
})
