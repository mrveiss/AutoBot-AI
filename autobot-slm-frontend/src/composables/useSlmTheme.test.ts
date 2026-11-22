// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #18239: the SLM switches between the four Refined themes, persists the choice in
 * localStorage under the key the user frontend uses, and carries a choice saved by the
 * legacy toggles over (the old high-contrast palette becomes `contrast`).
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useSlmTheme, SLM_THEMES, SLM_THEME_LABEL_KEYS } from './useSlmTheme'
import en from '@/locales/en.json'

const root = document.documentElement

beforeEach(() => {
  localStorage.clear()
  root.removeAttribute('data-theme')
  root.style.colorScheme = ''
})

describe('useSlmTheme (SLM)', () => {
  it('offers exactly the four Refined themes', () => {
    expect([...SLM_THEMES]).toEqual(['light', 'dark', 'contrast', 'mono'])
  })

  it.each(SLM_THEMES)('set(%s) applies data-theme and persists under autobot-theme', (name) => {
    const { set, theme } = useSlmTheme()
    set(name)
    expect(theme.value).toBe(name)
    expect(root.getAttribute('data-theme')).toBe(name)
    expect(localStorage.getItem('autobot-theme')).toBe(name)
  })

  it.each(SLM_THEMES)('init() restores a stored %s', (name) => {
    localStorage.setItem('autobot-theme', name)
    const { init, theme } = useSlmTheme()
    init()
    expect(theme.value).toBe(name)
    expect(root.getAttribute('data-theme')).toBe(name)
  })

  it('defaults to light when nothing is stored or the stored value is not an SLM theme', () => {
    const { init, theme } = useSlmTheme()
    init()
    expect(theme.value).toBe('light')
    localStorage.setItem('autobot-theme', 'contrast-dark')
    init()
    expect(theme.value).toBe('light')
  })

  it('migrates the legacy high-contrast flag to contrast and drops the old keys', () => {
    localStorage.setItem('autobot-high-contrast', 'true')
    localStorage.setItem('autobot-dark-mode', 'true')
    const { init, theme } = useSlmTheme()
    init()
    expect(theme.value).toBe('contrast')
    expect(root.getAttribute('data-theme')).toBe('contrast')
    expect(localStorage.getItem('autobot-theme')).toBe('contrast')
    expect(localStorage.getItem('autobot-high-contrast')).toBeNull()
    expect(localStorage.getItem('autobot-dark-mode')).toBeNull()
  })

  it('migrates the legacy dark-mode flag to dark', () => {
    localStorage.setItem('autobot-dark-mode', 'true')
    const { init, theme } = useSlmTheme()
    init()
    expect(theme.value).toBe('dark')
  })

  it('reads a stored legacy theme value high-contrast as contrast', () => {
    localStorage.setItem('autobot-theme', 'high-contrast')
    const { init, theme } = useSlmTheme()
    init()
    expect(theme.value).toBe('contrast')
    expect(localStorage.getItem('autobot-theme')).toBe('contrast')
  })

  it('never overwrites an already stored theme with a legacy flag', () => {
    localStorage.setItem('autobot-theme', 'mono')
    localStorage.setItem('autobot-high-contrast', 'true')
    const { init, theme } = useSlmTheme()
    init()
    expect(theme.value).toBe('mono')
    expect(localStorage.getItem('autobot-high-contrast')).toBeNull()
  })

  it('toggleContrast switches contrast on, then back to light', () => {
    const { set, toggleContrast, theme, isContrast } = useSlmTheme()
    set('dark')
    toggleContrast()
    expect(theme.value).toBe('contrast')
    expect(isContrast.value).toBe(true)
    toggleContrast()
    expect(theme.value).toBe('light')
  })

  it('every theme has a translated label key in en.json', () => {
    for (const name of SLM_THEMES) {
      const key = SLM_THEME_LABEL_KEYS[name].replace('settings.generalSettings.', '')
      expect((en as { settings: { generalSettings: Record<string, string> } }).settings.generalSettings[key]).toBeTruthy()
    }
  })
})
