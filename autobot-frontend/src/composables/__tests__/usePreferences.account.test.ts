// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * usePreferences account sync round-trip (#18240): ui_mode, ui_start and
 * theme_variant travel with the appearance prefs. The endpoint is a partial
 * PATCH, so a save must still send every field it owns, and a load must apply
 * the three new ones.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.setConfig({ testTimeout: 30_000 }) // first dynamic import of the preference stack is cold under CI load

const apiGet = vi.fn()
const apiPatch = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => apiGet(...args),
    patch: (...args: unknown[]) => apiPatch(...args),
    put: vi.fn(),
  },
}))
vi.mock('@/i18n', () => ({ setLocale: () => Promise.resolve() }))
vi.mock('../useThemeRegistry', () => ({ fetchInstalledThemes: () => Promise.resolve([]) }))

async function fresh() {
  vi.resetModules()
  const prefs = (await import('../usePreferences')).usePreferences()
  const ui = (await import('../useUiMode')).useUiMode()
  const variant = (await import('../useThemeVariant')).useThemeVariant()
  return { prefs, ui, variant }
}

beforeEach(() => {
  localStorage.clear()
  apiGet.mockReset()
  apiPatch.mockReset()
  apiPatch.mockResolvedValue({})
  document.documentElement.removeAttribute('data-ui')
  document.documentElement.removeAttribute('data-theme-variant')
})

describe('saveAppearanceToBackend', () => {
  it('sends the three new fields together with the existing ones', async () => {
    const { prefs, ui } = await fresh()
    ui.setMode('minimal')
    ui.setStart('full')
    await prefs.saveAppearanceToBackend()

    expect(apiPatch).toHaveBeenCalledTimes(1)
    const payload = apiPatch.mock.calls[0][1] as Record<string, unknown>
    expect(payload).toMatchObject({ ui_mode: 'minimal', ui_start: 'full', theme_variant: 'default' })
    for (const key of ['reasoning_effort', 'theme', 'accent_color', 'layout_density', 'font_size', 'theme_preset']) {
      expect(payload, key).toHaveProperty(key)
    }
  })
})

describe('loadAppearanceFromBackend', () => {
  it('applies ui_mode with start=last', async () => {
    apiGet.mockResolvedValue({ data: { preferences: { ui_mode: 'minimal', ui_start: 'last', theme_variant: 'default' } } })
    const { prefs, ui } = await fresh()
    await prefs.loadAppearanceFromBackend({ freshSignIn: true })
    expect(ui.uiMode.value).toBe('minimal')
    expect(document.documentElement.getAttribute('data-ui')).toBe('minimal')
  })

  it('opens in the pinned start mode when ui_start is not last', async () => {
    apiGet.mockResolvedValue({ data: { preferences: { ui_mode: 'full', ui_start: 'minimal' } } })
    const { prefs, ui } = await fresh()
    await prefs.loadAppearanceFromBackend({ freshSignIn: true })
    expect(ui.uiMode.value).toBe('minimal')
    expect(ui.uiStart.value).toBe('minimal')
  })

  it('applies a non-default account theme_variant', async () => {
    apiGet.mockResolvedValue({ data: { preferences: { theme_variant: 'ember' } } })
    const { prefs, variant } = await fresh()
    await prefs.loadAppearanceFromBackend({ freshSignIn: true })
    expect(variant.themeVariant.value).toBe('ember')
  })

  it("keeps a device that never chose when the account says 'default'", async () => {
    vi.stubEnv('VITE_DEFAULT_THEME_VARIANT', 'ember')
    apiGet.mockResolvedValue({ data: { preferences: { theme_variant: 'default' } } })
    const { prefs, variant } = await fresh()
    await prefs.loadAppearanceFromBackend({ freshSignIn: true })
    expect(variant.themeVariant.value).toBe('ember')
    vi.unstubAllEnvs()
  })

  it("lets the account's 'default' override a device that explicitly chose ember", async () => {
    localStorage.setItem('autobot-theme-variant', 'ember')
    apiGet.mockResolvedValue({ data: { preferences: { theme_variant: 'default' } } })
    const { prefs, variant } = await fresh()
    await prefs.loadAppearanceFromBackend({ freshSignIn: true })
    expect(variant.themeVariant.value).toBe('default')
  })

  it('leaves the mode and variant alone when the account carries none', async () => {
    localStorage.setItem('autobot-ui-mode', 'minimal')
    apiGet.mockResolvedValue({ data: { preferences: { font_size: 'large' } } })
    const { prefs, ui } = await fresh()
    await prefs.loadAppearanceFromBackend({ freshSignIn: true })
    expect(ui.uiMode.value).toBe('minimal')
  })
})

