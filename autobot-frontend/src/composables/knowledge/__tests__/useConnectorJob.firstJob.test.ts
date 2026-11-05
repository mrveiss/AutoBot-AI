// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19714, #20755: a just-started sync reads as 'starting' (the backend answers from its lease) until
// its job state is written, so the watch lasts as long as the sync does and "no job" ends it.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useConnectorJob } from '../useConnectorJob'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: { get } }))

const POLL_MS = 5_000
const notFound = Object.assign(new Error('not found'), { status: 404 })

describe('useConnectorJob first job', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    get.mockReset()
  })
  afterEach(() => vi.useRealTimers())

  it('keeps watching through a long starting phase until the job finishes', async () => {
    const starting = Array.from({ length: 30 }, () => ({ status: 'starting' }))
    starting.forEach((s) => get.mockResolvedValueOnce(s))
    get.mockResolvedValueOnce({ status: 'running' }).mockResolvedValueOnce({ status: 'success' })
    const { isPolling, jobState, start } = useConnectorJob()
    start('c') // polls at once, so 30 answers cover t=0 .. 29 intervals
    await vi.advanceTimersByTimeAsync(POLL_MS * 29)
    expect(isPolling.value, 'a detection longer than any fixed wait still watches').toBe(true)
    expect(jobState.value?.status).toBe('starting')
    await vi.advanceTimersByTimeAsync(POLL_MS * 2)
    expect(isPolling.value).toBe(false)
    expect(jobState.value?.status).toBe('success')
  })

  it('stops when a seen job is gone', async () => {
    get.mockResolvedValueOnce({ status: 'running' }).mockRejectedValueOnce(notFound)
    const { isPolling, start } = useConnectorJob()
    start('c')
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(isPolling.value).toBe(false)
  })

  it('stops at once when the job request fails, rather than waiting for a job', async () => {
    get.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }))
    const { isPolling, start } = useConnectorJob()
    start('c')
    await vi.advanceTimersByTimeAsync(0)
    expect(isPolling.value).toBe(false)
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('a failed request after a running job clears the state, so nothing shows Running', async () => {
    get
      .mockResolvedValueOnce({ status: 'running' })
      .mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 500 }))
    const { isPolling, jobState, pollFailed, start } = useConnectorJob()
    start('c')
    await vi.advanceTimersByTimeAsync(0)
    expect(jobState.value?.status).toBe('running')
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(isPolling.value).toBe(false)
    expect(jobState.value).toBeNull()
    expect(pollFailed.value).toBe(true)
  })

  it('stops at once when no sync is in flight', async () => {
    get.mockRejectedValue(notFound)
    const { isPolling, start } = useConnectorJob()
    start('c')
    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(isPolling.value).toBe(false)
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('stops on a finished state, and a fresh start polls again (the Retry path)', async () => {
    get.mockResolvedValueOnce({ status: 'failed' }).mockResolvedValueOnce({ status: 'running' })
    const { isPolling, start } = useConnectorJob()
    start('c')
    await vi.advanceTimersByTimeAsync(0)
    expect(isPolling.value).toBe(false)
    start('c')
    await vi.advanceTimersByTimeAsync(0)
    expect(isPolling.value).toBe(true)
  })
})
