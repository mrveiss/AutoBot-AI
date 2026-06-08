// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Unit tests for useDebounce / useDebouncedFn / useDebounceWithLoading (#5318)
 *
 * Verifies cleanup works via onScopeDispose instead of onUnmounted, which
 * previously emitted "onUnmounted is called when there is no active
 * component instance" warnings when used outside component setup().
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, ref, nextTick } from 'vue'
import { useDebounce, useDebouncedFn, useDebounceWithLoading } from '../useDebounce'

describe('useDebounce (scope-aware cleanup)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('does not warn outside component setup when using useDebouncedFn in effectScope', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const scope = effectScope()
    scope.run(() => {
      const fn = vi.fn()
      const { debouncedFn } = useDebouncedFn(fn, 100)
      debouncedFn()
    })
    scope.stop()
    expect(warn).not.toHaveBeenCalledWith(
      expect.stringContaining('no active component')
    )
    warn.mockRestore()
  })

  it('does not warn outside component setup when using useDebounce in effectScope', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const scope = effectScope()
    scope.run(() => {
      const source = ref('a')
      useDebounce(source, 100)
    })
    scope.stop()
    expect(warn).not.toHaveBeenCalledWith(
      expect.stringContaining('no active component')
    )
    warn.mockRestore()
  })

  it('does not warn outside component setup when using useDebounceWithLoading in effectScope', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const scope = effectScope()
    scope.run(() => {
      const source = ref('a')
      useDebounceWithLoading(source, 100)
    })
    scope.stop()
    expect(warn).not.toHaveBeenCalledWith(
      expect.stringContaining('no active component')
    )
    warn.mockRestore()
  })

  it('does not warn when called with no active scope at all', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const fn = vi.fn()
    const { debouncedFn, cancel } = useDebouncedFn(fn, 100)
    debouncedFn()
    cancel()
    expect(warn).not.toHaveBeenCalledWith(
      expect.stringContaining('no active component')
    )
    warn.mockRestore()
  })

  it('cancels pending timeout when scope is stopped', async () => {
    const fn = vi.fn()
    const scope = effectScope()
    let debouncedFn: ((...args: unknown[]) => void) | undefined
    scope.run(() => {
      ;({ debouncedFn } = useDebouncedFn(fn, 100))
    })
    debouncedFn!('arg')
    scope.stop()
    vi.advanceTimersByTime(200)
    await nextTick()
    expect(fn).not.toHaveBeenCalled()
  })

  it('stops updating debounced ref after scope is stopped', async () => {
    const source = ref('initial')
    const scope = effectScope()
    let debounced: ReturnType<typeof useDebounce<string>> | undefined
    scope.run(() => {
      debounced = useDebounce(source, 100)
    })
    source.value = 'updated'
    scope.stop()
    vi.advanceTimersByTime(200)
    await nextTick()
    // unwatch() fires on scope dispose, so debounced never receives the new value
    expect(debounced!.value).toBe('initial')
  })
})
