// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * DuplicatesSection shows "no duplicates" only for a scan that ran (#17983).
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import DuplicatesSection from '../DuplicatesSection.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const msg = en.analytics.duplicates
const render = (scanState?: 'done' | 'not_scanned' | 'failed') =>
  mount(DuplicatesSection, { props: { duplicates: [], scanState }, global: { plugins: [i18n] } }).text()

describe('DuplicatesSection scan states (#17983)', () => {
  it('a failed scan says so, and never "no duplicates"', () => {
    const text = render('failed')
    expect(text).toContain(msg.scanFailed)
    expect(text).not.toContain(msg.emptyMessage)
  })

  it('a never-run scan says it has not run', () => {
    const text = render('not_scanned')
    expect(text).toContain(msg.notScanned)
    expect(text).not.toContain(msg.emptyMessage)
  })

  it('a completed scan with nothing found shows "no duplicates"', () => {
    expect(render('done')).toContain(msg.emptyMessage)
  })
})
