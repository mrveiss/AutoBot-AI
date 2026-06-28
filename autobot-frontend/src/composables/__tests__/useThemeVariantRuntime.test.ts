// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useThemeVariantRuntime.test.ts — runtime installed-theme delivery (#10472)
 *
 * Installed themes are merged into availableVariants after loadInstalledThemes,
 * and applied by fetching their CSS and adopting a constructed stylesheet
 * (CSP-safe: no inline <style>, no cross-origin <link>).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const AQUA = { id: 'aqua', name: 'Aqua', author: 'me', version: '1.0.0', supports: ['light'] }
const fetchInstalledThemesMock = vi.fn()
vi.mock('../useThemeRegistry', () => ({ fetchInstalledThemes: fetchInstalledThemesMock }))

class FakeCSSStyleSheet {
  cssText = ''
  async replace(text: string): Promise<void> {
    this.cssText = text
  }
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme-variant')
  ;(document as unknown as { adoptedStyleSheets: unknown[] }).adoptedStyleSheets = []
  ;(globalThis as unknown as { CSSStyleSheet: unknown }).CSSStyleSheet = FakeCSSStyleSheet
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('[data-theme-variant="aqua"]{--bg-primary:#eef}'),
    }),
  )
  fetchInstalledThemesMock.mockResolvedValue([AQUA])
  vi.resetModules()
})

describe('useThemeVariant runtime themes', () => {
  it('merges installed theme ids into availableVariants after loadInstalledThemes', async () => {
    const { useThemeVariant } = await import('../useThemeVariant')
    const { availableVariants, loadInstalledThemes } = useThemeVariant()
    await loadInstalledThemes()
    expect(availableVariants.value).toContain('aqua')
  })

  it('exposes the installed theme descriptors', async () => {
    const { useThemeVariant } = await import('../useThemeVariant')
    const { installedThemes, loadInstalledThemes } = useThemeVariant()
    await loadInstalledThemes()
    expect(installedThemes.value.map((t) => t.id)).toEqual(['aqua'])
  })

  it('adopts a constructed stylesheet when applying an installed variant', async () => {
    const { useThemeVariant } = await import('../useThemeVariant')
    const { setThemeVariant, loadInstalledThemes } = useThemeVariant()
    await loadInstalledThemes()
    await setThemeVariant('aqua')
    expect(document.documentElement.getAttribute('data-theme-variant')).toBe('aqua')
    expect((document as unknown as { adoptedStyleSheets: unknown[] }).adoptedStyleSheets.length).toBe(1)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/themes/aqua/theme.css'),
      expect.objectContaining({ credentials: 'include' }),
    )
  })
})
