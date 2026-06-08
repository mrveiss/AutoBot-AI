// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Unit tests for useRequestQueue composable
 * Issue #4415: Backpressure for concurrent LLM calls
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

// Isolate module so each test gets a fresh singleton
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useRequestQueue', () => {
  // Re-import per test to reset module state properly
  beforeEach(() => {
    vi.resetModules()
  })

  it('executes a single request immediately', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue()
    const fn = vi.fn().mockResolvedValue('ok')
    const result = await queue.enqueue({ fn, priority: 'normal' })
    expect(result).toBe('ok')
    expect(fn).toHaveBeenCalledOnce()
  })

  it('pending increments while queued and decrements after start', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue({ concurrency: 1 })

    const d1 = deferred<string>()
    const d2 = deferred<string>()

    queue.enqueue({ fn: () => d1.promise, priority: 'normal' })
    queue.enqueue({ fn: () => d2.promise, priority: 'normal' })

    await nextTick()
    // d1 is in-flight, d2 is pending
    expect(queue.active.value).toBe(1)
    expect(queue.pending.value).toBe(1)

    d1.resolve('first')
    await nextTick()
    await nextTick()
    // d2 now in-flight
    expect(queue.active.value).toBe(1)
    expect(queue.pending.value).toBe(0)

    d2.resolve('second')
    await nextTick()
    expect(queue.active.value).toBe(0)
    expect(queue.pending.value).toBe(0)
  })

  it('respects concurrency limit', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue({ concurrency: 2 })

    const defers = [deferred<number>(), deferred<number>(), deferred<number>()]
    const startOrder: number[] = []

    defers.forEach((d, i) => {
      queue.enqueue({
        fn: () => { startOrder.push(i); return d.promise },
        priority: 'normal',
      })
    })

    await nextTick()
    // Only 2 should have started
    expect(queue.active.value).toBe(2)
    expect(queue.pending.value).toBe(1)
    expect(startOrder).toEqual([0, 1])

    defers[0].resolve(0)
    await nextTick()
    await nextTick()
    // Third should now start
    expect(queue.active.value).toBe(2)
    expect(startOrder).toEqual([0, 1, 2])

    defers[1].resolve(1)
    defers[2].resolve(2)
    await Promise.allSettled(defers.map((d) => d.promise))
    expect(queue.active.value).toBe(0)
  })

  it('executes high priority before normal before low', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    // concurrency=1 so we can observe ordering
    const queue = useRequestQueue({ concurrency: 1 })

    const gate = deferred<void>()
    const order: string[] = []

    // Fill the single slot first to allow queueing
    queue.enqueue({ fn: () => gate.promise, priority: 'normal' })

    queue.enqueue({ fn: async () => { order.push('low') }, priority: 'low' })
    queue.enqueue({ fn: async () => { order.push('high') }, priority: 'high' })
    queue.enqueue({ fn: async () => { order.push('normal') }, priority: 'normal' })

    await nextTick()
    gate.resolve()
    await nextTick()
    await nextTick()
    await nextTick()

    expect(order).toEqual(['high', 'normal', 'low'])
  })

  it('deduplicates in-flight requests by dedupeKey', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue()

    const fn = vi.fn().mockResolvedValue('data')
    const p1 = queue.enqueue({ fn, priority: 'normal', dedupeKey: 'search-x' })
    const p2 = queue.enqueue({ fn, priority: 'normal', dedupeKey: 'search-x' })

    expect(p1).toBe(p2)
    const [r1, r2] = await Promise.all([p1, p2])
    expect(r1).toBe('data')
    expect(r2).toBe('data')
    expect(fn).toHaveBeenCalledOnce()
  })

  it('deduplicates queued (not-yet-started) requests by dedupeKey', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue({ concurrency: 1 })

    const gate = deferred<void>()
    queue.enqueue({ fn: () => gate.promise, priority: 'normal' })

    const fn = vi.fn().mockResolvedValue('dedup')
    const p1 = queue.enqueue({ fn, priority: 'normal', dedupeKey: 'key-q' })
    const p2 = queue.enqueue({ fn, priority: 'normal', dedupeKey: 'key-q' })

    expect(p1).toBe(p2)

    gate.resolve()
    const result = await p1
    expect(result).toBe('dedup')
    expect(fn).toHaveBeenCalledOnce()
  })

  it('cancel drops a pending request', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue({ concurrency: 1 })

    const gate = deferred<void>()
    queue.enqueue({ fn: () => gate.promise, priority: 'normal' })

    const fn = vi.fn().mockResolvedValue('should-not-run')
    const p = queue.enqueue({ fn, priority: 'normal', dedupeKey: 'cancel-me' })

    queue.cancel('cancel-me')

    gate.resolve()
    await expect(p).rejects.toThrow('Request cancelled')
    expect(fn).not.toHaveBeenCalled()
  })

  it('cancel does not affect in-flight requests', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue()

    const d = deferred<string>()
    const p = queue.enqueue({ fn: () => d.promise, priority: 'normal', dedupeKey: 'inflight' })

    await nextTick()
    expect(queue.active.value).toBe(1)

    // cancel after it's already in-flight — should be a no-op
    queue.cancel('inflight')

    d.resolve('result')
    const result = await p
    expect(result).toBe('result')
  })

  it('propagates rejection from the underlying function', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue()

    const err = new Error('boom')
    const fn = vi.fn().mockRejectedValue(err)
    await expect(queue.enqueue({ fn, priority: 'normal' })).rejects.toThrow('boom')
    expect(queue.active.value).toBe(0)
  })

  it('active and pending stay consistent after errors', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue({ concurrency: 2 })

    const d1 = deferred<string>()
    const d2 = deferred<string>()

    const p1 = queue.enqueue({ fn: () => d1.promise, priority: 'normal' })
    const p2 = queue.enqueue({ fn: () => d2.promise, priority: 'normal' })

    await nextTick()
    expect(queue.active.value).toBe(2)

    d1.reject(new Error('err1'))
    d2.resolve('ok2')

    await Promise.allSettled([p1, p2])
    expect(queue.active.value).toBe(0)
    expect(queue.pending.value).toBe(0)
  })

  it('different dedupeKeys are treated independently', async () => {
    const { useRequestQueue } = await import('../useRequestQueue')
    const queue = useRequestQueue()

    const fn1 = vi.fn().mockResolvedValue('a')
    const fn2 = vi.fn().mockResolvedValue('b')

    const p1 = queue.enqueue({ fn: fn1, priority: 'normal', dedupeKey: 'key-a' })
    const p2 = queue.enqueue({ fn: fn2, priority: 'normal', dedupeKey: 'key-b' })

    expect(p1).not.toBe(p2)
    const [r1, r2] = await Promise.all([p1, p2])
    expect(r1).toBe('a')
    expect(r2).toBe('b')
  })

  it('module-level requestQueue singleton is exported', async () => {
    const mod = await import('../useRequestQueue')
    expect(mod.requestQueue).toBeDefined()
    expect(typeof mod.requestQueue.enqueue).toBe('function')
    expect(typeof mod.requestQueue.cancel).toBe('function')
    expect(mod.requestQueue.pending).toBeDefined()
    expect(mod.requestQueue.active).toBeDefined()
  })
})
