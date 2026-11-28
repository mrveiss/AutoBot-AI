// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The shared theme names, storage key and document application (#18239).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  THEMES, EFFECTIVE_THEMES, THEME_STORAGE_KEY, colorSchemeFor, resolveTheme,
  applyThemeToDocument, readStoredTheme, writeStoredTheme,
} from '../themeScheme'

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.colorScheme = ''
  vi.unstubAllGlobals()
})

describe('themeScheme', () => {
  it('offers the four Refined themes plus contrast-dark and system', () => {
    expect([...EFFECTIVE_THEMES]).toEqual(['light', 'dark', 'contrast', 'contrast-dark', 'mono'])
    expect(THEMES).toContain('system')
  })

  it.each([
    ['light', 'light'], ['dark', 'dark'], ['contrast', 'light'], ['contrast-dark', 'dark'], ['mono', 'light'],
  ] as const)('%s renders with color-scheme %s', (theme, scheme) => {
    expect(colorSchemeFor(theme)).toBe(scheme)
    applyThemeToDocument(theme)
    expect(document.documentElement.getAttribute('data-theme')).toBe(theme)
    expect(document.documentElement.style.colorScheme).toBe(scheme)
  })

  it('system follows the OS preference', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }))
    expect(resolveTheme('system')).toBe('dark')
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
    expect(resolveTheme('system')).toBe('light')
  })

  it('stores under autobot-theme and reads back only allowed values', () => {
    writeStoredTheme('mono')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('mono')
    expect(readStoredTheme()).toBe('mono')
    expect(readStoredTheme(['light', 'dark'])).toBeNull()
    localStorage.setItem(THEME_STORAGE_KEY, 'high-contrast')
    expect(readStoredTheme()).toBeNull()
  })
})
