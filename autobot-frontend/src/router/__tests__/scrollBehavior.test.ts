// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14770: the router scrolls smoothly on every navigation, which is motion the
 * app initiates and the stylesheet's global reduced-motion rule cannot reach —
 * `scroll-behavior: auto !important` does not override a behaviour passed
 * programmatically.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { routeScrollBehavior } from '../scrollBehavior'

function stubReducedMotion(matches: boolean) {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('routeScrollBehavior (#14770)', () => {
  it('glides to the top of a new page by default', () => {
    stubReducedMotion(false)
    expect(routeScrollBehavior({ hash: '' }, null)).toEqual({ top: 0, behavior: 'smooth' })
  })

  it('jumps instead of gliding when reduced motion is requested', () => {
    stubReducedMotion(true)
    expect(routeScrollBehavior({ hash: '' }, null)).toEqual({ top: 0, behavior: 'auto' })
  })

  it('glides to an anchor by default', () => {
    stubReducedMotion(false)
    expect(routeScrollBehavior({ hash: '#step-3' }, null)).toEqual({ el: '#step-3', behavior: 'smooth' })
  })

  it('jumps to an anchor when reduced motion is requested', () => {
    stubReducedMotion(true)
    expect(routeScrollBehavior({ hash: '#step-3' }, null)).toEqual({ el: '#step-3', behavior: 'auto' })
  })

  it('returns a restored history position untouched, whatever the preference', () => {
    // Not app-initiated motion: the browser is reinstating what the user
    // already had, and the position carries no behaviour to soften. Asserted
    // under BOTH settings so a future change cannot start rewriting it under
    // one of them unnoticed.
    const saved = { left: 40, top: 900 }

    stubReducedMotion(false)
    expect(routeScrollBehavior({ hash: '' }, saved)).toBe(saved)

    stubReducedMotion(true)
    expect(routeScrollBehavior({ hash: '#anywhere' }, saved)).toBe(saved)
  })

  it('does not throw where matchMedia is unavailable', () => {
    vi.stubGlobal('matchMedia', undefined)
    expect(routeScrollBehavior({ hash: '' }, null)).toEqual({ top: 0, behavior: 'smooth' })
  })
})
