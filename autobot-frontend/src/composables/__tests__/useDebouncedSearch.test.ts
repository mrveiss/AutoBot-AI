// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Unit tests for useDebouncedSearch (#5198)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, ref, nextTick } from 'vue'

import { useDebouncedSearch } from '../useDebouncedSearch'

describe('useDebouncedSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('initial state: results null, not searching, no error', () => {
    const scope = effectScope()
    scope.run(() => {
      const query = ref('')
      const onSearch = vi.fn().mockResolvedValue('result')
      const { results, isSearching, error } = useDebouncedSearch(query, onSearch)

      expect(results.value).toBeNull()
      expect(isSearching.value).toBe(false)
      expect(error.value).toBeNull()
      expect(onSearch).not.toHaveBeenCalled()
    })
    scope.stop()
  })

  it('typing query triggers debounced onSearch after delayMs', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('')
      const onSearch = vi.fn().mockResolvedValue('hits')
      const { results, isSearching } = useDebouncedSearch(query, onSearch, { delayMs: 300 })

      query.value = 'hello'
      await nextTick()

      // Within delay window, not yet fired
      vi.advanceTimersByTime(299)
      expect(onSearch).not.toHaveBeenCalled()
      expect(isSearching.value).toBe(false)

      // Cross the threshold
      vi.advanceTimersByTime(1)
      expect(onSearch).toHaveBeenCalledTimes(1)
      expect(onSearch).toHaveBeenCalledWith('hello')

      // Let the mock promise resolve
      await vi.runAllTimersAsync()
      expect(results.value).toBe('hits')
      expect(isSearching.value).toBe(false)
    })
    scope.stop()
  })

  it('query shorter than minLength does not fire onSearch and clears results', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('')
      const onSearch = vi.fn().mockResolvedValue('hits')
      const { results } = useDebouncedSearch(query, onSearch, { delayMs: 100, minLength: 3 })

      // First a valid query so results has a value
      query.value = 'valid'
      await nextTick()
      vi.advanceTimersByTime(100)
      await vi.runAllTimersAsync()
      expect(results.value).toBe('hits')
      expect(onSearch).toHaveBeenCalledTimes(1)

      // Now a too-short query
      query.value = 'hi'
      await nextTick()
      vi.advanceTimersByTime(100)
      await vi.runAllTimersAsync()
      expect(onSearch).toHaveBeenCalledTimes(1) // unchanged
      expect(results.value).toBeNull() // cleared
    })
    scope.stop()
  })

  it('whitespace-only query is treated as too short', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('')
      const onSearch = vi.fn().mockResolvedValue('hits')
      useDebouncedSearch(query, onSearch, { delayMs: 100, minLength: 1 })

      query.value = '   '
      await nextTick()
      vi.advanceTimersByTime(100)
      await vi.runAllTimersAsync()
      expect(onSearch).not.toHaveBeenCalled()
    })
    scope.stop()
  })

  it('rapid retyping: only last query is awaited (race guard)', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('')
      const callArgs: string[] = []
      let resolveFirst!: (v: string) => void
      let resolveSecond!: (v: string) => void

      const onSearch = vi.fn((q: string) => {
        callArgs.push(q)
        if (callArgs.length === 1) {
          return new Promise<string>((resolve) => {
            resolveFirst = resolve
          })
        }
        return new Promise<string>((resolve) => {
          resolveSecond = resolve
        })
      })

      const { results } = useDebouncedSearch(query, onSearch, { delayMs: 100 })

      // First query fires
      query.value = 'foo'
      await nextTick()
      vi.advanceTimersByTime(100)
      expect(onSearch).toHaveBeenCalledWith('foo')

      // Retype before first resolves; debounce will fire again
      query.value = 'foobar'
      await nextTick()
      vi.advanceTimersByTime(100)
      expect(onSearch).toHaveBeenCalledWith('foobar')

      // Resolve OUT OF ORDER: the stale first resolves AFTER the fresh second
      resolveSecond('result-for-foobar')
      await vi.runAllTimersAsync()
      expect(results.value).toBe('result-for-foobar')

      resolveFirst('result-for-foo')
      await vi.runAllTimersAsync()
      // Stale response must NOT overwrite the fresh result
      expect(results.value).toBe('result-for-foobar')
    })
    scope.stop()
  })

  it('error ref populated when onSearch throws', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('')
      const boom = new Error('search failed')
      const onSearch = vi.fn().mockRejectedValue(boom)
      const { results, error, isSearching } = useDebouncedSearch(query, onSearch, {
        delayMs: 50
      })

      query.value = 'x'
      await nextTick()
      vi.advanceTimersByTime(50)
      await vi.runAllTimersAsync()

      expect(error.value).toBe(boom)
      expect(results.value).toBeNull()
      expect(isSearching.value).toBe(false)
    })
    scope.stop()
  })

  it('non-Error throw is wrapped into Error', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('')
      const onSearch = vi.fn().mockRejectedValue('string failure')
      const { error } = useDebouncedSearch(query, onSearch, { delayMs: 10 })

      query.value = 'x'
      await nextTick()
      vi.advanceTimersByTime(10)
      await vi.runAllTimersAsync()

      expect(error.value).toBeInstanceOf(Error)
      expect(error.value?.message).toBe('string failure')
    })
    scope.stop()
  })

  it('flush() bypasses debounce and runs immediately', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('immediate')
      const onSearch = vi.fn().mockResolvedValue('flushed')
      const { results, flush } = useDebouncedSearch(query, onSearch, { delayMs: 5000 })

      flush()
      await vi.runAllTimersAsync()

      expect(onSearch).toHaveBeenCalledTimes(1)
      expect(onSearch).toHaveBeenCalledWith('immediate')
      expect(results.value).toBe('flushed')
    })
    scope.stop()
  })

  it('cancel() prevents subsequent state updates from pending searches', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('')
      let resolve!: (v: string) => void
      const onSearch = vi.fn(
        () =>
          new Promise<string>((r) => {
            resolve = r
          })
      )
      const { results, isSearching, cancel } = useDebouncedSearch(query, onSearch, {
        delayMs: 50
      })

      query.value = 'foo'
      await nextTick()
      vi.advanceTimersByTime(50)
      expect(onSearch).toHaveBeenCalledTimes(1)
      expect(isSearching.value).toBe(true)

      cancel()
      expect(isSearching.value).toBe(false)

      resolve('late-result')
      await vi.runAllTimersAsync()
      expect(results.value).toBeNull() // suppressed
    })
    scope.stop()
  })

  it('onScopeDispose cancels in-flight search when scope stops', async () => {
    const scope = effectScope()
    const query = ref('')
    let resolve!: (v: string) => void
    const onSearch = vi.fn(
      () =>
        new Promise<string>((r) => {
          resolve = r
        })
    )

    let handle!: ReturnType<typeof useDebouncedSearch<string>>
    scope.run(() => {
      handle = useDebouncedSearch<string>(query, onSearch, { delayMs: 20 })
    })

    query.value = 'foo'
    await nextTick()
    vi.advanceTimersByTime(20)
    expect(onSearch).toHaveBeenCalledTimes(1)

    scope.stop()
    resolve('after-dispose')
    await vi.runAllTimersAsync()

    expect(handle.results.value).toBeNull()
    expect(handle.isSearching.value).toBe(false)
  })

  it('custom delayMs respected', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('')
      const onSearch = vi.fn().mockResolvedValue('r')
      useDebouncedSearch(query, onSearch, { delayMs: 1000 })

      query.value = 'hello'
      await nextTick()
      vi.advanceTimersByTime(500)
      expect(onSearch).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      expect(onSearch).toHaveBeenCalledTimes(1)
    })
    scope.stop()
  })

  it('immediate: true fires watcher synchronously on mount', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('seed')
      const onSearch = vi.fn().mockResolvedValue('r')
      useDebouncedSearch(query, onSearch, { delayMs: 100, immediate: true })

      // Watcher schedules the debounced call immediately
      vi.advanceTimersByTime(100)
      await vi.runAllTimersAsync()
      expect(onSearch).toHaveBeenCalledWith('seed')
    })
    scope.stop()
  })

  it('immediate: false (default) does not fire for initial value', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('seed')
      const onSearch = vi.fn().mockResolvedValue('r')
      useDebouncedSearch(query, onSearch, { delayMs: 100 })

      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()
      expect(onSearch).not.toHaveBeenCalled()
    })
    scope.stop()
  })

  it('isSearching toggles true during in-flight and false after resolve', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const query = ref('')
      let resolve!: (v: string) => void
      const onSearch = vi.fn(
        () =>
          new Promise<string>((r) => {
            resolve = r
          })
      )
      const { isSearching } = useDebouncedSearch(query, onSearch, { delayMs: 50 })

      query.value = 'foo'
      await nextTick()
      vi.advanceTimersByTime(50)
      expect(isSearching.value).toBe(true)

      resolve('ok')
      await vi.runAllTimersAsync()
      expect(isSearching.value).toBe(false)
    })
    scope.stop()
  })
})
