// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// RumAgent keeps only the latest RUM_MAX_API_CALLS per-call records (#21583): every kit-client request is
// recorded now, so a polling view must not grow the buffers without bound.

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import rum from '@/utils/RumAgent'
import { RUM_MAX_API_CALLS } from '@/utils/rumBufferCap'

type Buffers = {
  metrics: { apiCalls: Array<{ url: string; isTimeout: boolean }> }
  pendingApiCalls: Array<{ endpoint: string; is_timeout: boolean; error_type?: string }>
  pendingCriticalIssues: Array<{ issue_type: string }>
}

const buffers = (): Buffers => rum as unknown as Buffers

describe('RumAgent.trackApiCall buffers', () => {
  beforeEach(() => {
    rum.clear()
    buffers().pendingApiCalls = []
    buffers().pendingCriticalIssues = []
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

  it('bounds the unflushed critical-issue queue: slow polling past the timeout threshold', () => {
    for (let i = 0; i <= RUM_MAX_API_CALLS; i++) rum.trackApiCall('GET', `/api/poll/${i}`, 0, 30001, 200)
    expect(buffers().pendingCriticalIssues).toHaveLength(RUM_MAX_API_CALLS)
  })

  it('records a typed timeout under the duration threshold as a timeout, reported once', () => {
    rum.trackApiCall('GET', '/api/slow', 0, 5000, 'error', new Error('timed out'), true)
    expect(buffers().metrics.apiCalls.at(-1)?.isTimeout).toBe(true)
    expect(buffers().pendingApiCalls.at(-1)).toMatchObject({ is_timeout: true, error_type: 'timeout' })
    expect(buffers().pendingCriticalIssues).toEqual([{ issue_type: 'api_timeout' }])
  })

  it('has a positive default bound', () => {
    expect(RUM_MAX_API_CALLS).toBeGreaterThan(0)
  })
})
