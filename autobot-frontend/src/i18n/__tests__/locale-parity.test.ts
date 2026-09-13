// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Locale Parity Tests
 *
 * Asserts that no non-English locale file carries a leaf key `en.json` does
 * not define. A locale may lag `en.json`; it may never drift ahead of it.
 *
 * `en.json` is the source of truth: every translation key the application
 * uses MUST be defined in en.json first.
 *
 * Issue #6498: Locale files had drifted ahead of en.json — fa/he/ur each
 * carried 12 stale `nav.*` keys; ar/de/es/fr/lv/pl/pt each carried 1 stale
 * `knowledge.search` key. A stale key is dead weight nothing can render, and
 * that is what this test still prevents.
 *
 * Issue #16063: the mirror assertion — no MISSING keys — used to live here
 * too, and it made every UI change a ten-locale translation change. It was
 * stricter than the application: `i18n/index.ts` sets `fallbackLocale: 'en'`,
 * so a key absent from `de.json` already renders the English string. English
 * ships first; translation follows on its own cadence.
 *
 * Lagging is therefore allowed but NOT unmeasured. A key missing from a
 * locale counts as untranslated in `repo_tests/i18n_untranslated_ratchet_test.py`,
 * which owns the per-locale debt figure and fails when it grows. Do not
 * re-derive that count here — two definitions of the same debt would
 * eventually disagree about what "translated" means.
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
    const extra = [...localeKeys].filter((k) => !enKeys.has(k)).sort()

    it(`has no extra keys (keys absent from en.json but present in ${code}.json)`, () => {
      expect(
        extra,
        `${code}.json contains ${extra.length} stale key(s) not defined in en.json:\n  ${extra.join('\n  ')}`,
      ).toEqual([])
    })
  })
})
