// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** #21581 -- the fetch monitor counts a timeout by type (isRequestTimeout), never by message text. */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest'
import { RequestTimeoutError } from '@autobot/ui'

type Monitor = { connectionErrorCount: number; setupCacheErrorMonitoring: () => void }

let CacheBusterClass: new () => Monitor
const pristineFetch = window.fetch

beforeAll(async () => {
  // The module auto-initializes a singleton (intervals, fetch wrapper); fake timers keep its checks from running.
  vi.useFakeTimers()
  CacheBusterClass = (await import('../CacheBuster')).default
})

afterAll(() => {
  window.fetch = pristineFetch
  vi.useRealTimers()
})

/** A monitor wrapping a fetch that rejects with `error`; returns the monitor after one failed call. */
async function monitorAfterFailure(error: unknown): Promise<Monitor> {
  window.fetch = vi.fn().mockRejectedValue(error)
  const monitor = new CacheBusterClass()
  monitor.setupCacheErrorMonitoring()
  await expect(window.fetch('/api/health')).rejects.toBe(error)
  return monitor
}

describe('CacheBuster fetch monitor timeout recognition', () => {
  beforeEach(() => {
    window.fetch = pristineFetch
  })

  it('counts the DOMException AbortSignal.timeout() produces', async () => {
    const monitor = await monitorAfterFailure(new DOMException('signal timed out', 'TimeoutError'))
    expect(monitor.connectionErrorCount).toBe(1)
  })

  it('counts the kit client RequestTimeoutError', async () => {
    const monitor = await monitorAfterFailure(new RequestTimeoutError(5))
    expect(monitor.connectionErrorCount).toBe(1)
  })

  it('does not count a plain Error that only says timeout (control)', async () => {
    const monitor = await monitorAfterFailure(new Error('Request timeout after 5ms'))
    expect(monitor.connectionErrorCount).toBe(0)
  })

  it('still counts a browser connection failure worded as a TypeError', async () => {
    const monitor = await monitorAfterFailure(new TypeError('Failed to fetch'))
    expect(monitor.connectionErrorCount).toBe(1)
  })
})
