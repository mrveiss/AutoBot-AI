// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useThemeVariant.test.ts — default-variant resolution + persistence (Issue #10461)
 *
 * The user GUI defaults to the Refined palette (`default`; ember was the default until
 * #18161), overridable at build time via
 * VITE_DEFAULT_THEME_VARIANT. A saved user choice always wins. The composable is a
 * module-level singleton, so each test resets modules and imports a fresh instance.
 */
import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'

// Installed-theme registry is exercised by useThemeVariantRuntime.test.ts; here we
// stub it so the fire-and-forget loadInstalledThemes() in initVariant() is inert and
// the built-in availableVariants stay deterministic.
vi.mock('../useThemeRegistry', () => ({
  fetchInstalledThemes: vi.fn().mockResolvedValue([]),
}))

const KEY = 'autobot-theme-variant'

async function freshComposable() {
  vi.resetModules()
  const mod = await import('../useThemeVariant')
  return mod.useThemeVariant()
}


/**
 * Each test resets modules and re-imports a fresh instance. The first import also
 * pays the cold transform of the whole import graph, which under load outran the
 * default 10 s test timeout (pre-push, #18254). Warm the transform once here, with
 * its own budget, so every test measures only its own work.
 */
const COLD_IMPORT_MS = 60_000
beforeAll(async () => {
  await import('../useThemeVariant')
}, COLD_IMPORT_MS)

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme-variant')
  vi.unstubAllEnvs()
})

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('useThemeVariant — default resolution', () => {
  it('defaults to default (not ember) when nothing is stored and no env override', async () => {
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('default')
  })

  it('honours VITE_DEFAULT_THEME_VARIANT=ember override', async () => {
    vi.stubEnv('VITE_DEFAULT_THEME_VARIANT', 'ember')
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('ember')
  })

  it('falls back to default when the env override is an unknown value', async () => {
    vi.stubEnv('VITE_DEFAULT_THEME_VARIANT', 'not-a-real-theme')
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('default')
  })

  it('a saved choice wins over the default', async () => {
    localStorage.setItem(KEY, 'ember')
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('ember')
  })

  it('ignores an unknown saved value and uses the default', async () => {
    localStorage.setItem(KEY, 'garbage')
    const { themeVariant } = await freshComposable()
    expect(themeVariant.value).toBe('default')
  })

  it('exposes both known variants', async () => {
    const { availableVariants } = await freshComposable()
    expect(availableVariants.value).toEqual(['default', 'ember'])
  })
})

describe('useThemeVariant — DOM application + persistence', () => {
  it('sets no data-theme-variant on <html> by default (no-flash parity)', async () => {
    await freshComposable()
    expect(document.documentElement.getAttribute('data-theme-variant')).toBeNull()
  })

  it('applies a saved ember variant to <html> on init', async () => {
    localStorage.setItem(KEY, 'ember')
    await freshComposable()
    expect(document.documentElement.getAttribute('data-theme-variant')).toBe('ember')
  })

  it('removes the attribute when switching to default, and persists the choice', async () => {
    localStorage.setItem(KEY, 'ember')
    const { setThemeVariant } = await freshComposable()
    await setThemeVariant('default')
    await nextTick()
    expect(document.documentElement.getAttribute('data-theme-variant')).toBeNull()
    expect(localStorage.getItem(KEY)).toBe('default')
  })

  it('sets the attribute and persists when switching to ember', async () => {
    const { setThemeVariant } = await freshComposable()
    await setThemeVariant('ember')
    await nextTick()
    expect(document.documentElement.getAttribute('data-theme-variant')).toBe('ember')
    expect(localStorage.getItem(KEY)).toBe('ember')
  })
})
