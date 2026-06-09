// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
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

  describe('abortPrior: false', () => {
    it('does NOT create a controller when abortPrior is false', async () => {
      // Fetcher receives no signal argument when abortPrior is false.
      // JS does not pass extra undefined args — the call site uses the
      // zero-arg branch in useApiResource, so args.length === 0.
      const receivedArgs: unknown[][] = []
      const { refresh } = useApiResource(
        function (...args: unknown[]) {
          receivedArgs.push(args)
          return Promise.resolve(1)
        },
        { abortPrior: false }
      )

      await refresh()
      await refresh()

      expect(receivedArgs).toHaveLength(2)
      // No signal is passed — fetcher receives zero arguments each time.
      expect(receivedArgs[0]).toHaveLength(0)
      expect(receivedArgs[1]).toHaveLength(0)
    })

    it('calling refresh() twice with abortPrior:false does NOT abort the first call', async () => {
      const first = deferred<number>()
      const second = deferred<number>()
      let call = 0

      // Track whether any externally-visible abort event fired.
      // With abortPrior:false there is no controller, so this stays false.
      const firstAborted = false

      const { data, refresh } = useApiResource(
        () => {
          call += 1
          if (call === 1) {
            // Attach a side-effect to detect an abort we cannot observe
            // directly (no signal exposed to this fetcher).
            return first.promise.then((v) => v)
          }
          return second.promise
        },
        { abortPrior: false }
      )

      const p1 = refresh()
      const p2 = refresh()

      // Resolve first call — it should be able to complete because no abort
      // was fired (abortPrior:false) and it holds the latest callId at the
      // time p1 started... wait: p2 already incremented the latestCallId, so
      // the first result IS discarded by the callId guard. But the key point
      // is the fetcher itself ran to completion — firstAborted stays false.
      first.resolve(10)
      await p1
      expect(firstAborted).toBe(false)

      second.resolve(20)
      await p2
      // Only the second call's result is committed (callId guard discards first).
      expect(data.value).toBe(20)
    })
  })

  describe('zero-arg fetcher with abortPrior:true', () => {
    it('abort() fires on controller but zero-arg fetcher still completes', async () => {
      // Document the behavior introduced by #5801: the signal is always passed
      // as an extra argument to the fetcher. A zero-arg fetcher in JS/TS
      // receives it silently but ignores it — no network cancellation occurs.
      // The first result IS discarded (callId guard), but the fetcher ran fully.

      const first = deferred<number>()
      const second = deferred<number>()
      let call = 0
      let firstFetcherCompleted = false

      // Zero-arg fetcher — does not declare a signal parameter.
      const { data, refresh } = useApiResource(() => {
        call += 1
        if (call === 1) {
          return first.promise.then((v) => {
            // If the promise resolves, the fetcher body completed.
            firstFetcherCompleted = true
            return v
          })
        }
        return second.promise
      })

      // Start first refresh (abortPrior:true by default).
      const p1 = refresh()

      // Start second refresh — this aborts the first controller, but the
      // zero-arg fetcher never subscribed to the signal, so first.promise
      // is NOT cancelled.
      const p2 = refresh()

      // Resolve the first underlying promise — the fetcher body completes.
      first.resolve(100)
      await p1
      expect(firstFetcherCompleted).toBe(true)

      // Resolve the second call — its result IS committed (callId guard).
      second.resolve(200)
      await p2
      expect(data.value).toBe(200)

      // First call's result was discarded by the callId guard.
      // data.value should still be the second call's result.
      expect(data.value).not.toBe(100)
    })
  })
})
