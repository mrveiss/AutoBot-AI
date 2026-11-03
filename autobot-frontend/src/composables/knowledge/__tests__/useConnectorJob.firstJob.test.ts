// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19714: a just-started sync reports its job late, so an early "no job" doesn't end the watch.
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

  it('keeps watching after an early 404 until the job finishes', async () => {
    get
      .mockRejectedValueOnce(notFound)
      .mockResolvedValueOnce({ status: 'running' })
      .mockResolvedValueOnce({ status: 'completed' })
    const { isPolling, jobState, start } = useConnectorJob()
    start('c')
    await vi.advanceTimersByTimeAsync(0)
    expect(isPolling.value).toBe(true)
    await vi.advanceTimersByTimeAsync(POLL_MS * 2)
    expect(isPolling.value).toBe(false)
    expect(jobState.value?.status).toBe('completed')
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

  it('gives up if no job ever appears', async () => {
    get.mockRejectedValue(notFound)
    const { isPolling, start } = useConnectorJob()
    start('c')
    await vi.advanceTimersByTimeAsync(POLL_MS * 13)
    expect(isPolling.value).toBe(false)
    expect(get).toHaveBeenCalledTimes(13)
  })
})
