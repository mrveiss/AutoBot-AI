// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19938: the gate rows render their translated names outside English, and the wizard's
// ?welcome=plan flag survives the company-root redirect to the backlog.

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import en from '@/i18n/locales/en.json'
import de from '@/i18n/locales/de.json'
import ar from '@/i18n/locales/ar.json'
import PlannerGateList from '../PlannerGateList.vue'
import { llcCompanyChildren } from '@/router/llcRoutes'

const GATE = {
  status: 'approved',
  next_status: 'converted',
  missing: [{ gate: 'converted', message: 'the conversion has not been committed' }],
} as never

function render(locale: 'de' | 'ar') {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, de, ar } })
  return mount(PlannerGateList, { props: { status: 'approved', gate: GATE }, global: { plugins: [i18n] } })
}

describe('PlannerGateList translated names', () => {
  it.each([
    ['de', de.llc.workflowPlanner.gate.name.converted, de.llc.workflowPlanner.gate.name.G1],
    ['ar', ar.llc.workflowPlanner.gate.name.converted, ar.llc.workflowPlanner.gate.name.G1],
  ] as const)('renders the converted and G1 rows in %s, not English', (locale, converted, g1) => {
    const w = render(locale)
    const text = w.find('[data-testid="gate-converted"]').text()
    expect(text).toContain(converted)
    expect(converted).not.toBe(en.llc.workflowPlanner.gate.name.converted)
    expect(w.find('[data-testid="gate-G1"]').text()).toContain(g1)
    expect(text).not.toContain(en.llc.workflowPlanner.gate.unknown)
  })
})

describe('company-root redirect', () => {
  it('keeps ?welcome=plan when / redirects to the backlog', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/llc/companies/:companyId', children: llcCompanyChildren }],
    })
    await router.push({ path: '/llc/companies/co-1', query: { welcome: 'plan' } })
    expect(router.currentRoute.value.name).toBe('llc-backlog')
    expect(router.currentRoute.value.query.welcome).toBe('plan')
  })
})
