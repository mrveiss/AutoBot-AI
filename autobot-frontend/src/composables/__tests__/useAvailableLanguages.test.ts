// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAvailableLanguages } from '../useAvailableLanguages'

// Mock SUPPORTED_LOCALES so tests don't depend on disk files
vi.mock('@/i18n', () => ({
  SUPPORTED_LOCALES: ['ar', 'de', 'en', 'fr']
}))

describe('useAvailableLanguages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns one entry per supported locale', () => {
    const { languages } = useAvailableLanguages()
    expect(languages.value).toHaveLength(4)
    expect(languages.value.map(l => l.code)).toEqual(['ar', 'de', 'en', 'fr'])
  })

  it('each entry has a non-empty name string', () => {
    const { languages } = useAvailableLanguages()
    for (const lang of languages.value) {
      expect(typeof lang.name).toBe('string')
      expect(lang.name.length).toBeGreaterThan(0)
    }
  })

  it('falls back to locale code when Intl.DisplayNames returns undefined', () => {
    // Simulate a browser that returns undefined for an unknown code.
    // vi.spyOn on a constructor requires mockImplementation to use a class or
    // a function that works with `new` (returns an object from within the function).
    const spy = vi.spyOn(Intl, 'DisplayNames').mockImplementation(
      function (_locales: any, _options: any) {
        return { of: () => undefined, resolvedOptions: () => ({} as any) }
      } as unknown as typeof Intl.DisplayNames
    )

    const { languages } = useAvailableLanguages()
    expect(languages.value[0].name).toBe('ar')

    spy.mockRestore()
  })

  it('en locale produces an English name', () => {
    const { languages } = useAvailableLanguages()
    const en = languages.value.find(l => l.code === 'en')
    expect(en).toBeDefined()
    // Intl.DisplayNames(['en'], { type: 'language' }).of('en') → 'English'
    expect(en!.name).toBeTruthy()
  })
})
