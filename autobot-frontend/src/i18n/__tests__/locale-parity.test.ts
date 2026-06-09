// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Locale Parity Tests
 *
 * Asserts that every non-English locale file has exactly the same set of
 * leaf translation keys as `en.json` — no missing keys, no extra (stale)
 * keys.
 *
 * `en.json` is the source of truth: every translation key the application
 * uses MUST be defined in en.json first. Other locales are translations
 * of those keys and should drift neither ahead (stale keys removed from
 * en.json but lingering in translations) nor behind (untranslated keys).
 *
 * Issue #6498: Locale files have drifted from en.json — fa/he/ur each
 * carry 12 stale `nav.*` keys; ar/de/es/fr/lv/pl/pt each carry 1 stale
 * `knowledge.search` key. This test prevents future drift by failing CI
 * whenever a locale's leaf-key set differs from en.json's.
 */

import { describe, it, expect } from 'vitest'

import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'
import de from '@/i18n/locales/de.json'
import es from '@/i18n/locales/es.json'
import fa from '@/i18n/locales/fa.json'
import fr from '@/i18n/locales/fr.json'
import he from '@/i18n/locales/he.json'
import lv from '@/i18n/locales/lv.json'
import pl from '@/i18n/locales/pl.json'
import pt from '@/i18n/locales/pt.json'
import ur from '@/i18n/locales/ur.json'

type LocaleTree = Record<string, unknown>

/**
 * Flatten a nested locale dictionary into a Set of dot-delimited leaf
 * paths. Only paths that resolve to a non-object value (string, number,
 * boolean, null) are included; intermediate object nodes are skipped.
 */
function flattenLeafKeys(tree: LocaleTree, prefix = ''): Set<string> {
  const out = new Set<string>()
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      for (const leaf of flattenLeafKeys(value as LocaleTree, path)) {
        out.add(leaf)
      }
    } else {
      out.add(path)
    }
  }
  return out
}

const enKeys = flattenLeafKeys(en as LocaleTree)

const NON_EN_LOCALES: ReadonlyArray<readonly [string, LocaleTree]> = [
  ['ar', ar as LocaleTree],
  ['de', de as LocaleTree],
  ['es', es as LocaleTree],
  ['fa', fa as LocaleTree],
  ['fr', fr as LocaleTree],
  ['he', he as LocaleTree],
  ['lv', lv as LocaleTree],
  ['pl', pl as LocaleTree],
  ['pt', pt as LocaleTree],
  ['ur', ur as LocaleTree],
]

describe('locale parity with en.json', () => {
  it('en.json itself has at least one leaf key (sanity check)', () => {
    expect(enKeys.size).toBeGreaterThan(0)
  })

  describe.each(NON_EN_LOCALES)('%s.json', (code, tree) => {
    const localeKeys = flattenLeafKeys(tree)
    const missing = [...enKeys].filter((k) => !localeKeys.has(k)).sort()
    const extra = [...localeKeys].filter((k) => !enKeys.has(k)).sort()

    it(`has no missing keys (keys present in en.json but absent in ${code}.json)`, () => {
      expect(
        missing,
        `${code}.json is missing ${missing.length} key(s) defined in en.json:\n  ${missing.join('\n  ')}`,
      ).toEqual([])
    })

    it(`has no extra keys (keys absent from en.json but present in ${code}.json)`, () => {
      expect(
        extra,
        `${code}.json contains ${extra.length} stale key(s) not defined in en.json:\n  ${extra.join('\n  ')}`,
      ).toEqual([])
    })
  })
})
