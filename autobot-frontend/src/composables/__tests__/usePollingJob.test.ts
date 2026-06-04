/**
 * Unit tests for usePollingJob (#5191)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import { usePollingJob } from '../usePollingJob'

describe('usePollingJob', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('starts in idle state with null data/error', () => {
    const fetcher = vi.fn().mockResolvedValue({ status: 'PENDING' })
    const { isPolling, data, error, attempts } = usePollingJob(fetcher)

    expect(isPolling.value).toBe(false)
    expect(data.value).toBeNull()
    expect(error.value).toBeNull()
    expect(attempts.value).toBe(0)
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('fires fetcher immediately on start and again on each interval', async () => {
    const fetcher = vi.fn().mockResolvedValue({ status: 'PENDING' })
    const { start, stop, isPolling, attempts } = usePollingJob(fetcher, {
      intervalMs: 1000
    })

    start('task-1')
    expect(isPolling.value).toBe(true)
    // Immediate fire
    await vi.advanceTimersByTimeAsync(0)
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher).toHaveBeenCalledWith('task-1')

    // Second tick after interval
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetcher).toHaveBeenCalledTimes(2)

    // Third tick
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetcher).toHaveBeenCalledTimes(3)

    expect(attempts.value).toBe(3)
    stop()
  })

  it('stops polling and fires onDone when isComplete returns true', async () => {
    const responses = [
      { status: 'PENDING' },
      { status: 'PROGRESS' },
      { status: 'SUCCESS' }
    ]
    let i = 0
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(responses[i++]))
    const onDone = vi.fn()

    const { start, isPolling, data } = usePollingJob(fetcher, {
      intervalMs: 500,
      isComplete: (r) => r.status === 'SUCCESS' || r.status === 'FAILURE',
      onDone
    })

    start('task-success')

    // First call (immediate)
    await vi.advanceTimersByTimeAsync(0)
    expect(isPolling.value).toBe(true)

    // Second tick
    await vi.advanceTimersByTimeAsync(500)
    expect(isPolling.value).toBe(true)

    // Third tick — SUCCESS
    await vi.advanceTimersByTimeAsync(500)
    expect(fetcher).toHaveBeenCalledTimes(3)
    expect(isPolling.value).toBe(false)
    expect(onDone).toHaveBeenCalledTimes(1)
    expect(onDone).toHaveBeenCalledWith({ status: 'SUCCESS' })
    expect(data.value).toEqual({ status: 'SUCCESS' })
  })

  it('stores error but continues polling on transient fetcher errors', async () => {
    const fetcher = vi.fn()
      .mockRejectedValueOnce(new Error('network blip'))
      .mockResolvedValueOnce({ status: 'PENDING' })
      .mockResolvedValueOnce({ status: 'SUCCESS' })

    const { start, isPolling, error } = usePollingJob(fetcher, {
      intervalMs: 100,
      isComplete: (r) => r.status === 'SUCCESS'
    })

    start('task-err')
    // First call (immediate) → rejects
    await vi.advanceTimersByTimeAsync(0)
    expect(error.value).toBeInstanceOf(Error)
    expect(error.value?.message).toBe('network blip')
    expect(isPolling.value).toBe(true)

    // Second tick → PENDING, still polling
    await vi.advanceTimersByTimeAsync(100)
    expect(isPolling.value).toBe(true)

    // Third tick → SUCCESS, stop
    await vi.advanceTimersByTimeAsync(100)
    expect(isPolling.value).toBe(false)
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('stops automatically when maxAttempts is reached', async () => {
    const fetcher = vi.fn().mockResolvedValue({ status: 'PENDING' })
    const { start, isPolling, attempts } = usePollingJob(fetcher, {
      intervalMs: 10,
      maxAttempts: 3,
      isComplete: () => false
    })

    start('task-max')
    // Immediate + 2 interval ticks = 3 attempts
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(10)
    await vi.advanceTimersByTimeAsync(10)

    expect(attempts.value).toBe(3)
    expect(isPolling.value).toBe(false)
    expect(fetcher).toHaveBeenCalledTimes(3)

    // Verify no further calls after cap
    await vi.advanceTimersByTimeAsync(100)
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('stop() halts polling and clears the interval', async () => {
    const fetcher = vi.fn().mockResolvedValue({ status: 'PENDING' })
    const { start, stop, isPolling } = usePollingJob(fetcher, { intervalMs: 100 })

    start('task-stop')
    await vi.advanceTimersByTimeAsync(0)
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(isPolling.value).toBe(true)

    stop()
    expect(isPolling.value).toBe(false)

    await vi.advanceTimersByTimeAsync(500)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('auto-cleans up when owning effect scope is disposed', async () => {
    const fetcher = vi.fn().mockResolvedValue({ status: 'PENDING' })

    const scope = effectScope()
    let handle: ReturnType<typeof usePollingJob<unknown>>
    scope.run(() => {
      handle = usePollingJob(fetcher, { intervalMs: 50 })
      handle.start('task-scope')
    })

    await vi.advanceTimersByTimeAsync(0)
    expect(fetcher).toHaveBeenCalledTimes(1)

    scope.stop()
    expect(handle!.isPolling.value).toBe(false)

    await vi.advanceTimersByTimeAsync(500)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('last-caller-wins: restart with new taskId abandons in-flight old tick', async () => {
    let resolveFirst: (v: { status: string; which: string }) => void = () => {}
    const firstPromise = new Promise<{ status: string; which: string }>((r) => {
      resolveFirst = r
    })

    const fetcher = vi.fn()
      .mockImplementationOnce(() => firstPromise)
      .mockResolvedValue({ status: 'PENDING', which: 'new' })

    const { start, data, attempts } = usePollingJob(fetcher, {
      intervalMs: 1000,
      isComplete: (r: { status: string }) => r.status === 'SUCCESS'
    })

    start('task-old')
    // First immediate call is pending (unresolved)
    await nextTick()
    expect(fetcher).toHaveBeenCalledTimes(1)

    // User restarts with a new task before old one resolves
    start('task-new')
    // attempts was reset to 0 on start(); the immediate poll tick then increments to 1
    expect(attempts.value).toBe(1)

    // Resolve the old promise — it should be abandoned (data stays null for old)
    resolveFirst({ status: 'SUCCESS', which: 'old' })
    await nextTick()
    // New taskId's immediate poll fires
    await vi.advanceTimersByTimeAsync(0)
    await nextTick()

    // data should reflect the NEW call, not the abandoned old one
    expect(data.value).toEqual({ status: 'PENDING', which: 'new' })
  })

  it('onDone is not called if isComplete is not provided (polls until maxAttempts)', async () => {
    const fetcher = vi.fn().mockResolvedValue({ anything: true })
    const onDone = vi.fn()
    const { start, isPolling } = usePollingJob(fetcher, {
      intervalMs: 10,
      maxAttempts: 2,
      onDone
    })

    start('task-nocomplete')
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(10)

    expect(isPolling.value).toBe(false)
    expect(onDone).not.toHaveBeenCalled()
  })

  it('wraps non-Error rejections into Error instances', async () => {
    const fetcher = vi.fn().mockRejectedValue('string rejection')
    const { start, error } = usePollingJob(fetcher, {
      intervalMs: 100,
      maxAttempts: 1
    })

    start('task-strerr')
    await vi.advanceTimersByTimeAsync(0)

    expect(error.value).toBeInstanceOf(Error)
    expect(error.value?.message).toBe('string rejection')
  })

  it('accepts Ref<number> for intervalMs and uses its value at start() time', async () => {
    const fetcher = vi.fn().mockResolvedValue({ status: 'PENDING' })
    const intervalRef = ref(500)
    const { start, stop, attempts } = usePollingJob(fetcher, {
      intervalMs: intervalRef
    })

    start('task-ref-interval')
    // Immediate fire
    await vi.advanceTimersByTimeAsync(0)
    expect(fetcher).toHaveBeenCalledTimes(1)

    // Tick at captured interval (500ms)
    await vi.advanceTimersByTimeAsync(500)
    expect(fetcher).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(500)
    expect(fetcher).toHaveBeenCalledTimes(3)

    expect(attempts.value).toBe(3)
    stop()
  })

  it('stops after consecutiveErrorLimit consecutive errors (#6765 circuit-breaker)', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('404 Not Found'))
    const { start, isPolling, error, attempts } = usePollingJob(fetcher, {
      intervalMs: 100,
      consecutiveErrorLimit: 3
    })

    start('task-404')
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(100)
    await vi.advanceTimersByTimeAsync(100)

    expect(attempts.value).toBe(3)
    expect(isPolling.value).toBe(false)
    expect(error.value?.message).toBe('404 Not Found')

    await vi.advanceTimersByTimeAsync(500)
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('resets consecutive error count on success (circuit-breaker survives recovery)', async () => {
    const fetcher = vi.fn()
      .mockRejectedValueOnce(new Error('blip'))
      .mockRejectedValueOnce(new Error('blip'))
      .mockResolvedValueOnce({ status: 'OK' })
      .mockRejectedValueOnce(new Error('blip'))
      .mockRejectedValueOnce(new Error('blip'))
    const { start, isPolling, attempts } = usePollingJob(fetcher, {
      intervalMs: 50,
      consecutiveErrorLimit: 3
    })

    start('task-recovery')
    await vi.advanceTimersByTimeAsync(0)   // error #1
    await vi.advanceTimersByTimeAsync(50)  // error #2
    await vi.advanceTimersByTimeAsync(50)  // success → resets counter
    await vi.advanceTimersByTimeAsync(50)  // error #1 again
    await vi.advanceTimersByTimeAsync(50)  // error #2 again — still below limit 3

    expect(isPolling.value).toBe(true)
    expect(attempts.value).toBe(5)
  })

  it('picks up updated Ref<number> value when start() is called again', async () => {
    const fetcher = vi.fn().mockResolvedValue({ status: 'PENDING' })
    const intervalRef = ref(1000)
    const { start, stop } = usePollingJob(fetcher, {
      intervalMs: intervalRef
    })

    // First polling session at 1000ms interval
    start('task-ref-update')
    await vi.advanceTimersByTimeAsync(0)
    expect(fetcher).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetcher).toHaveBeenCalledTimes(2)
    stop()

    // Update ref and restart — new interval should be 200ms
    intervalRef.value = 200
    start('task-ref-update')
    await vi.advanceTimersByTimeAsync(0)
    expect(fetcher).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(200)
    expect(fetcher).toHaveBeenCalledTimes(4)
    // Old 1000ms interval should NOT fire at t=800ms
    await vi.advanceTimersByTimeAsync(600)
    expect(fetcher).toHaveBeenCalledTimes(7) // 3 more at 200ms: t=400, 600, 800
    stop()
  })
})
