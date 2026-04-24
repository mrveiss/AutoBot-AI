// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
//
// Tests for useApiResource (#5149, #5179)

import { describe, it, expect, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'
import { useApiResource } from '../useApiResource'

/**
 * Helper to create a deferred promise whose `resolve` / `reject` we can
 * call from the test body. Lets us control fetch timing precisely.
 */
function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useApiResource', () => {
  it('initializes with data=null, error=null, isLoading=false', () => {
    const { data, error, isLoading } = useApiResource(() =>
      Promise.resolve(42)
    )
    expect(data.value).toBe(null)
    expect(error.value).toBe(null)
    expect(isLoading.value).toBe(false)
  })

  it('refresh() sets isLoading=true while in flight, then data=result', async () => {
    const d = deferred<number>()
    const { data, isLoading, refresh } = useApiResource(() => d.promise)

    const refreshPromise = refresh()
    expect(isLoading.value).toBe(true)
    expect(data.value).toBe(null)

    d.resolve(42)
    await refreshPromise

    expect(isLoading.value).toBe(false)
    expect(data.value).toBe(42)
  })

  it('refresh() captures rejection in error.value and clears isLoading', async () => {
    const err = new Error('boom')
    const { data, error, isLoading, refresh } = useApiResource(() =>
      Promise.reject(err)
    )

    await refresh()

    expect(error.value).toBe(err)
    expect(data.value).toBe(null)
    expect(isLoading.value).toBe(false)
  })

  it('wraps non-Error rejections (string, number, object) in Error', async () => {
    const cases: unknown[] = ['string rejection', 42, { kind: 'obj' }]
    for (const rejectValue of cases) {
      const { error, refresh } = useApiResource(() =>
        Promise.reject(rejectValue)
      )
      await refresh()
      expect(error.value).toBeInstanceOf(Error)
      expect(error.value?.message).toBe(String(rejectValue))
    }
  })

  it('clears previous error on successful re-fetch', async () => {
    let shouldFail = true
    const { data, error, refresh } = useApiResource(() =>
      shouldFail ? Promise.reject(new Error('boom')) : Promise.resolve(42)
    )

    await refresh()
    expect(error.value?.message).toBe('boom')
    expect(data.value).toBe(null)

    shouldFail = false
    await refresh()
    expect(error.value).toBe(null)
    expect(data.value).toBe(42)
  })

  it('keepPreviousData (default true): data remains visible during refresh', async () => {
    let shouldReturn = 1
    const d = deferred<number>()
    const fetcher = vi.fn(() => {
      if (shouldReturn === 1) return Promise.resolve(1)
      return d.promise
    })
    const { data, isLoading, refresh } = useApiResource(fetcher)

    await refresh()
    expect(data.value).toBe(1)

    shouldReturn = 2
    const secondRefresh = refresh()
    // Still loading, but data hasn't been cleared
    expect(isLoading.value).toBe(true)
    expect(data.value).toBe(1)

    d.resolve(2)
    await secondRefresh
    expect(data.value).toBe(2)
  })

  it('keepPreviousData=false: data clears on every refresh', async () => {
    let shouldReturn = 1
    const d = deferred<number>()
    const fetcher = () => {
      if (shouldReturn === 1) return Promise.resolve(1)
      return d.promise
    }
    const { data, refresh } = useApiResource(fetcher, {
      keepPreviousData: false,
    })

    await refresh()
    expect(data.value).toBe(1)

    shouldReturn = 2
    const p = refresh()
    // data cleared immediately on refresh()
    expect(data.value).toBe(null)

    d.resolve(2)
    await p
    expect(data.value).toBe(2)
  })

  it('race: late-arriving first call does NOT overwrite later result', async () => {
    const first = deferred<number>()
    const second = deferred<number>()
    let call = 0
    const { data, refresh } = useApiResource(() => {
      call += 1
      return call === 1 ? first.promise : second.promise
    })

    const p1 = refresh()
    const p2 = refresh()

    // Second resolves first
    second.resolve(2)
    await p2
    expect(data.value).toBe(2)

    // First resolves LATER — should be discarded
    first.resolve(1)
    await p1
    expect(data.value).toBe(2)
  })

  it('race: late-arriving first error does NOT overwrite later success', async () => {
    const first = deferred<number>()
    const second = deferred<number>()
    let call = 0
    const { data, error, refresh } = useApiResource(() => {
      call += 1
      return call === 1 ? first.promise : second.promise
    })

    const p1 = refresh()
    const p2 = refresh()

    second.resolve(42)
    await p2
    expect(data.value).toBe(42)
    expect(error.value).toBe(null)

    // First rejects late
    first.reject(new Error('late failure'))
    await p1
    // Still success — late error was discarded
    expect(data.value).toBe(42)
    expect(error.value).toBe(null)
  })

  it('immediate: true triggers refresh() on creation', async () => {
    const fetcher = vi.fn(() => Promise.resolve(42))
    const { data } = useApiResource(fetcher, { immediate: true })

    // Let the microtask flush
    await nextTick()
    await nextTick()

    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(data.value).toBe(42)
  })

  it('immediate: false (default) does not auto-fetch', () => {
    const fetcher = vi.fn(() => Promise.resolve(42))
    useApiResource(fetcher)
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('onScopeDispose: in-flight fetches do not update disposed scope', async () => {
    const d = deferred<number>()
    const scope = effectScope()

    let ref1!: ReturnType<typeof useApiResource<number>>
    scope.run(() => {
      ref1 = useApiResource(() => d.promise)
    })

    const p = ref1.refresh()
    expect(ref1.isLoading.value).toBe(true)

    // Simulate component unmount
    scope.stop()

    d.resolve(42)
    await p

    // Scope was disposed, so the refs were NOT updated — isLoading remains
    // frozen at its last-observed state, data/error untouched.
    expect(ref1.data.value).toBe(null)
    expect(ref1.error.value).toBe(null)
  })

  it('AbortController: passes signal to fetcher on each refresh()', async () => {
    const signals: (AbortSignal | undefined)[] = []
    const { refresh } = useApiResource((signal) => {
      signals.push(signal)
      return Promise.resolve(1)
    })

    await refresh()
    await refresh()

    expect(signals).toHaveLength(2)
    expect(signals[0]).toBeInstanceOf(AbortSignal)
    expect(signals[1]).toBeInstanceOf(AbortSignal)
    // Each call gets a distinct signal
    expect(signals[0]).not.toBe(signals[1])
  })

  it('AbortController: aborts previous in-flight signal when new refresh() starts', async () => {
    const d = deferred<number>()
    let capturedSignal: AbortSignal | undefined

    const { refresh } = useApiResource((signal) => {
      capturedSignal = signal
      return d.promise
    })

    // Start first refresh — captures signal from first controller
    const p1 = refresh()
    const firstSignal = capturedSignal!
    expect(firstSignal.aborted).toBe(false)

    // Start second refresh — first controller must be aborted
    const p2 = refresh()
    expect(firstSignal.aborted).toBe(true)

    d.resolve(99)
    await Promise.allSettled([p1, p2])
  })

  it('AbortController: AbortError from fetcher does not surface in error.value', async () => {
    const abortError = new DOMException('Aborted', 'AbortError')
    const { data, error, isLoading, refresh } = useApiResource(() =>
      Promise.reject(abortError)
    )

    await refresh()

    // AbortError is swallowed — not a user-visible failure
    expect(error.value).toBe(null)
    expect(data.value).toBe(null)
    expect(isLoading.value).toBe(false)
  })

  it('AbortController: onScopeDispose aborts the active controller', async () => {
    const d = deferred<number>()
    const scope = effectScope()
    let capturedSignal: AbortSignal | undefined

    let resource!: ReturnType<typeof useApiResource<number>>
    scope.run(() => {
      resource = useApiResource((signal) => {
        capturedSignal = signal
        return d.promise
      })
    })

    resource.refresh()
    const signalBeforeDispose = capturedSignal!
    expect(signalBeforeDispose.aborted).toBe(false)

    // Disposing the scope should abort the active controller
    scope.stop()
    expect(signalBeforeDispose.aborted).toBe(true)
  })
})
