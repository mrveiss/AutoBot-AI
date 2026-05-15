// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * RTL Layout Tests for setLocale()
 *
 * Verifies that setting a locale via setLocale() correctly updates:
 *   - document.documentElement[dir]  (ltr or rtl)
 *   - document.documentElement[lang] (locale code)
 *   - localStorage 'autobot-language' key
 *
 * Issue #1510: Add automated RTL layout tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock only loadLocaleMessages so tests exercise the real setLocale(). (#1598)
// The real setLocale() calls loadLocaleMessages() via an internal reference that
// vitest cannot intercept (same-module binding), so loadLocaleMessages() runs for
// real — loading locale JSON from disk and calling i18n.global.setLocaleMessage().
// The mock below only affects code that imports loadLocaleMessages directly.
vi.mock('@/i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/i18n')>()
  return {
    ...actual,
    // Only mock the export; the real setLocale is preserved. (#1598)
    loadLocaleMessages: vi.fn().mockResolvedValue(true),
  }
})

import { setLocale } from '@/i18n'

describe('setLocale() RTL dir attribute', () => {
  beforeEach(() => {
    // Reset dir/lang before every test so tests are fully independent
    document.documentElement.removeAttribute('dir')
    document.documentElement.removeAttribute('lang')
    localStorage.clear()
  })

  // ── RTL locales ────────────────────────────────────────────────────────────

  it('sets dir=rtl for Arabic (ar)', async () => {
    await setLocale('ar')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  it('sets dir=rtl for Hebrew (he)', async () => {
    await setLocale('he')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  it('sets dir=rtl for Persian (fa)', async () => {
    await setLocale('fa')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  it('sets dir=rtl for Urdu (ur)', async () => {
    await setLocale('ur')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })

  // ── LTR locales ────────────────────────────────────────────────────────────

  it('sets dir=ltr for English (en)', async () => {
    await setLocale('en')
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  it('sets dir=ltr for German (de)', async () => {
    await setLocale('de')
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  it('sets dir=ltr for French (fr)', async () => {
    await setLocale('fr')
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  // ── Direction switching ────────────────────────────────────────────────────

  it('switches from rtl back to ltr when locale changes from ar to en', async () => {
    await setLocale('ar')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
    await setLocale('en')
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  it('switches from ltr to rtl when locale changes from en to ar', async () => {
    await setLocale('en')
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
    await setLocale('ar')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
  })
})

describe('setLocale() html[lang] attribute', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('dir')
    document.documentElement.removeAttribute('lang')
    localStorage.clear()
  })

  it('sets lang=ar when locale is ar', async () => {
    await setLocale('ar')
    expect(document.documentElement.getAttribute('lang')).toBe('ar')
  })

  it('sets lang=en when locale is en', async () => {
    await setLocale('en')
    expect(document.documentElement.getAttribute('lang')).toBe('en')
  })

  it('sets lang=he when locale is he', async () => {
    await setLocale('he')
    expect(document.documentElement.getAttribute('lang')).toBe('he')
  })

  it('sets lang=fa when locale is fa', async () => {
    await setLocale('fa')
    expect(document.documentElement.getAttribute('lang')).toBe('fa')
  })

  it('sets lang=ur when locale is ur', async () => {
    await setLocale('ur')
    expect(document.documentElement.getAttribute('lang')).toBe('ur')
  })
})

describe('setLocale() localStorage persistence', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('dir')
    document.documentElement.removeAttribute('lang')
    localStorage.clear()
  })

  it('persists the locale code to localStorage', async () => {
    await setLocale('ar')
    expect(localStorage.getItem('autobot-language')).toBe('ar')
  })

  it('overwrites previous locale in localStorage', async () => {
    await setLocale('en')
    await setLocale('ar')
    expect(localStorage.getItem('autobot-language')).toBe('ar')
  })
})
