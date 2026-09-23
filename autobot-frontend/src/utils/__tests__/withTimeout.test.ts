// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * `withTimeout` settles like a race and never leaves its deadline timer behind (#16274, #16285).
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { withTimeout } from '@/utils/withTimeout'

describe('withTimeout (#16274, #16285)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('resolves with the work and clears the deadline', async () => {
    await expect(withTimeout(Promise.resolve('done'), 10_000, 'late')).resolves.toBe('done')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('passes the work\'s own rejection through and clears the deadline', async () => {
    await expect(withTimeout(Promise.reject(new Error('boom')), 10_000, 'late')).rejects.toThrow('boom')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('rejects with the given message once the deadline passes', async () => {
    const pending = withTimeout(new Promise<never>(() => {}), 10_000, 'Initialization timeout')
    const settled = expect(pending).rejects.toThrow('Initialization timeout')

    await vi.advanceTimersByTimeAsync(10_000)

    await settled
    expect(vi.getTimerCount()).toBe(0)
  })
})
