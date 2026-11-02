// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useTheme.test.ts - Unit Tests for Theme Composable
 * Issue #8988: User-Selectable Theme System
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

describe('useTheme', () => {
  let useTheme: typeof import('./useTheme').useTheme

  beforeEach(async () => {
    // Mock matchMedia before each test
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: query === '(prefers-color-scheme: dark)',
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })

    // Reset localStorage before each test
    localStorage.clear()
    // Reset document attributes
    document.documentElement.removeAttribute('data-high-contrast')
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.removeAttribute('data-accent')
    document.documentElement.style.colorScheme = ''
    // Reset module to get fresh singleton state
    vi.resetModules()
    // Import fresh module
    const module = await import('./useTheme')
    useTheme = module.useTheme
  })

  describe('theme management', () => {
    it('should initialize with the default light theme (the Refined default, #18223)', () => {
      const { theme, effectiveTheme, isDark } = useTheme()
      expect(theme.value).toBe('light')
      expect(effectiveTheme.value).toBe('light')
      expect(isDark.value).toBe(false)
    })

    it('should apply theme to document', () => {
      const { setTheme } = useTheme()
      setTheme('light')
      expect(document.documentElement.getAttribute('data-theme')).toBe('light')
      expect(document.documentElement.style.colorScheme).toBe('light')
    })

    it.each(['contrast', 'mono'] as const)('should apply the %s theme to document', (name) => {
      const { setTheme, effectiveTheme, isDark, isLight } = useTheme()
      setTheme(name)
      expect(document.documentElement.getAttribute('data-theme')).toBe(name)
      // Both are light-based: native controls render light.
      expect(document.documentElement.style.colorScheme).toBe('light')
      expect(effectiveTheme.value).toBe(name)
      expect(isDark.value).toBe(false)
      expect(isLight.value).toBe(false)
    })

    it.each(['contrast', 'mono'] as const)('should restore the saved %s theme on init', async (name) => {
      localStorage.setItem('autobot-theme', name)
      vi.resetModules()
      const module = await import('./useTheme')
      module.initializeTheme()
      expect(document.documentElement.getAttribute('data-theme')).toBe(name)
    })

    it('should ignore an unknown saved theme', async () => {
      localStorage.setItem('autobot-theme', 'sepia')
      vi.resetModules()
      const module = await import('./useTheme')
      expect(module.useTheme().theme.value).toBe('light')
    })

    it('should persist theme to localStorage', () => {
      const { setTheme } = useTheme()
      setTheme('light')
      expect(localStorage.getItem('autobot-theme')).toBe('light')
    })

    it('should load theme from localStorage', async () => {
      localStorage.setItem('autobot-theme', 'light')
      vi.resetModules()
      const module = await import('./useTheme')
      const { theme } = module.useTheme()
      expect(theme.value).toBe('light')
    })

    it('should toggle between dark and light', () => {
      const { theme, toggleTheme } = useTheme()
      expect(theme.value).toBe('light')
      toggleTheme()
      expect(theme.value).toBe('dark')
      toggleTheme()
      expect(theme.value).toBe('light')
    })

    it('should handle system theme preference', () => {
      const { setTheme, effectiveTheme, isDark } = useTheme()
      setTheme('system')
      // matchMedia is mocked to return true for dark mode
      expect(effectiveTheme.value).toBe('dark')
      expect(isDark.value).toBe(true)
    })
  })

  describe('accent color management', () => {
    it('should initialize with the theme accent, which sets no data-accent', () => {
      const { accentColor } = useTheme()
      expect(accentColor.value).toBe('theme')
      expect(document.documentElement.hasAttribute('data-accent')).toBe(false)
    })

    it('should clear data-accent when the theme accent is chosen again', () => {
      const { setAccentColor } = useTheme()
      setAccentColor('green')
      expect(document.documentElement.getAttribute('data-accent')).toBe('green')
      setAccentColor('theme')
      expect(document.documentElement.hasAttribute('data-accent')).toBe(false)
      expect(localStorage.getItem('autobot-accent-color')).toBe('theme')
    })

    it('should apply accent color to document', () => {
      const { setAccentColor } = useTheme()
      setAccentColor('green')
      expect(document.documentElement.getAttribute('data-accent')).toBe('green')
    })

    it('should persist accent color to localStorage', () => {
      const { setAccentColor } = useTheme()
      setAccentColor('purple')
      expect(localStorage.getItem('autobot-accent-color')).toBe('purple')
    })

    it('should load accent color from localStorage', async () => {
      localStorage.setItem('autobot-accent-color', 'orange')
      vi.resetModules()
      const module = await import('./useTheme')
      const { accentColor } = module.useTheme()
      expect(accentColor.value).toBe('orange')
    })

    it('should validate accent color values', async () => {
      localStorage.setItem('autobot-accent-color', 'invalid-color')
      vi.resetModules()
      const module = await import('./useTheme')
      const { accentColor } = module.useTheme()
      // Should fallback to default
      expect(accentColor.value).toBe('theme')
    })
  })

  describe('available options', () => {
    it('should provide available theme options', () => {
      const { availableThemes } = useTheme()
      expect(availableThemes).toEqual(['light', 'dark', 'contrast', 'mono', 'system'])
    })

    it('should provide available accent options', () => {
      const { availableAccents } = useTheme()
      expect(availableAccents).toEqual([
        'theme',
        'blue',
        'green',
        'purple',
        'orange',
        'pink',
        'teal',
        'indigo',
        'red',
      ])
    })

    it('should provide theme labels', () => {
      const { themeLabels } = useTheme()
      expect(themeLabels.dark).toBe('Dark')
      expect(themeLabels.light).toBe('Light')
      expect(themeLabels.system).toBe('System')
      expect(themeLabels.contrast).toBe('High contrast')
      expect(themeLabels.mono).toBe('Monochrome')
    })

    it('should provide accent labels', () => {
      const { accentLabels } = useTheme()
      expect(accentLabels.blue).toBe('Blue')
      expect(accentLabels.green).toBe('Green')
      expect(accentLabels.purple).toBe('Purple')
    })

    it('gives every accent a description key that en.json defines (#18255)', async () => {
      const { accentDescriptionKeys, availableAccents } = useTheme()
      type Tree = { [key: string]: Tree | string }
      const en = (await import('@/i18n/locales/en.json')).default as unknown as Tree
      const resolve = (key: string) =>
        key.split('.').reduce<Tree | string | undefined>((node, part) => (typeof node === 'object' ? node[part] : undefined), en)
      for (const accent of availableAccents) {
        expect(typeof resolve(accentDescriptionKeys[accent])).toBe('string')
      }
    })
  })

  describe('preset state (#18252)', () => {
    it('selects no preset on a fresh install, which renders light', () => {
      const { initTheme, preset, theme } = useTheme()
      initTheme()
      expect(theme.value).toBe('light')
      expect(preset.value).toBeNull()
    })

    it.each([
      ['system', 'theme', 'auto'],
      ['dark', 'theme', null],
      ['system', 'blue', null],
    ] as const)('reads a stored "auto" with theme %s and accent %s as %s', (storedTheme, accent, expected) => {
      localStorage.setItem('autobot-theme-preset', 'auto')
      localStorage.setItem('autobot-theme', storedTheme)
      localStorage.setItem('autobot-accent-color', accent)
      const { initTheme, preset } = useTheme()
      initTheme()
      expect(preset.value).toBe(expected)
    })

    it('keeps a stored named preset', () => {
      localStorage.setItem('autobot-theme-preset', 'midnight')
      const { initTheme, preset } = useTheme()
      initTheme()
      expect(preset.value).toBe('midnight')
    })

    it('a manual theme change after a high-contrast preset leaves no preset and no high contrast', () => {
      const { setPreset, setTheme, preset } = useTheme()
      setPreset('high-contrast-dark')
      expect(document.documentElement.getAttribute('data-high-contrast')).toBe('true')
      setTheme('light')
      expect(preset.value).toBeNull()
      expect(localStorage.getItem('autobot-theme-preset')).toBe('auto')
      expect(document.documentElement.hasAttribute('data-high-contrast')).toBe(false)
    })

    it('a manual accent change after a high-contrast preset leaves no preset and no high contrast', () => {
      const { setPreset, setAccentColor, preset } = useTheme()
      setPreset('high-contrast-light')
      setAccentColor('green')
      expect(preset.value).toBeNull()
      expect(localStorage.getItem('autobot-theme-preset')).toBe('auto')
      expect(document.documentElement.hasAttribute('data-high-contrast')).toBe(false)
    })

    it('initializeTheme applies a stored named preset before mount', async () => {
      localStorage.setItem('autobot-theme-preset', 'high-contrast-dark')
      const module = await import('./useTheme')
      module.initializeTheme()
      const { preset, theme } = module.useTheme()
      expect(preset.value).toBe('high-contrast-dark')
      expect(theme.value).toBe('dark')
      expect(document.documentElement.getAttribute('data-high-contrast')).toBe('true')
    })

    it('choosing system theme with the theme accent is the Auto preset', () => {
      const { setTheme, preset } = useTheme()
      setTheme('system')
      expect(preset.value).toBe('auto')
    })
  })

  describe('computed properties', () => {
    it('should compute isDark correctly', () => {
      const { setTheme, isDark } = useTheme()
      setTheme('dark')
      expect(isDark.value).toBe(true)
      setTheme('light')
      expect(isDark.value).toBe(false)
    })

    it('should compute isLight correctly', () => {
      const { setTheme, isLight } = useTheme()
      setTheme('light')
      expect(isLight.value).toBe(true)
      setTheme('dark')
      expect(isLight.value).toBe(false)
    })

    it('should compute effectiveTheme for system mode', () => {
      const { setTheme, effectiveTheme } = useTheme()
      setTheme('system')
      // matchMedia is mocked to return dark
      expect(effectiveTheme.value).toBe('dark')
    })
  })

  describe('initialization', () => {
    it('should not reinitialize if already initialized', () => {
      const { initTheme } = useTheme()
      const spy = vi.spyOn(document.documentElement, 'setAttribute')
      initTheme()
      const callCount = spy.mock.calls.length
      initTheme()
      // Should not call setAttribute again
      expect(spy.mock.calls.length).toBe(callCount)
    })

    it('should handle missing localStorage gracefully', async () => {
      const originalGetItem = localStorage.getItem
      localStorage.getItem = vi.fn(() => {
        throw new Error('localStorage not available')
      }) as typeof localStorage.getItem
      vi.resetModules()
      const module = await import('./useTheme')
      const { theme, accentColor } = module.useTheme()
      expect(theme.value).toBe('light')
      expect(accentColor.value).toBe('theme')
      localStorage.getItem = originalGetItem
    })
  })
})
