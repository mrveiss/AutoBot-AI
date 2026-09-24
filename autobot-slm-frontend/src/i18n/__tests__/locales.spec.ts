// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The SLM console resolves, switches and lays out all 11 locales (#14781).
 *
 * The app shipped `locale: 'en'` hardcoded and one message bundle, so these are
 * the assertions that would have failed before: that every locale on disk is
 * reachable, that the resolved locale comes from the user rather than from a
 * constant, and that an RTL locale sets `dir` — strings in Arabic with a
 * left-to-right layout is the half-fix this guards against.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n, { SUPPORTED_LOCALES, detectBrowserLocale, getLocaleDir, resolveInitialLocale, setLocale } from '../index'

const EXPECTED = ['ar', 'de', 'en', 'es', 'fa', 'fr', 'he', 'lv', 'pl', 'pt', 'ur']
const RTL = ['ar', 'fa', 'he', 'ur']

describe('the locale set', () => {
  it('carries all 11 locales, derived from disk rather than a list', () => {
    expect(SUPPORTED_LOCALES).toEqual(EXPECTED)
  })

  it('has messages loaded for every one of them', () => {
    for (const locale of EXPECTED) {
      expect(Object.keys(i18n.global.messages[locale] ?? {}).length).toBeGreaterThan(0)
    }
  })
})

describe('direction', () => {
  it.each(RTL)('%s is right-to-left, read from the locale file', (locale) => {
    expect(getLocaleDir(locale)).toBe('rtl')
  })

  it.each(EXPECTED.filter((l) => !RTL.includes(l)))('%s is left-to-right', (locale) => {
    expect(getLocaleDir(locale)).toBe('ltr')
  })

  it('treats an unknown locale as left-to-right rather than throwing', () => {
    expect(getLocaleDir('zz')).toBe('ltr')
  })
})

describe('resolving the initial locale', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('prefers a stored preference', () => {
    localStorage.setItem('autobot-language', 'lv')

    expect(resolveInitialLocale()).toBe('lv')
  })

  it('ignores a stored preference for a locale that does not exist', () => {
    localStorage.setItem('autobot-language', 'zz')

    expect(EXPECTED).toContain(resolveInitialLocale())
  })

  it('falls back to browser detection, base tag included', () => {
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['de-AT', 'en'])

    expect(detectBrowserLocale()).toBe('de')
  })

  it('answers en when the browser asks for nothing we have', () => {
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['ja-JP'])

    expect(detectBrowserLocale()).toBe('en')
  })
})

describe('switching', () => {
  beforeEach(() => {
    localStorage.clear()
    setLocale('en')
  })

  it('changes the active locale and persists it', () => {
    setLocale('de')

    expect(String(i18n.global.locale)).toBe('de')
    expect(localStorage.getItem('autobot-language')).toBe('de')
  })

  it('sets html[lang] and html[dir] together', () => {
    setLocale('ar')

    expect(document.documentElement.getAttribute('lang')).toBe('ar')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  it('returns to ltr when leaving an RTL locale', () => {
    setLocale('ar')
    setLocale('fr')

    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  it('refuses a locale it does not have, rather than blanking the UI', () => {
    setLocale('de')
    setLocale('zz')

    expect(String(i18n.global.locale)).toBe('de')
  })
})

describe('translation actually resolves', () => {
  it('renders a lifted translation in its own language, not English', () => {
    setLocale('de')

    // `common.sidebar.languageLabel` is this PR's own key; pick a key the lift
    // rule translated instead, so this asserts the pipeline rather than a
    // string I typed. `addNodeModal.adding` is "Hinzufügen..." in de.
    expect(i18n.global.t('addNodeModal.adding')).not.toBe('Adding...')
  })

  it('falls back to English for an untranslated key rather than showing the key', () => {
    setLocale('he')

    const rendered = i18n.global.t('addNodeModal.addNewNode')
    expect(rendered).not.toBe('addNodeModal.addNewNode')
    expect(rendered.length).toBeGreaterThan(0)
  })
})
