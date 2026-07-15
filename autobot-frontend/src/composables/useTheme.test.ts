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
    it('should initialize with default dark theme', () => {
      const { theme, effectiveTheme, isDark } = useTheme()
      expect(theme.value).toBe('dark')
      expect(effectiveTheme.value).toBe('dark')
      expect(isDark.value).toBe(true)
    })

    it('should apply theme to document', () => {
      const { setTheme } = useTheme()
      setTheme('light')
      expect(document.documentElement.getAttribute('data-theme')).toBe('light')
      expect(document.documentElement.style.colorScheme).toBe('light')
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
      expect(theme.value).toBe('dark')
      toggleTheme()
      expect(theme.value).toBe('light')
      toggleTheme()
      expect(theme.value).toBe('dark')
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
    it('should initialize with default blue accent', () => {
      const { accentColor } = useTheme()
      expect(accentColor.value).toBe('blue')
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
      expect(accentColor.value).toBe('blue')
    })
  })

  describe('available options', () => {
    it('should provide available theme options', () => {
      const { availableThemes } = useTheme()
      expect(availableThemes).toEqual(['dark', 'light', 'system'])
    })

    it('should provide available accent options', () => {
      const { availableAccents } = useTheme()
      expect(availableAccents).toEqual([
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
    })

    it('should provide accent labels', () => {
      const { accentLabels } = useTheme()
      expect(accentLabels.blue).toBe('Blue')
      expect(accentLabels.green).toBe('Green')
      expect(accentLabels.purple).toBe('Purple')
    })

    it('should provide accent descriptions', () => {
      const { accentDescriptions } = useTheme()
      expect(accentDescriptions.blue).toContain('Electric Blue')
      expect(accentDescriptions.green).toContain('Emerald')
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
      expect(theme.value).toBe('dark')
      expect(accentColor.value).toBe('blue')
      localStorage.getItem = originalGetItem
    })
  })
})
