// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useThemeVariant.test.ts — default-variant resolution + persistence (Issue #10461)
 *
 * The user GUI defaults to the warm "ember" palette, overridable at build time via
 * VITE_DEFAULT_THEME_VARIANT. A saved user choice always wins. The composable is a
 * module-level singleton, so each test resets modules and imports a fresh instance.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'

const KEY = 'autobot-theme-variant'

async function freshComposable() {
  vi.resetModules()
  const mod = await import('../useThemeVariant')
  return mod.useThemeVariant()
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme-variant')
  vi.unstubAllEnvs()
})

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('useThemeVariant — default resolution', () => {
  it('defaults to ember when nothing is stored and no env override', async () => {
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('ember')
  })

  it('honours VITE_DEFAULT_THEME_VARIANT=default override', async () => {
    vi.stubEnv('VITE_DEFAULT_THEME_VARIANT', 'default')
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('default')
  })

  it('falls back to ember when the env override is an unknown value', async () => {
    vi.stubEnv('VITE_DEFAULT_THEME_VARIANT', 'not-a-real-theme')
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('ember')
  })

  it('a saved choice wins over the default', async () => {
    localStorage.setItem(KEY, 'default')
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('default')
  })

  it('ignores an unknown saved value and uses the default (ember)', async () => {
    localStorage.setItem(KEY, 'garbage')
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('ember')
  })

  it('exposes both known variants', async () => {
    const { availableVariants } = await freshComposable()
    expect(availableVariants).toEqual(['default', 'ember'])
  })
})

describe('useThemeVariant — DOM application + persistence', () => {
  it('applies data-theme-variant=ember to <html> by default (no-flash parity)', async () => {
    await freshComposable()
    expect(document.documentElement.getAttribute('data-theme-variant')).toBe('ember')
  })

  it('removes the attribute when switching to default, and persists the choice', async () => {
    const { setThemeVariant } = await freshComposable()
    setThemeVariant('default')
    await nextTick()
    expect(document.documentElement.getAttribute('data-theme-variant')).toBeNull()
    expect(localStorage.getItem(KEY)).toBe('default')
  })

  it('sets the attribute and persists when switching back to ember', async () => {
    localStorage.setItem(KEY, 'default')
    const { setThemeVariant } = await freshComposable()
    setThemeVariant('ember')
    await nextTick()
    expect(document.documentElement.getAttribute('data-theme-variant')).toBe('ember')
    expect(localStorage.getItem(KEY)).toBe('ember')
  })
})
