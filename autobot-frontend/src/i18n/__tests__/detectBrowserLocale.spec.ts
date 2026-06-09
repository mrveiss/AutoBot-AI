// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Unit tests for detectBrowserLocale()
 *
 * Verifies that detectBrowserLocale() correctly resolves the user's
 * preferred locale from navigator.languages / navigator.language against
 * the SUPPORTED_LOCALES list. Covers exact matches, base-language
 * fallback (e.g. 'es-MX' -> 'es'), priority ordering, case
 * insensitivity, and the 'en' default when no locale matches.
 *
 * Issue #1674: Add unit tests for detectBrowserLocale()
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { detectBrowserLocale } from '@/i18n'

/**
 * Helper: override navigator.languages with a given array.
 * Uses Object.defineProperty so the read-only property can be replaced.
 */
function setNavigatorLanguages(languages: string[]): void {
  Object.defineProperty(window.navigator, 'languages', {
    value: languages,
    configurable: true,
  })
}

/**
 * Helper: set navigator.language (single string) and clear
 * navigator.languages to simulate browsers that only expose the
 * singular property.
 */
function setNavigatorLanguage(language: string): void {
  Object.defineProperty(window.navigator, 'languages', {
    value: undefined,
    configurable: true,
  })
  Object.defineProperty(window.navigator, 'language', {
    value: language,
    configurable: true,
  })
}

describe('detectBrowserLocale()', () => {
  beforeEach(() => {
    // Reset navigator properties before every test
    Object.defineProperty(window.navigator, 'languages', {
      value: ['en'],
      configurable: true,
    })
    Object.defineProperty(window.navigator, 'language', {
      value: 'en',
      configurable: true,
    })
  })

  // -- Exact match ---------------------------------------------------------

  describe('exact match', () => {
    it('returns es when navigator.languages contains es', () => {
      setNavigatorLanguages(['es'])
      expect(detectBrowserLocale()).toBe('es')
    })

    it('returns en when navigator.languages contains en', () => {
      setNavigatorLanguages(['en'])
      expect(detectBrowserLocale()).toBe('en')
    })
  })

  // -- Base language fallback ----------------------------------------------

  describe('base language fallback', () => {
    it('returns es for es-MX (region stripped)', () => {
      setNavigatorLanguages(['es-MX'])
      expect(detectBrowserLocale()).toBe('es')
    })

    it('returns ar for ar-EG (Arabic region variant)', () => {
      setNavigatorLanguages(['ar-EG'])
      expect(detectBrowserLocale()).toBe('ar')
    })
  })

  // -- Priority ordering ---------------------------------------------------

  describe('priority ordering', () => {
    it('skips unsupported ja and returns de (first match wins)', () => {
      setNavigatorLanguages(['ja', 'de'])
      expect(detectBrowserLocale()).toBe('de')
    })

    it('returns fr when fr appears before de', () => {
      setNavigatorLanguages(['fr', 'de'])
      expect(detectBrowserLocale()).toBe('fr')
    })
  })

  // -- Unsupported locale --------------------------------------------------

  describe('unsupported locale fallback', () => {
    it('returns en when no locale matches', () => {
      setNavigatorLanguages(['ja'])
      expect(detectBrowserLocale()).toBe('en')
    })
  })

  // -- Case insensitivity --------------------------------------------------

  describe('case insensitivity', () => {
    it('returns es for uppercase ES', () => {
      setNavigatorLanguages(['ES'])
      expect(detectBrowserLocale()).toBe('es')
    })
  })

  // -- navigator.language fallback -----------------------------------------

  describe('navigator.language fallback', () => {
    it('falls back to navigator.language when languages is unavailable', () => {
      setNavigatorLanguage('fr')
      expect(detectBrowserLocale()).toBe('fr')
    })
  })
})
