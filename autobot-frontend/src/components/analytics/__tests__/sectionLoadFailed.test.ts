// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #17651: a section whose load FAILED must say so. Before, Problems, Code
 * Smells, Declarations and Hardcodes had no error branch, so a 4xx/5xx
 * rendered as "No problems detected" (a success-styled empty state).
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ProblemsReportSection from '../ProblemsReportSection.vue'
import CodeSmellsSection from '../CodeSmellsSection.vue'
import DeclarationsSection from '../DeclarationsSection.vue'
import HardcodesSection from '../HardcodesSection.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const EmptyState = {
  props: ['message'],
  template: '<div class="empty-state">{{ message }}</div>',
}
const mountIt = (comp: object, props: Record<string, unknown>) =>
  mount(comp as never, { props, global: { plugins: [i18n], stubs: { EmptyState } } })

const FAILED = 'could not be loaded'
const cases: Array<[string, object, Record<string, unknown>, string]> = [
  ['Problems', ProblemsReportSection, { problems: [] }, 'No problems detected'],
  ['Code smells', CodeSmellsSection, { smells: [], codeHealthScore: null }, 'No code smells detected'],
  ['Declarations', DeclarationsSection, { declarations: [] }, 'No declarations found'],
  ['Hardcodes', HardcodesSection, { hardcodes: [] }, 'No hardcoded values detected'],
]

describe('analytics sections report a failed load (#17651)', () => {
  it.each(cases)('%s: error shows the failure, not the empty message', (_n, comp, props, emptyMsg) => {
    const w = mountIt(comp, { ...props, error: 'Endpoint returned 500' })
    expect(w.text()).toContain(FAILED)
    expect(w.text()).toContain('returned 500')
    expect(w.text()).not.toContain(emptyMsg)
  })

  it.each(cases)('%s: no error and no rows is still the honest empty state', (_n, comp, props, emptyMsg) => {
    const w = mountIt(comp, props)
    expect(w.text()).toContain(emptyMsg)
    expect(w.text()).not.toContain(FAILED)
  })
})