describe('loadAppearanceFromBackend on a session restore (no fresh sign-in)', () => {
  it('keeps the device mode and start, whatever the account holds', async () => {
    localStorage.setItem('autobot-ui-mode', 'full')
    apiGet.mockResolvedValue({ data: { preferences: { ui_mode: 'minimal', ui_start: 'minimal' } } })
    const { prefs, ui } = await fresh()
    await prefs.loadAppearanceFromBackend()
    expect(ui.uiMode.value).toBe('full')
    expect(ui.uiStart.value).toBe('last')
    expect(document.documentElement.getAttribute('data-ui')).toBe('full')
  })

  it('keeps the device theme variant', async () => {
    localStorage.setItem('autobot-theme-variant', 'ember')
    apiGet.mockResolvedValue({ data: { preferences: { theme_variant: 'default' } } })
    const { prefs, variant } = await fresh()
    await prefs.loadAppearanceFromBackend()
    expect(variant.themeVariant.value).toBe('ember')
  })

  it('a toggle then a reload keeps the toggled mode; a fresh sign-in replaces it', async () => {
    apiGet.mockResolvedValue({ data: { preferences: { ui_mode: 'full', ui_start: 'last' } } })
    const first = await fresh()
    first.ui.setMode('minimal') // the user's in-session toggle, written to the device
    const reloaded = await fresh() // reload: modules re-read localStorage
    await reloaded.prefs.loadAppearanceFromBackend()
    expect(reloaded.ui.uiMode.value).toBe('minimal')

    await reloaded.prefs.loadAppearanceFromBackend({ freshSignIn: true })
    expect(reloaded.ui.uiMode.value).toBe('full')
  })
})

describe('every appearance field follows the sign-in rule', () => {
  const account = { theme: 'dark', accent_color: 'green', layout_density: 'spacious', font_size: 'large', reasoning_effort: 'high' }

  it('keeps the device theme, density and font size on a restore, without asking the account', async () => {
    localStorage.setItem('autobot-theme', 'light')
    apiGet.mockResolvedValue({ data: { preferences: account } })
    const { prefs } = await fresh()
    const { usePreferences } = await import('../usePreferences')
    const before = { d: usePreferences().layoutDensity.value, f: usePreferences().fontSize.value }
    await prefs.loadAppearanceFromBackend()
    const after = usePreferences()
    expect(after.layoutDensity.value).toBe(before.d)
    expect(after.fontSize.value).toBe(before.f)
    expect(after.fontSize.value).not.toBe('large')
    expect(after.layoutDensity.value).not.toBe('spacious')
    expect(localStorage.getItem('autobot-theme')).toBe('light')
  })

  it('applies the account theme, density and font size at a fresh sign-in', async () => {
    localStorage.setItem('autobot-theme', 'light')
    apiGet.mockResolvedValue({ data: { preferences: account } })
    const { prefs } = await fresh()
    await prefs.loadAppearanceFromBackend({ freshSignIn: true })
    const { usePreferences } = await import('../usePreferences')
    expect(usePreferences().layoutDensity.value).toBe('spacious')
    expect(usePreferences().fontSize.value).toBe('large')
    expect(localStorage.getItem('autobot-theme')).toBe('dark')
  })
})
