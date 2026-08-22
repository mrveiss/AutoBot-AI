// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14770: `scrollTo({ behavior: 'smooth' })` is motion the app initiates, so
 * the stylesheet's global reduced-motion rule cannot reach it.
 *
 * This composable defaulted to `'smooth'` in a module-level constant. Two
 * problems with that beyond the preference itself: the value was frozen at
 * import time, and `scrollToTop`/`scrollToBottom` passed it down as an
 * explicit argument, so the default could never be re-decided per call.
 *
 * Asserted at the boundary — the object handed to the container's own
 * `scrollTo` — rather than on the resolver, so an unwired resolver fails.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { ref } from 'vue'
import { useVirtualScroll } from '../useVirtualScroll'

function stubReducedMotion(matches: boolean) {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
}

/** A container whose `scrollTo` records what it was asked to do. */
function harness(options: Record<string, unknown> = {}) {
  const scrollTo = vi.fn()
  const container = {
    scrollTo,
    clientHeight: 400,
    clientWidth: 400,
    scrollTop: 0,
    scrollLeft: 0,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }
  const items = ref(Array.from({ length: 50 }, (_, i) => ({ id: i })))
  const vs = useVirtualScroll(items, { estimatedItemHeight: 20, ...options })
  ;(vs.containerRef as { value: unknown }).value = container
  return { vs, scrollTo }
}

function behaviorOf(scrollTo: ReturnType<typeof vi.fn>): unknown {
  return (scrollTo.mock.calls.at(-1)?.[0] as { behavior?: unknown } | undefined)?.behavior
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useVirtualScroll honours prefers-reduced-motion (#14770)', () => {
  it('scrolls smoothly by default', () => {
    stubReducedMotion(false)
    const { vs, scrollTo } = harness()

    vs.scrollToIndex(10)

    expect(scrollTo).toHaveBeenCalled()
    expect(behaviorOf(scrollTo)).toBe('smooth')
  })

  it('jumps when the user has asked for reduced motion', () => {
    stubReducedMotion(true)
    const { vs, scrollTo } = harness()

    vs.scrollToIndex(10)

    expect(scrollTo).toHaveBeenCalled()
    expect(behaviorOf(scrollTo)).toBe('auto')
  })

  it('applies the same rule to scrollToTop and scrollToBottom', () => {
    // These passed the frozen default down as an explicit argument, which is
    // what stopped it being re-decided per call.
    stubReducedMotion(true)
    const { vs, scrollTo } = harness()

    vs.scrollToTop()
    expect(behaviorOf(scrollTo)).toBe('auto')

    vs.scrollToBottom()
    expect(behaviorOf(scrollTo)).toBe('auto')
  })

  it('honours an explicitly passed behaviour over the preference', () => {
    // A caller that has genuinely decided is not second-guessed — the
    // preference supplies a default, it does not veto an instruction.
    stubReducedMotion(true)
    const { vs, scrollTo } = harness()

    vs.scrollToIndex(10, 'smooth')

    expect(behaviorOf(scrollTo)).toBe('smooth')
  })

  it('honours an explicit option over the preference', () => {
    stubReducedMotion(true)
    const { vs, scrollTo } = harness({ scrollBehavior: 'smooth' })

    vs.scrollToIndex(10)

    expect(behaviorOf(scrollTo)).toBe('smooth')
  })
})
