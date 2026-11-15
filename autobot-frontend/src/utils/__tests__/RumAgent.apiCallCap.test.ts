// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// RumAgent keeps only the latest RUM_MAX_API_CALLS per-call records (#21583): every kit-client request is
// recorded now, so a polling view must not grow the buffers without bound.

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import rum from '@/utils/RumAgent'
import { RUM_MAX_API_CALLS } from '@/utils/rumBufferCap'

type Buffers = { metrics: { apiCalls: Array<{ url: string }> }; pendingApiCalls: Array<{ endpoint: string }> }

const buffers = (): Buffers => rum as unknown as Buffers

describe('RumAgent.trackApiCall buffers', () => {
  beforeEach(() => {
    rum.clear()
    buffers().pendingApiCalls = []
  })
  afterEach(() => {
    rum.stop()
  })

  it('keeps the latest N recorded calls when N+1 are pushed', () => {
    for (let i = 0; i <= RUM_MAX_API_CALLS; i++) rum.trackApiCall('GET', `/api/poll/${i}`, 0, 1, 200)
    const kept = buffers().metrics.apiCalls
    expect(kept).toHaveLength(RUM_MAX_API_CALLS)
    expect(kept[0].url).toBe('/api/poll/1')
    expect(kept[RUM_MAX_API_CALLS - 1].url).toBe(`/api/poll/${RUM_MAX_API_CALLS}`)
  })

  it('bounds the unflushed reporting queue the same way', () => {
    for (let i = 0; i <= RUM_MAX_API_CALLS; i++) rum.trackApiCall('GET', `/api/poll/${i}`, 0, 1, 200)
    expect(buffers().pendingApiCalls).toHaveLength(RUM_MAX_API_CALLS)
  })

  it('has a positive default bound', () => {
    expect(RUM_MAX_API_CALLS).toBeGreaterThan(0)
  })
})
