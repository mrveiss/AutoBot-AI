// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for useLoadingState (#5881, #5883)

import { describe, it, expect } from 'vitest'
import { nextTick } from 'vue'
import { useLoadingState } from '../useLoadingState'

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useLoadingState', () => {
  it('initializes isLoading=false by default', () => {
    const { isLoading } = useLoadingState()
    expect(isLoading.value).toBe(false)
  })

  it('initializes isLoading=true when initial=true', () => {
    const { isLoading } = useLoadingState(true)
    expect(isLoading.value).toBe(true)
  })

  it('sets isLoading=true while wrap is running', async () => {
    const { isLoading, wrap } = useLoadingState()
    const d = deferred<number>()
    const resultPromise = wrap(() => d.promise)
    await nextTick()
    expect(isLoading.value).toBe(true)
    d.resolve(42)
    await resultPromise
    expect(isLoading.value).toBe(false)
  })

  it('returns the resolved value from wrap', async () => {
    const { wrap } = useLoadingState()
    const result = await wrap(() => Promise.resolve('hello'))
    expect(result).toBe('hello')
  })

  it('clears isLoading=false after wrap completes', async () => {
    const { isLoading, wrap } = useLoadingState()
    await wrap(() => Promise.resolve(1))
    expect(isLoading.value).toBe(false)
  })

  it('clears isLoading=false even when wrap throws', async () => {
    const { isLoading, wrap } = useLoadingState()
    await wrap(() => Promise.reject(new Error('boom'))).catch(() => {})
    expect(isLoading.value).toBe(false)
  })

  it('propagates errors thrown inside wrap', async () => {
    const { wrap } = useLoadingState()
    await expect(wrap(() => Promise.reject(new Error('fail')))).rejects.toThrow('fail')
  })

  it('does NOT clear isLoading prematurely when two calls overlap (#5883)', async () => {
    const { isLoading, wrap } = useLoadingState()
    const d1 = deferred<number>()
    const d2 = deferred<number>()

    const p1 = wrap(() => d1.promise)
    const p2 = wrap(() => d2.promise)
    await nextTick()

    expect(isLoading.value).toBe(true)

    // op1 finishes first — isLoading must stay true because op2 is still running
    d1.resolve(1)
    await p1
    expect(isLoading.value).toBe(true)

    // op2 finishes — now isLoading can clear
    d2.resolve(2)
    await p2
    expect(isLoading.value).toBe(false)
  })

  it('handles many concurrent calls and only clears after last one', async () => {
    const { isLoading, wrap } = useLoadingState()
    const defers = Array.from({ length: 5 }, () => deferred<number>())
    const promises = defers.map((d) => wrap(() => d.promise))

    await nextTick()
    expect(isLoading.value).toBe(true)

    // resolve first 4 — still loading
    for (let i = 0; i < 4; i++) {
      defers[i].resolve(i)
      await promises[i]
      expect(isLoading.value).toBe(true)
    }

    // resolve last one — now done
    defers[4].resolve(4)
    await promises[4]
    expect(isLoading.value).toBe(false)
  })

  it('resets correctly for sequential calls', async () => {
    const { isLoading, wrap } = useLoadingState()
    await wrap(() => Promise.resolve(1))
    expect(isLoading.value).toBe(false)

    const d = deferred<number>()
    const p = wrap(() => d.promise)
    await nextTick()
    expect(isLoading.value).toBe(true)
    d.resolve(2)
    await p
    expect(isLoading.value).toBe(false)
  })
})
