// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Polled monitoring callers fail fast once the ApiClient circuit opens (#11682).
 * One get() makes up to 3 attempts; each failed attempt counts toward the
 * threshold, so the call after the first exhausted one must not reach fetch.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { resetCircuitBreakers } from '@/utils/apiCircuitBreaker'
import { useSystemMetrics } from '@/composables/useInstallMetrics'
import { useServiceMessages } from '@/composables/useServiceMessages'
import { useErrorMonitoring } from '@/composables/useErrorMonitoring'

async function settle(run: () => Promise<unknown>) {
  const p = run()
  await vi.advanceTimersByTimeAsync(10_000)
  await p
}

describe('polled callers use the circuit breaker', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    vi.useFakeTimers()
    resetCircuitBreakers()
    fetchMock = vi.fn().mockRejectedValue(new Error('network down'))
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('useSystemMetrics stops hitting the network after the threshold', async () => {
    const { fetch: poll } = useSystemMetrics()
    await settle(poll)
    const calls = fetchMock.mock.calls.length
    expect(calls).toBeGreaterThanOrEqual(3)
    await settle(poll)
    expect(fetchMock.mock.calls.length).toBe(calls)
  })

  it('useServiceMessages.fetchLatest stops hitting the network after the threshold', async () => {
    const { fetchLatest } = useServiceMessages()
    await settle(() => fetchLatest())
    const calls = fetchMock.mock.calls.length
    expect(calls).toBeGreaterThanOrEqual(3)
    await settle(() => fetchLatest())
    expect(fetchMock.mock.calls.length).toBe(calls)
  })

  it('useErrorMonitoring.fetchStatistics stops hitting the network after the threshold', async () => {
    const { fetchStatistics } = useErrorMonitoring({ autoFetch: false, pollInterval: 0 })
    await settle(() => fetchStatistics())
    const calls = fetchMock.mock.calls.length
    expect(calls).toBeGreaterThanOrEqual(3)
    await settle(() => fetchStatistics())
    expect(fetchMock.mock.calls.length).toBe(calls)
  })
})
