// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19270 — the resource heatmap never draws invented values. A failed or empty read used to
 * fill six hard-coded machines with random load; now it leaves the heatmap empty.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: { get } }))

import { useResourceMetrics } from '../useResourceMetrics'

beforeEach(() => {
  get.mockReset()
})

describe('useResourceMetrics (#19270)', () => {
  it('a failed read shows the error and no data', async () => {
    get.mockRejectedValue(new Error('HTTP 503'))
    const metrics = useResourceMetrics(() => 'all')
    await metrics.fetchData()
    expect(metrics.error.value).toBe('HTTP 503')
    expect(metrics.heatmapData.value).toEqual([])
  })

  it('a response with no machines is empty, not an error', async () => {
    get.mockResolvedValue({})
    const metrics = useResourceMetrics(() => 'all')
    await metrics.fetchData()
    expect(metrics.error.value).toBeNull()
    expect(metrics.heatmapData.value).toEqual([])
  })

  it('real points keep their values and get readable time labels', async () => {
    const time = '2026-10-23T09:30:00+00:00'
    get.mockResolvedValue({ machines: [{ name: 'node-a', metrics: [{ time, value: 42.5 }] }] })
    const metrics = useResourceMetrics(() => 'all')
    await metrics.fetchData()
    const [series] = metrics.heatmapData.value
    expect(series.name).toBe('node-a')
    expect(series.data).toHaveLength(1)
    expect(series.data[0].y).toBe(42.5)
    expect(series.data[0].x).not.toBe(time)
    expect(series.data[0].x).not.toBe('')
  })
})
