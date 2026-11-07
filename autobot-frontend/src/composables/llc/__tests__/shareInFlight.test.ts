// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// shareInFlight (#13942, #14556): concurrent callers share one pending call; a call after it
// settles — resolved or rejected — runs the function again.

import { describe, it, expect, vi } from 'vitest'
import { shareInFlight } from '../shareInFlight'

describe('shareInFlight', () => {
  it('concurrent callers share one call and one answer', async () => {
    const fn = vi.fn(() => Promise.resolve('c1'))
    const once = shareInFlight(fn)
    const [a, b] = await Promise.all([once(), once()])
    expect([a, b]).toEqual(['c1', 'c1'])
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('a call after the first settles runs the function again', async () => {
    const fn = vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce('c1')
    const once = shareInFlight(fn)
    expect(await once()).toBeNull()
    expect(await once()).toBe('c1')
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('a rejection is shared, then released', async () => {
    const fn = vi.fn().mockRejectedValueOnce(new Error('down')).mockResolvedValueOnce('c1')
    const once = shareInFlight(fn)
    const results = await Promise.allSettled([once(), once()])
    expect(results.map((r) => r.status)).toEqual(['rejected', 'rejected'])
    expect(fn).toHaveBeenCalledTimes(1)
    expect(await once()).toBe('c1')
  })

  it('starts the call synchronously, and a synchronous throw becomes a rejection', async () => {
    const fn = vi.fn(() => 'c3')
    const once = shareInFlight(fn)
    const p = once()
    expect(fn).toHaveBeenCalledTimes(1)
    expect(await p).toBe('c3')
    const boom = shareInFlight(() => {
      throw new Error('sync')
    })
    await expect(boom()).rejects.toThrow('sync')
  })

  it('accepts a synchronous function', async () => {
    const once = shareInFlight(() => 'c2')
    expect(await once()).toBe('c2')
  })
})
