// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// backoffDelay (#15402): the one exponential-backoff formula both apps'
// reconnects and retries call.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { backoffDelay } from '../backoff'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('backoffDelay', () => {
  it('doubles from the base with each exponent', () => {
    expect([0, 1, 2, 3].map((n) => backoffDelay(n, { base: 1000 }))).toEqual([1000, 2000, 4000, 8000])
  })

  it('stops at the cap', () => {
    expect([0, 1, 2, 3, 4, 5].map((n) => backoffDelay(n, { base: 1000, max: 5000 }))).toEqual([
      1000, 2000, 4000, 5000, 5000, 5000,
    ])
  })

  it('treats a negative exponent as the base, never a fraction of it', () => {
    expect(backoffDelay(-1, { base: 1000 })).toBe(1000)
  })

  it('adds jitter below jitterMs, and the cap still holds with jitter included', () => {
    vi.spyOn(crypto, 'getRandomValues').mockImplementation(<T extends ArrayBufferView | null>(a: T) => {
      ;(a as unknown as Uint32Array)[0] = 1999
      return a
    })
    expect(backoffDelay(0, { base: 1000, jitterMs: 1000 })).toBe(1999)
    expect(backoffDelay(5, { base: 1000, max: 30000, jitterMs: 1000 })).toBe(30000)
  })

  it('redraws a value from the biased top bucket instead of taking its modulo', () => {
    // For jitterMs = 1000 the unbiased ceiling is 2^32 - (2^32 % 1000) = 4294967000.
    const draws = [0xffffffff, 1999]
    const spy = vi.spyOn(crypto, 'getRandomValues').mockImplementation(<T extends ArrayBufferView | null>(a: T) => {
      ;(a as unknown as Uint32Array)[0] = draws.shift() as number
      return a
    })
    expect(backoffDelay(0, { base: 1000, jitterMs: 1000 })).toBe(1999)
    expect(spy).toHaveBeenCalledTimes(2)
  })

  it('keeps jitter inside [0, jitterMs) at both ends of the accepted range', () => {
    const draws = [0, 4294966999]
    vi.spyOn(crypto, 'getRandomValues').mockImplementation(<T extends ArrayBufferView | null>(a: T) => {
      ;(a as unknown as Uint32Array)[0] = draws.shift() as number
      return a
    })
    expect(backoffDelay(0, { base: 0, jitterMs: 1000 })).toBe(0)
    expect(backoffDelay(0, { base: 0, jitterMs: 1000 })).toBe(999)
  })

  it('adds no jitter unless asked', () => {
    const spy = vi.spyOn(crypto, 'getRandomValues')
    backoffDelay(2, { base: 500, max: 10000 })
    expect(spy).not.toHaveBeenCalled()
  })

  it('never returns NaN for a bad config', () => {
    expect(backoffDelay(2, { base: 1000, max: Number.NaN })).toBe(4000)
    expect(backoffDelay(Number.NaN, { base: 1000, max: 5000 })).toBe(1000)
    expect(backoffDelay(2, { base: Number.NaN, max: 5000 })).toBe(0)
  })
})
