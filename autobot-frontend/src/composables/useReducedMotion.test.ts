// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14770: the single source for `prefers-reduced-motion` in JavaScript.
 *
 * The environment cases are the point of most of these. This runs in SSR, in
 * jsdom, and in browsers, and a motion preference must never be the thing that
 * throws — an absent or hostile `matchMedia` has to read as "no stated
 * preference", not as an exception on a render path.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { effectScope } from 'vue'
import { isReducedMotion, scrollBehavior, useReducedMotion } from './useReducedMotion'

/** Install a `matchMedia` that reports `matches` and records its listeners. */
function stubMatchMedia(matches: boolean) {
  const listeners: ((e: MediaQueryListEvent) => void)[] = []
  const query = {
    matches,
    media: '(prefers-reduced-motion: reduce)',
    addEventListener: vi.fn((_t: string, fn: (e: MediaQueryListEvent) => void) => listeners.push(fn)),
    removeEventListener: vi.fn((_t: string, fn: (e: MediaQueryListEvent) => void) => {
      const i = listeners.indexOf(fn)
      if (i >= 0) listeners.splice(i, 1)
    }),
  }
  vi.stubGlobal('matchMedia', vi.fn(() => query))
  return { query, listeners, emit: (m: boolean) => listeners.forEach((fn) => fn({ matches: m } as MediaQueryListEvent)) }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('isReducedMotion', () => {
  it('reports the preference when the user has set it', () => {
    stubMatchMedia(true)
    expect(isReducedMotion()).toBe(true)
  })

  it('reports false when the user has not', () => {
    stubMatchMedia(false)
    expect(isReducedMotion()).toBe(false)
  })

  it('reads live rather than caching, so a mid-session change is seen', () => {
    // No module-level cache is deliberate: a cached value would also leak one
    // test's stubbed preference into the next.
    stubMatchMedia(false)
    expect(isReducedMotion()).toBe(false)
    stubMatchMedia(true)
    expect(isReducedMotion()).toBe(true)
  })

  it('treats an absent matchMedia as no preference instead of throwing', () => {
    vi.stubGlobal('matchMedia', undefined)
    expect(() => isReducedMotion()).not.toThrow()
    expect(isReducedMotion()).toBe(false)
  })

  it('treats a throwing matchMedia as no preference', () => {
    vi.stubGlobal('matchMedia', () => {
      throw new Error('unsupported media feature')
    })
    expect(isReducedMotion()).toBe(false)
  })
})

describe('scrollBehavior', () => {
  it('is smooth by default', () => {
    stubMatchMedia(false)
    expect(scrollBehavior()).toBe('smooth')
  })

  it('is auto when reduced motion is requested', () => {
    stubMatchMedia(true)
    expect(scrollBehavior()).toBe('auto')
  })
})

describe('useReducedMotion', () => {
  it('starts from the current preference', () => {
    stubMatchMedia(true)
    const scope = effectScope()
    const state = scope.run(() => useReducedMotion())!
    expect(state.prefersReducedMotion.value).toBe(true)
    scope.stop()
  })

  it('tracks a change made after mount', () => {
    const mm = stubMatchMedia(false)
    const scope = effectScope()
    const state = scope.run(() => useReducedMotion())!
    expect(state.prefersReducedMotion.value).toBe(false)

    mm.emit(true)

    expect(state.prefersReducedMotion.value).toBe(true)
    scope.stop()
  })

  it('removes its listener when the scope is disposed', () => {
    const mm = stubMatchMedia(false)
    const scope = effectScope()
    scope.run(() => useReducedMotion())
    expect(mm.listeners).toHaveLength(1)

    scope.stop()

    expect(mm.query.removeEventListener).toHaveBeenCalled()
    expect(mm.listeners).toHaveLength(0)
  })

  it('subscribes through the legacy addListener where addEventListener is absent', () => {
    // Pre-2019 spelling; some environments still expose only this one, and a
    // missing modern listener must not silently drop the subscription.
    const listeners: ((e: MediaQueryListEvent) => void)[] = []
    const removeListener = vi.fn()
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: false,
        addListener: (fn: (e: MediaQueryListEvent) => void) => listeners.push(fn),
        removeListener,
      })),
    )
    const scope = effectScope()
    const state = scope.run(() => useReducedMotion())!
    expect(listeners).toHaveLength(1)

    listeners[0]({ matches: true } as MediaQueryListEvent)
    expect(state.prefersReducedMotion.value).toBe(true)

    scope.stop()
    expect(removeListener).toHaveBeenCalled()
  })

  it('still returns a usable ref when matchMedia throws', () => {
    vi.stubGlobal('matchMedia', () => {
      throw new Error('unsupported media feature')
    })
    const scope = effectScope()
    const state = scope.run(() => useReducedMotion())!
    expect(state.prefersReducedMotion.value).toBe(false)
    scope.stop()
  })

  it('still returns a usable ref where matchMedia is absent', () => {
    vi.stubGlobal('matchMedia', undefined)
    const scope = effectScope()
    const state = scope.run(() => useReducedMotion())!
    expect(state.prefersReducedMotion.value).toBe(false)
    scope.stop()
  })
})
