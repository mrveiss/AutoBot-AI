// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14598 / #14607: recording how long a step takes and how often it runs, and
// the role hourly rate its cost derives from.
//
// The rule under test throughout: **missing is not zero**. A step nobody
// measured, or a role with no rate, is reported as not costable — never as
// costing nothing. A zero would understate every total it feeds and would be
// indistinguishable from a genuinely free step.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()
const del = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post, put, delete: del }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import RolesView from '../RolesView.vue'

const ROLE = { id: 'r1', name: 'Head of Sales', description: '', is_system: false }

/** A costed step, exactly as `GET .../workflows/{id}/cost` returns it. */
const COSTED = {
  workflow_id: 'wf-1',
  estimated_minutes: 30,
  runs_per_month: 10,
  per_run: '60.000000',
  per_month: '600.000000',
  per_year: '7200.000000',
  currency: 'EUR',
  missing: [],
}

/** The same step with nothing recorded — the state that must not read as free. */
const UNCOSTED = {
  workflow_id: 'wf-1',
  estimated_minutes: null,
  runs_per_month: null,
  per_run: null,
  per_month: null,
  per_year: null,
  currency: null,
  missing: ['no_estimated_minutes', 'no_runs_per_month', 'no_role_rate'],
}

function respond(cost: unknown = COSTED, rate: unknown = { hourly_rate: '120.000000', currency: 'EUR' }): void {
  get.mockImplementation((url: string) => {
    // Order matters: the cost URL also contains '/workflows'.
    if (url.includes('/cost')) return Promise.resolve(cost)
    if (url.includes('/rate')) return Promise.resolve(rate)
    if (url.includes('/holders')) return Promise.resolve([])
    if (url.includes('/permissions')) return Promise.resolve([])
    if (url.includes('/workflows')) return Promise.resolve(['wf-1'])
    // #14852: the company tool catalogue shares the '/tools' substring with
    // the role's own tool list, so it must be matched FIRST or it would be
    // served the role list and the picker would render from strings. Empty
    // here on purpose: with no catalogue the panel keeps its text box, which
    // is the control these tests were written against.
    if (url.startsWith('/api/llc/tools/')) return Promise.resolve([])
    if (url.includes('/tools')) return Promise.resolve([])
    if (url.includes('/credentials')) return Promise.resolve([])
    return Promise.resolve([ROLE])
  })
}

// #14860: one shared instance for the whole file. A fresh createI18n per
// mount re-ingested the ~400KB message bundle every time; nothing here
// mutates the instance, so building it once is enough.
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountView() {
  // The first role is selected automatically on load (RolesView L472), so the
  // detail pane is present without an explicit click.
  const wrapper = mount(RolesView, { global: { plugins: [i18n], stubs: { BaseModal: true } } })
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('step cost and role rate in the Roles tab (#14598, #14607)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    put.mockReset()
    del.mockReset()
  })

  it('shows the derived monthly cost of a costed step', async () => {
    respond()
    const wrapper = await mountView()

    const label = wrapper.find('[data-testid="step-cost-label-wf-1"]')
    expect(label.exists()).toBe(true)
    expect(label.text()).toContain('600.000000')
    expect(label.text()).toContain('EUR')
  })

  it('says an unmeasured step is not costed, never that it costs nothing', async () => {
    respond(UNCOSTED, null)
    const wrapper = await mountView()

    const label = wrapper.find('[data-testid="step-cost-label-wf-1"]')
    expect(label.exists()).toBe(true)
    // The point of the whole feature: no zero anywhere in that line.
    expect(label.text()).not.toContain('0')
    expect(label.text()).toBe(en.llcRoles.costNeedsRate)
  })

  it('says the role has no rate rather than showing a rate of zero', async () => {
    respond(UNCOSTED, null)
    const wrapper = await mountView()

    expect(wrapper.find('[data-testid="role-rate-absent"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="role-rate-amount"]').element.getAttribute('value')).not.toBe('0')
  })

  it('sends an emptied field as null, so a mistyped number can be removed', async () => {
    respond()
    put.mockResolvedValue(undefined)
    const wrapper = await mountView()

    await wrapper.find('[data-testid="step-minutes-wf-1"]').setValue('')
    await wrapper.find('[data-testid="step-cost-save-wf-1"]').trigger('click')
    await flushPromises()

    expect(put).toHaveBeenCalledWith('/api/llc/roles/c1/r1/workflows/wf-1/cost', {
      estimated_minutes: null,
      runs_per_month: 10,
    })
  })

  it('saves the role rate with its currency', async () => {
    respond(COSTED, null)
    put.mockResolvedValue(undefined)
    const wrapper = await mountView()

    await wrapper.find('[data-testid="role-rate-amount"]').setValue('95.5')
    await wrapper.find('[data-testid="role-rate-currency"]').setValue('pln')
    await wrapper.find('[data-testid="role-rate-save"]').trigger('click')
    await flushPromises()

    // Upper-cased: the server takes a three-letter code, and a lower-case one
    // would be rejected for a reason the user did not cause.
    expect(put).toHaveBeenCalledWith('/api/llc/roles/c1/r1/rate', {
      hourly_rate: '95.5',
      currency: 'PLN',
    })
  })

  it('survives a cost response of the wrong shape instead of blanking the view', async () => {
    // A response whose shape the panel does not read reached the template
    // during development and threw inside `cost.missing.includes(...)`, taking
    // the whole role detail down — the failure #13617 fixed elsewhere.
    respond(['not', 'a', 'cost', 'row'])
    const wrapper = await mountView()

    // The row is dropped...
    expect(wrapper.find('[data-testid="step-costs-panel"]').exists()).toBe(false)
    // ...and the rest of the detail still rendered, so the assertion above is
    // the guard working rather than the view having died.
    expect(wrapper.find('[data-testid="role-rate-panel"]').exists()).toBe(true)
  })
})
