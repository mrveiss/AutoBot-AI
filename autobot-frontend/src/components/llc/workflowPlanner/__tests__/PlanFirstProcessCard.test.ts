// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19938 E2: the wizard-exit card on the company landing page, and the pure gate rules.

import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { gateRows } from '@/composables/llc/workflowPlanGate'

const push = vi.fn()
const replace = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/llc/companies/co-1', query: { welcome: 'plan' }, params: { companyId: 'co-1' } }),
  useRouter: () => ({ push, replace }),
}))

import PlanFirstProcessCard from '../PlanFirstProcessCard.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

describe('PlanFirstProcessCard', () => {
  it('opens the planner with the wizard_exit entry point', async () => {
    const w = mount(PlanFirstProcessCard, { global: { plugins: [i18n] } })
    await w.find('[data-testid="plan-first-process-now"]').trigger('click')
    expect(push).toHaveBeenCalledWith({
      path: '/llc/companies/co-1/org-chart',
      query: { view: 'planner', entry_point: 'wizard_exit' },
    })
  })

  it('drops only the welcome flag on Later', async () => {
    const w = mount(PlanFirstProcessCard, { global: { plugins: [i18n] } })
    await w.find('[data-testid="plan-first-process-later"]').trigger('click')
    expect(replace).toHaveBeenCalledWith({ path: '/llc/companies/co-1', query: { welcome: undefined } })
  })
})

describe('gateRows', () => {
  it('never shows an unevaluated gate as met', () => {
    const rows = gateRows('draft', { status: 'draft', next_status: 'measured', missing: [{ gate: 'G2', message: 'no metric' }] })
    const state = Object.fromEntries(rows.map((r) => [r.id, r.state]))
    expect(state).toMatchObject({ G1: 'met', G2: 'open', G3: 'pending', G7: 'pending' })
  })

  it('lists a gate id it does not know instead of dropping it', () => {
    const rows = gateRows('approved', { status: 'approved', next_status: 'converted', missing: [{ gate: 'converted', message: 'not committed' }] })
    expect(rows.find((r) => r.id === 'converted')).toMatchObject({ state: 'open', messages: ['not committed'] })
    expect(rows.find((r) => r.id === 'G7')?.state).toBe('met')
  })
})
