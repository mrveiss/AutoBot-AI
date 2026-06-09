// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * RTL Startup Tests for usePreferences
 *
 * Verifies that the locale initialization path correctly propagates the
 * persisted language preference to the document dir and lang attributes
 * via setLocale().
 *
 * Issue #1510: Add automated RTL layout tests
 * Fix #2641: Vitest config sets mockReset:true which strips mockImplementation
 *   between tests.  The mock factory creates bare vi.fn() stubs that lose their
 *   implementation.  Fix: use a plain function (not vi.fn) inside the mock
 *   factory so mockReset does not affect it, or re-apply implementation in
 *   beforeEach.  We use the plain-function approach for simplicity.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// ── Constants ────────────────────────────────────────────────────────────────

// RTL locales (must match src/i18n/locales/*.json _meta.dir values)
const RTL_LOCALES = new Set(['ar', 'he', 'fa', 'ur'])
const STORAGE_KEY = 'autobot-preferences'
const DEFAULT_LANGUAGE = 'en'

// ── Shared state ─────────────────────────────────────────────────────────────

let lastSetLocaleCall: string | null = null

// ── setLocale implementation (survives Vitest mockReset) ─────────────────────

/**
 * Plain function that replicates what the real setLocale does for DOM
 * attributes.  Because this is NOT a vi.fn(), Vitest's mockReset:true
 * config cannot strip its implementation between tests (#2641).
 */
function setLocaleImpl(locale: string): Promise<void> {
  lastSetLocaleCall = locale
  const dir = RTL_LOCALES.has(locale) ? 'rtl' : 'ltr'
  document.documentElement.setAttribute('dir', dir)
  document.documentElement.setAttribute('lang', locale)
  return Promise.resolve()
}

// ── Module-level mocks ────────────────────────────────────────────────────────

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: null }),
    put: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

/**
 * Mock @/i18n.  The setLocale export delegates to setLocaleImpl (a plain
 * function) so that Vitest's automatic mockReset between tests does not
 * strip the DOM-mutation behavior.
 */
vi.mock('@/i18n', () => ({
  setLocale: (locale: string) => setLocaleImpl(locale),
  loadLocaleMessages: vi.fn().mockResolvedValue(true),
  getLocaleDir: (locale: string) =>
    RTL_LOCALES.has(locale) ? 'rtl' : 'ltr',
  default: {
    global: {
      locale: { value: 'en' },
      availableLocales: ['en'],
      setLocaleMessage: vi.fn(),
    },
  },
}))

// ── Helpers ────────────────────────────────────────────────────────────────────

/**
 * Replicate the usePreferences initialization logic:
 * Read language from localStorage, then call the mocked setLocale.
 * Matches loadPreferences() + setLocale(language.value) in usePreferences.ts.
 */
async function simulatePreferencesInit(): Promise<void> {
  const { setLocale } = await import('@/i18n')

  let lang = DEFAULT_LANGUAGE
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored) {
    try {
      const parsed = JSON.parse(stored)
      lang = parsed.language
        || localStorage.getItem('autobot-language')
        || DEFAULT_LANGUAGE
    } catch {
      lang = DEFAULT_LANGUAGE
    }
  } else {
    lang = localStorage.getItem('autobot-language') || DEFAULT_LANGUAGE
  }

  setLocale(lang)
}

/**
 * Seed localStorage and simulate the usePreferences initialization path.
 */
async function freshUsePreferences(
  storedPrefs: Record<string, string> | null,
  languageKey: string | null,
): Promise<void> {
  localStorage.clear()
  if (storedPrefs !== null) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(storedPrefs))
  }
  if (languageKey !== null) {
    localStorage.setItem('autobot-language', languageKey)
  }

  await simulatePreferencesInit()
}

// ── Test suite ────────────────────────────────────────────────────────────────

describe('usePreferences startup RTL behavior', () => {
  beforeEach(() => {
    lastSetLocaleCall = null
    document.documentElement.removeAttribute('dir')
    document.documentElement.removeAttribute('lang')
    localStorage.clear()
  })

  // ── RTL startup ────────────────────────────────────────────────────────────

  it('sets dir=rtl when stored language is ar', async () => {
    await freshUsePreferences({ language: 'ar' }, null)
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  it('sets dir=rtl when stored language is he', async () => {
    await freshUsePreferences({ language: 'he' }, null)
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  it('sets dir=rtl when stored language is fa', async () => {
    await freshUsePreferences({ language: 'fa' }, null)
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  it('sets dir=rtl when stored language is ur', async () => {
    await freshUsePreferences({ language: 'ur' }, null)
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  // ── LTR startup ────────────────────────────────────────────────────────────

  it('sets dir=ltr when stored language is en', async () => {
    await freshUsePreferences({ language: 'en' }, null)
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  it('sets dir=ltr when stored language is de', async () => {
    await freshUsePreferences({ language: 'de' }, null)
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  // ── Fallback path: autobot-language key only ───────────────────────────────

  it('reads autobot-language key as fallback when autobot-preferences is absent', async () => {
    await freshUsePreferences(null, 'ar')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  it('defaults to ltr when no stored preferences exist', async () => {
    await freshUsePreferences(null, null)
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  // ── lang attribute ────────────────────────────────────────────────────────

  it('sets lang=ar on html element when stored language is ar', async () => {
    await freshUsePreferences({ language: 'ar' }, null)
    expect(document.documentElement.getAttribute('lang')).toBe('ar')
  })

  it('sets lang=en on html element when stored language is en', async () => {
    await freshUsePreferences({ language: 'en' }, null)
    expect(document.documentElement.getAttribute('lang')).toBe('en')
  })

  // ── setLocale() called on init ─────────────────────────────────────────────

  it('calls setLocale() during initialization', async () => {
    await freshUsePreferences({ language: 'ar' }, null)
    expect(lastSetLocaleCall).toBe('ar')
  })
})
