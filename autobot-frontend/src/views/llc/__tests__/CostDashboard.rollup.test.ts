// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14599: nothing totalled what the canvas maps. These guard the property that
// makes such a total safe to read — coverage is reported beside it, so a
// partial figure can never be mistaken for a complete one.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import CostDashboard from '../CostDashboard.vue'

const PARTIAL = {
  key: 'r1', label: 'Head of Sales', per_month: '600.000000',
  costed: 1, not_costable: 1, total_steps: 2, is_complete: false, currencies: ['EUR'],
}
const COMPLETE = {
  key: 'r2', label: 'SRE', per_month: '120.000000',
  costed: 2, not_costable: 0, total_steps: 2, is_complete: true, currencies: ['EUR'],
}

function respond(rollup: unknown): void {
  get.mockImplementation((url: string) => {
    if (String(url).includes('/step-rollup')) {
      if (rollup === 'reject') return Promise.reject(new Error('HTTP 503: upstream'))
      return Promise.resolve(rollup)
    }
    if (String(url).includes('/cost-events')) return Promise.resolve([])
    if (String(url).includes('/budget')) return Promise.resolve([])
    return Promise.resolve([])
  })
}

async function mountDashboard() {
  const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
  const wrapper = mount(CostDashboard, {
    global: { plugins: [i18n], stubs: { BaseModal: true, BaseButton: true, Icon: true } },
  })
  await flushPromises()
  return wrapper
}

describe('step rollup on the cost dashboard (#14599)', () => {
  beforeEach(() => get.mockReset())

  it('states coverage beside a partial total, never the total alone', async () => {
    respond({ by_role: [PARTIAL], by_tool: [] })
    const wrapper = await mountDashboard()

    const coverage = wrapper.find('[data-testid="rollup-coverage-role-r1"]')
    expect(coverage.exists()).toBe(true)
    expect(coverage.text()).toBe('1 of 2 steps costed')
    // The figure is shown too — this is a partial answer, not a refusal.
    expect(wrapper.find('[data-testid="step-rollup"]').text()).toContain('600.000000')
  })

  it('distinguishes a complete bucket from a partial one', async () => {
    // The pair is the point: if the distinction were dropped, one of these two
    // assertions would still pass, so neither alone is evidence.
    respond({ by_role: [PARTIAL, COMPLETE], by_tool: [] })
    const wrapper = await mountDashboard()

    expect(wrapper.find('[data-testid="rollup-coverage-role-r2"]').text()).toBe('All steps costed')
    expect(wrapper.find('[data-testid="rollup-coverage-role-r1"]').text()).not.toBe('All steps costed')
  })

  it('says the totals could not be loaded, not that nothing is mapped', async () => {
    respond('reject')
    const wrapper = await mountDashboard()

    expect(wrapper.find('[data-testid="step-rollup-unavailable"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="step-rollup-empty"]').exists()).toBe(false)
  })

  it('says nothing is mapped when the server answers with nothing', async () => {
    respond({ by_role: [], by_tool: [] })
    const wrapper = await mountDashboard()

    expect(wrapper.find('[data-testid="step-rollup-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="step-rollup-unavailable"]').exists()).toBe(false)
  })

  // NOTE: there is deliberately no test here for the `Array.isArray` guard on
  // the rollup payload. Removing that guard does not change anything this
  // harness can observe — a malformed payload renders the same empty section
  // either way — so a test for it would pass with the guard deleted and would
  // be evidence of nothing. The guard stays because it is cheap and because
  // this exact failure took a view down twice (#13617, #14598); it is honest
  // to record that it is unproven rather than to assert coverage it lacks.

  it('explains why tool totals do not add up to role totals', async () => {
    respond({ by_role: [PARTIAL], by_tool: [{ ...PARTIAL, key: 'crm', label: 'crm' }] })
    const wrapper = await mountDashboard()

    expect(wrapper.find('[data-testid="step-rollup-tool-note"]').text()).toBe(en.llc.cost.stepRollupToolNote)
  })
})
