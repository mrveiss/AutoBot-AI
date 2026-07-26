// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Regression test for #12342: locale message bundles (~285KB combined) must be
 * split so only the active locale (+ the 'en' fallback) is fetched, on demand.
 * The monolithic `import en from './locales/en.json'` used to pull the whole
 * English bundle into the initial chunk on every page (incl. /chat).
 *
 * Guards both the source-level split (no static locale JSON import) and the
 * runtime lazy-load contract (loadLocaleMessages / initI18n).
 */

import { describe, it, expect } from 'vitest'
import i18n, { loadLocaleMessages, initI18n, SUPPORTED_LOCALES } from '@/i18n'
// Vite `?raw` import returns the i18n setup source as a string.
import i18nSource from '@/i18n/index.ts?raw'

describe('i18n locale bundle code-splitting (#12342)', () => {
  it('does NOT statically import any locale JSON into the i18n setup', () => {
    // A static `import en from './locales/en.json'` (or any locale) would put
    // that ~366KB bundle into the eager initial chunk.
    expect(i18nSource).not.toMatch(/^\s*import\s+\w+\s+from\s+['"`]\.\/locales\/\w+\.json['"`]/m)
  })

  it('loads a locale on demand via loadLocaleMessages()', async () => {
    // Pick a non-English supported locale that isn't the active one.
    const target = SUPPORTED_LOCALES.find(l => l !== 'en' && l !== i18n.global.locale.value)
    expect(target).toBeDefined()
    expect(i18n.global.availableLocales).not.toContain(target)

    const ok = await loadLocaleMessages(target as string)
    expect(ok).toBe(true)
    expect(i18n.global.availableLocales).toContain(target)
    // Real messages were loaded, not an empty object.
    expect(Object.keys(i18n.global.getLocaleMessage(target as string)).length).toBeGreaterThan(0)
  })

  it('initI18n() loads the active locale and the en fallback', async () => {
    await initI18n()
    expect(i18n.global.availableLocales).toContain('en')
    expect(i18n.global.availableLocales).toContain(i18n.global.locale.value)
  })
})
