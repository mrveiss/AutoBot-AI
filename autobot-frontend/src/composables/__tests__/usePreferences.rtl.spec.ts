// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * RTL Startup Tests for usePreferences
 *
 * Verifies that calling usePreferences() on startup correctly propagates
 * the persisted language preference to the document dir and lang attributes
 * via setLocale().
 *
 * Issue #1510: Add automated RTL layout tests
 *
 * Strategy
 * --------
 * usePreferences has a module-level _initialized guard so initialization
 * only runs once per module lifecycle.  Each test uses vi.resetModules() and
 * dynamic import() to obtain a fresh module instance, ensuring the guard is
 * reset between tests.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ── Shared mock state ─────────────────────────────────────────────────────────

// We store what locale setLocale() was last called with so we can assert
// the DOM outcome without needing the real vue-i18n runtime.
let lastSetLocaleCall: string | null = null

// ── Module-level mocks ────────────────────────────────────────────────────────

// Mock the ApiClient to prevent real HTTP calls from syncLanguageToBackend
vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: null }),
    put: vi.fn().mockResolvedValue({}),
  },
}))

// Mock debugUtils to silence logger output during tests
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

// Mock @/i18n so we can intercept setLocale and apply the same RTL dir logic
// the real worktree implementation uses, without loading actual locale files.
vi.mock('@/i18n', () => {
  const RTL_LOCALES = new Set(['ar', 'he', 'fa', 'ur'])

  const setLocale = vi.fn().mockImplementation(async (locale: string) => {
    lastSetLocaleCall = locale
    const dir = RTL_LOCALES.has(locale) ? 'rtl' : 'ltr'
    document.documentElement.setAttribute('dir', dir)
    document.documentElement.setAttribute('lang', locale)
    localStorage.setItem('autobot-language', locale)
  })

  return {
    setLocale,
    loadLocaleMessages: vi.fn().mockResolvedValue(true),
    default: {
      global: {
        locale: { value: 'en' },
        availableLocales: ['en'],
        setLocaleMessage: vi.fn(),
      },
    },
  }
})

// ── Helpers ────────────────────────────────────────────────────────────────────

/**
 * Reset the module registry, seed localStorage, then dynamically import a
 * fresh copy of usePreferences.  Calling the returned composable triggers
 * the initialization path (loadPreferences + setLocale).
 */
async function freshUsePreferences(
  storedPrefs: Record<string, string> | null,
  languageKey: string | null,
): Promise<void> {
  // Seed storage BEFORE importing so loadPreferences() sees the values
  localStorage.clear()
  if (storedPrefs !== null) {
    localStorage.setItem('autobot-preferences', JSON.stringify(storedPrefs))
  }
  if (languageKey !== null) {
    localStorage.setItem('autobot-language', languageKey)
  }

  // Fresh module so _initialized = false
  vi.resetModules()
  const { usePreferences } = await import('@/composables/usePreferences')

  // Calling the composable triggers the init guard
  usePreferences()
}

// ── Test suite ────────────────────────────────────────────────────────────────

describe('usePreferences startup RTL behavior', () => {
  beforeEach(() => {
    lastSetLocaleCall = null
    document.documentElement.removeAttribute('dir')
    document.documentElement.removeAttribute('lang')
    localStorage.clear()
  })

  afterEach(() => {
    vi.resetModules()
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
    // No 'autobot-preferences' blob — only the raw language key
    await freshUsePreferences(null, 'ar')
    // usePreferences falls back to localStorage.getItem('autobot-language')
    // which yields 'ar', and should trigger dir=rtl
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  it('defaults to ltr when no stored preferences exist', async () => {
    // No preferences at all — DEFAULT_PREFERENCES.language = 'en'
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
    // lastSetLocaleCall is updated by our mock implementation
    expect(lastSetLocaleCall).toBe('ar')
  })
})
