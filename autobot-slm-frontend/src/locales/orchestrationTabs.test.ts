// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #17487: the tab id, route and key are all "infrastructure", so the label must name the
 * infrastructure tab, not "Overview" (the key name is the only hint a translator gets).
 */

import { describe, it, expect } from 'vitest'

const bundles = import.meta.glob('./*.json', { eager: true, import: 'default' }) as Record<
  string,
  { orchestrationView: Record<string, string> }
>

/** What each locale held before the fix: its own translation of "Overview" (#17487). */
const OLD_OVERVIEW: Record<string, string> = {
  './ar.json': 'نظرة عامة',
  './de.json': 'Übersicht',
  './en.json': 'Overview',
  './es.json': 'Resumen',
  './fa.json': 'نمای کلی',
  './fr.json': 'Aperçu',
  './he.json': 'סקירה',
  './lv.json': 'Pārskats',
  './pl.json': 'Przegląd',
  './pt.json': 'Visão geral',
  './ur.json': 'جائزہ',
}

describe('orchestrationView.tabInfrastructure (#17487)', () => {
  it('reads "Infrastructure" in English', () => {
    expect(bundles['./en.json'].orchestrationView.tabInfrastructure).toBe('Infrastructure')
  })

  it('every locale bundle has a recorded old value, so none escapes the check', () => {
    expect(Object.keys(bundles).sort()).toEqual(Object.keys(OLD_OVERVIEW).sort())
  })

  it.each(Object.keys(OLD_OVERVIEW))('%s no longer carries its own "Overview" wording', (file) => {
    const v = bundles[file].orchestrationView.tabInfrastructure
    expect(v).toBeTruthy()
    expect(v).not.toBe(OLD_OVERVIEW[file])
  })
})
