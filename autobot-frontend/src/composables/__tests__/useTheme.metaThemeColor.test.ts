// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useTheme is the only writer of data-theme (#18240), so it also owns the
 * mobile browser chrome colour that useUserStore#applyTheme used to set from
 * two hardcoded hex values. It now follows the active theme's surface token.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

beforeEach(() => {
  localStorage.clear()
  document.head.innerHTML = '<meta name="theme-color" content="initial">'
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.removeProperty('--bg-secondary')
})

describe('useTheme meta theme-color', () => {
  it('sets data-theme and points <meta theme-color> at the surface token', async () => {
    vi.resetModules()
    document.documentElement.style.setProperty('--bg-secondary', '#123456')
    const { useTheme } = await import('../useTheme')
    useTheme().setTheme('dark')

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute('content')).toBe('#123456')
  })

  it('leaves the meta tag alone when the token does not resolve', async () => {
    vi.resetModules()
    const { useTheme } = await import('../useTheme')
    useTheme().setTheme('light')

    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute('content')).toBe('initial')
  })
})
